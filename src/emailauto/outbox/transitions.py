""" Transitions for EmailAuto."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from emailauto.cache.stats_cache import invalidate_dashboard_stats
from emailauto.core.exceptions import StaleClaimToken
from emailauto.core.states import PROTECTED_OUTBOX_TARGETS, EventType, OutboxStatus, assert_outbox_transition
from emailauto.observability.events import record_event
from emailauto.outbox.models import EmailOutbox

EVENT_FOR_STATUS = {
    OutboxStatus.ENQUEUED: EventType.ENQUEUED,
    OutboxStatus.SENT: EventType.SENT,
    OutboxStatus.RETRY_SCHEDULED: EventType.RETRY_SCHEDULED,
    OutboxStatus.FAILED: EventType.FAILED,
    OutboxStatus.DEAD_LETTERED: EventType.DEAD_LETTERED,
    OutboxStatus.REQUEUED: EventType.REQUEUED,
    OutboxStatus.SKIPPED_SUPPRESSED: EventType.SKIPPED_SUPPRESSED,
    OutboxStatus.CANCELLED: EventType.CANCELLED,
}


def transition_outbox(
    outbox_id: int,
    target_status: str,
    *,
    claim_token: str = "",
    last_error: str = "",
    next_attempt_at=None,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
) -> EmailOutbox:
    with transaction.atomic():
        outbox = EmailOutbox.objects.select_for_update().select_related("campaign").get(pk=outbox_id)
        assert_outbox_transition(outbox.status, target_status)
        if target_status in PROTECTED_OUTBOX_TARGETS and not force and outbox.claim_token != claim_token:
            raise StaleClaimToken(f"Stale claim token for outbox {outbox_id}")

        now = timezone.now()
        outbox.status = target_status
        if target_status == OutboxStatus.SENDING:
            outbox.started_at = outbox.started_at or now
        elif target_status == OutboxStatus.SENT:
            outbox.sent_at = now
            outbox.last_error = ""
        elif target_status == OutboxStatus.RETRY_SCHEDULED:
            outbox.next_attempt_at = next_attempt_at
            outbox.last_error = last_error
            if force:
                outbox.locked_by = ""
                outbox.claim_token = ""
                outbox.locked_at = None
                outbox.enqueued_at = None
                outbox.celery_task_id = ""
        elif target_status == OutboxStatus.FAILED:
            outbox.failed_at = now
            outbox.last_error = last_error
        elif target_status == OutboxStatus.DEAD_LETTERED:
            outbox.dead_lettered_at = now
            outbox.last_error = last_error
        elif target_status == OutboxStatus.REQUEUED:
            outbox.next_attempt_at = now
            outbox.dead_lettered_at = None
            outbox.failed_at = None
            outbox.last_error = ""
            outbox.locked_by = ""
            outbox.claim_token = ""
            outbox.locked_at = None
            outbox.enqueued_at = None
            outbox.celery_task_id = ""
        elif target_status == OutboxStatus.SKIPPED_SUPPRESSED:
            outbox.last_error = last_error
        elif target_status == OutboxStatus.CANCELLED:
            outbox.last_error = last_error
            outbox.locked_by = ""
            outbox.claim_token = ""
            outbox.locked_at = None
            outbox.enqueued_at = None
            outbox.celery_task_id = ""

        outbox.save()
        event_type = EVENT_FOR_STATUS.get(target_status)
        if event_type:
            record_event(event_type, outbox=outbox, message=last_error, metadata=metadata or {})
        invalidate_dashboard_stats(campaign_id=outbox.campaign_id)
        return outbox


def enqueue_outbox_row(outbox_id: int, *, celery_task_id: str = "") -> EmailOutbox | None:
    with transaction.atomic():
        outbox = EmailOutbox.objects.select_for_update().get(pk=outbox_id)
        if outbox.status not in {OutboxStatus.PENDING, OutboxStatus.RETRY_SCHEDULED, OutboxStatus.REQUEUED}:
            return None
        assert_outbox_transition(outbox.status, OutboxStatus.ENQUEUED)
        outbox.status = OutboxStatus.ENQUEUED
        outbox.enqueued_at = timezone.now()
        outbox.celery_task_id = celery_task_id or outbox.celery_task_id
        outbox.save()
        record_event(EventType.ENQUEUED, outbox=outbox, metadata={"celery_task_id": celery_task_id})
        invalidate_dashboard_stats(campaign_id=outbox.campaign_id)
        _mark_run_dispatching(outbox.campaign_run_id)
        return outbox


def _mark_run_dispatching(campaign_run_id: int | None) -> None:
    if not campaign_run_id:
        return
    from emailauto.core.states import CampaignRunStatus, assert_campaign_run_transition
    from emailauto.scheduling.models import CampaignRun

    run = CampaignRun.objects.filter(pk=campaign_run_id, status=CampaignRunStatus.OUTBOX_GENERATED).first()
    if run is None:
        return
    assert_campaign_run_transition(run.status, CampaignRunStatus.DISPATCHING)
    CampaignRun.objects.filter(pk=campaign_run_id, status=CampaignRunStatus.OUTBOX_GENERATED).update(
        status=CampaignRunStatus.DISPATCHING,
        updated_at=timezone.now(),
    )
