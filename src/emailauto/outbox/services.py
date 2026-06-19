from __future__ import annotations

import socket
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import F

from emailauto.core.exceptions import TemplateRenderError
from emailauto.core.results import SendResult
from emailauto.core.states import CampaignStatus, OutboxStatus
from emailauto.email_providers.base import get_backend
from emailauto.outbox.attempts import complete_attempt, start_attempt
from emailauto.outbox.claim import claim_outbox
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.transitions import transition_outbox
from emailauto.recipients.suppression import check_suppression
from emailauto.templates.renderer import TemplateSnapshot, render_template
from emailauto.workers.retry_policy import next_retry_at
from emailauto.workers.throttling import allow_send


@dataclass(frozen=True)
class SendOutcome:
    status: str
    outbox_id: int
    detail: str = ""


def _increment_attempt_count(outbox_id: int) -> EmailOutbox:
    EmailOutbox.objects.filter(pk=outbox_id).update(attempt_count=F("attempt_count") + 1)
    return EmailOutbox.objects.select_related("campaign", "campaign_run", "recipient", "template").get(pk=outbox_id)


def _finish_result(outbox: EmailOutbox, token: str, result: SendResult) -> SendOutcome:
    outbox = _increment_attempt_count(outbox.id)
    error = result.error_message or result.error_code
    if result.result == "success":
        updated = transition_outbox(outbox.id, OutboxStatus.SENT, claim_token=token)
        return SendOutcome(updated.status, updated.id)
    if result.result == "permanent_failure":
        updated = transition_outbox(outbox.id, OutboxStatus.FAILED, claim_token=token, last_error=error)
        return SendOutcome(updated.status, updated.id, error)
    if outbox.attempt_count >= outbox.max_attempts:
        updated = transition_outbox(outbox.id, OutboxStatus.DEAD_LETTERED, claim_token=token, last_error=error)
        return SendOutcome(updated.status, updated.id, error)
    updated = transition_outbox(
        outbox.id,
        OutboxStatus.RETRY_SCHEDULED,
        claim_token=token,
        last_error=error,
        next_attempt_at=next_retry_at(outbox.attempt_count),
    )
    return SendOutcome(updated.status, updated.id, error)


def _reschedule_without_attempt(outbox: EmailOutbox, token: str, reason: str) -> SendOutcome:
    """Release a claimed/sending row back to retry_scheduled without burning an attempt.

    Used for throttling and paused-campaign holds: the provider was never contacted,
    so the delay must not count toward max_attempts (otherwise a throttled job could be
    dead-lettered, losing it).
    """
    delay_seconds_basis = outbox.attempt_count or 1
    updated = transition_outbox(
        outbox.id,
        OutboxStatus.RETRY_SCHEDULED,
        claim_token=token,
        last_error=reason,
        next_attempt_at=next_retry_at(delay_seconds_basis),
    )
    return SendOutcome(updated.status, updated.id, reason)


def send_outbox_email(outbox_id: int, *, worker_id: str | None = None, celery_task_id: str = "", backend_name: str | None = None) -> SendOutcome:
    worker = worker_id or socket.gethostname() or "worker"
    claim = claim_outbox(outbox_id, worker_id=worker, celery_task_id=celery_task_id)
    if claim is None:
        current = EmailOutbox.objects.filter(pk=outbox_id).only("id", "status").first()
        return SendOutcome(current.status if current else "missing", outbox_id, "not claimable")

    # The row is now CLAIMED. Resolve every reason-not-to-send while still in CLAIMED,
    # because the state machine only permits skipped_suppressed/cancelled from claimed,
    # never from sending. (This is the fix for the suppression-at-send bug.)
    outbox = claim.outbox
    token = claim.token

    if outbox.campaign.status == CampaignStatus.CANCELLED:
        updated = transition_outbox(outbox.id, OutboxStatus.CANCELLED, claim_token=token, last_error="campaign is cancelled")
        return SendOutcome(updated.status, updated.id, "campaign is cancelled")

    if outbox.campaign.status == CampaignStatus.PAUSED:
        return _reschedule_without_attempt(outbox, token, "campaign is paused")

    suppression = check_suppression(outbox.recipient)
    if suppression.suppressed:
        updated = transition_outbox(
            outbox.id,
            OutboxStatus.SKIPPED_SUPPRESSED,
            claim_token=token,
            last_error=suppression.reason,
        )
        return SendOutcome(updated.status, updated.id, suppression.reason)

    # Commit to sending only once the row is known to be sendable.
    outbox = transition_outbox(outbox.id, OutboxStatus.SENDING, claim_token=token)
    backend = get_backend(backend_name)

    try:
        # Render from the immutable snapshot captured when the row was created, not from
        # the live template — a queued email must not change if the template is edited.
        rendered = render_template(
            email_template=TemplateSnapshot.from_outbox(outbox),
            recipient=outbox.recipient,
            campaign=outbox.campaign,
            campaign_run=outbox.campaign_run,
            idempotency_key=outbox.idempotency_key,
        )
    except TemplateRenderError as exc:
        attempt = start_attempt(outbox=outbox, worker_id=worker, celery_task_id=celery_task_id, provider_name="renderer")
        result = SendResult.permanent_failure("renderer", "template_render_error", str(exc))
        complete_attempt(attempt, result)
        return _finish_result(outbox, token, result)

    throttle = allow_send(campaign_id=outbox.campaign_id)
    if not throttle.allowed:
        # A throttle rejection is a delay, not a delivery attempt: reschedule without
        # incrementing attempt_count. The retry_scheduled event records the decision.
        return _reschedule_without_attempt(outbox, token, throttle.reason)

    attempt = start_attempt(outbox=outbox, worker_id=worker, celery_task_id=celery_task_id, provider_name=backend.provider_name)
    try:
        result = backend.send_email(rendered)
    except Exception as exc:
        result = SendResult.transient_failure(backend.provider_name, type(exc).__name__, str(exc))
    complete_attempt(attempt, result)
    return _finish_result(outbox, token, result)


def requeue_outbox(outbox_id: int) -> EmailOutbox:
    """Requeue a failed or dead-lettered row for another delivery cycle."""
    with transaction.atomic():
        outbox = EmailOutbox.objects.select_for_update().get(pk=outbox_id)
        if outbox.status not in {OutboxStatus.DEAD_LETTERED, OutboxStatus.FAILED}:
            raise ValueError("Only failed or dead-lettered outbox rows can be requeued.")
        outbox.attempt_count = 0
        outbox.max_attempts = settings.EMAILAUTO_MAX_SEND_ATTEMPTS
        outbox.save(update_fields=["attempt_count", "max_attempts", "updated_at"])
        return transition_outbox(outbox.id, OutboxStatus.REQUEUED)


def requeue_dead_letter(outbox_id: int) -> EmailOutbox:
    """Backwards-compatible alias for requeueing a dead-lettered row."""
    return requeue_outbox(outbox_id)


def retry_outbox(outbox_id: int, *, enqueue_celery: bool | None = None) -> EmailOutbox:
    """Operator 'retry now' for a single row.

    Failed/dead-lettered rows are requeued (attempts reset); pipeline rows are made due
    and enqueued immediately when Celery is enabled.
    """
    from emailauto.core import clock
    from emailauto.scheduling.dispatcher import enqueue_outbox_by_id, republish_enqueued_row

    use_celery = True if enqueue_celery is None else enqueue_celery
    enqueue_after: int | None = None

    with transaction.atomic():
        outbox = EmailOutbox.objects.select_for_update().get(pk=outbox_id)
        if outbox.status in {OutboxStatus.DEAD_LETTERED, OutboxStatus.FAILED}:
            outbox = requeue_outbox(outbox_id)
            enqueue_after = outbox.id if use_celery else None
        elif outbox.status == OutboxStatus.ENQUEUED:
            if use_celery and republish_enqueued_row(outbox.id):
                return EmailOutbox.objects.get(pk=outbox_id)
            outbox = transition_outbox(
                outbox.id,
                OutboxStatus.RETRY_SCHEDULED,
                force=True,
                last_error="operator retry",
                next_attempt_at=clock.utcnow(),
                metadata={"operator": "retry"},
            )
            enqueue_after = outbox.id if use_celery else None
        elif outbox.status in {
            OutboxStatus.PENDING,
            OutboxStatus.RETRY_SCHEDULED,
            OutboxStatus.REQUEUED,
        }:
            outbox.next_attempt_at = clock.utcnow()
            outbox.save(update_fields=["next_attempt_at", "updated_at"])
            enqueue_after = outbox.id if use_celery else None
        else:
            raise ValueError(f"Cannot retry an outbox row in status '{outbox.status}'.")

    if enqueue_after is not None:
        enqueue_outbox_by_id(enqueue_after, enqueue_celery=True)
    return EmailOutbox.objects.get(pk=outbox_id)


def release_stale_outbox(outbox_id: int, *, reason: str) -> EmailOutbox | None:
    """Release a row stuck in claimed/sending back to retry_scheduled (system recovery)."""
    outbox = EmailOutbox.objects.filter(pk=outbox_id).only("id", "status", "attempt_count").first()
    if outbox is None or outbox.status not in {OutboxStatus.CLAIMED, OutboxStatus.SENDING}:
        return None
    delay_basis = outbox.attempt_count or 1
    return transition_outbox(
        outbox_id,
        OutboxStatus.RETRY_SCHEDULED,
        force=True,
        last_error=reason,
        next_attempt_at=next_retry_at(delay_basis),
        metadata={"recovery": "stale_claim"},
    )


def force_requeue_outbox(outbox_id: int, *, reason: str = "operator force requeue") -> EmailOutbox:
    """Operator recovery for rows stuck in claimed/sending after a worker crash."""
    with transaction.atomic():
        outbox = EmailOutbox.objects.select_for_update().get(pk=outbox_id)
        if outbox.status not in {OutboxStatus.CLAIMED, OutboxStatus.SENDING}:
            raise ValueError("Only claimed or sending rows can be force-requeued.")
    released = release_stale_outbox(outbox_id, reason=reason)
    if released is None:
        raise ValueError(f"Could not force-requeue outbox {outbox_id}.")
    return released


def cancel_outbox(outbox_id: int) -> EmailOutbox:
    """Cancel a row that has not yet entered the send path."""
    with transaction.atomic():
        outbox = EmailOutbox.objects.select_for_update().get(pk=outbox_id)
        if outbox.status not in {
            OutboxStatus.PENDING,
            OutboxStatus.ENQUEUED,
            OutboxStatus.RETRY_SCHEDULED,
            OutboxStatus.REQUEUED,
        }:
            raise ValueError("Only pending, enqueued, retry-scheduled, or requeued rows can be cancelled.")
        return transition_outbox(outbox.id, OutboxStatus.CANCELLED, last_error="cancelled by operator")
