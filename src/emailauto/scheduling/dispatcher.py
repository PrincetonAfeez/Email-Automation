from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from emailauto.core.states import CampaignRunStatus, CampaignStatus, EventType, OutboxStatus, ScheduleType
from emailauto.observability.events import record_event
from emailauto.observability.logging import log_event
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.transitions import enqueue_outbox_row
from emailauto.scheduling.due_scanner import due_schedules
from emailauto.scheduling.models import CampaignRun, CampaignSchedule
from emailauto.scheduling.recurrence import next_occurrence

# Outbox statuses that, for run reconciliation, count as "done", "failed", or "in flight".
_RUN_TERMINAL = {
    OutboxStatus.SENT,
    OutboxStatus.FAILED,
    OutboxStatus.DEAD_LETTERED,
    OutboxStatus.CANCELLED,
    OutboxStatus.SKIPPED_SUPPRESSED,
}
_RUN_FAILED = {OutboxStatus.FAILED, OutboxStatus.DEAD_LETTERED}
_RUN_INFLIGHT = {OutboxStatus.ENQUEUED, OutboxStatus.CLAIMED, OutboxStatus.SENDING, OutboxStatus.RETRY_SCHEDULED}


@dataclass
class DispatchSummary:
    schedules_seen: int = 0
    runs_created: int = 0
    outbox_created: int = 0
    outbox_enqueued: int = 0
    runs_reconciled: int = 0


def idempotency_key(*, campaign_id: int, campaign_run_id: int, recipient_id: int) -> str:
    return f"campaign:{campaign_id}:run:{campaign_run_id}:recipient:{recipient_id}"


def run_key_for(schedule: CampaignSchedule, scheduled_for) -> str:
    return f"schedule:{schedule.id}:{scheduled_for.isoformat()}"


def _advance_schedule(schedule: CampaignSchedule, scheduled_for) -> None:
    schedule.last_run_at = scheduled_for
    if schedule.schedule_type == ScheduleType.ONE_TIME:
        schedule.enabled = False
    else:
        try:
            schedule.next_run_at = next_occurrence(schedule, scheduled_for)
        except ValueError as exc:
            # Couldn't compute the next occurrence (e.g. a valid-but-impossible date like
            # Feb 30 with no match in the horizon). Disable the schedule, but because this
            # runs inside the row-creating transaction, swallow the error so the current
            # occurrence's outbox rows are NOT rolled back — the scheduled send still happens.
            log_event("schedule_advance_failed", schedule_id=schedule.id, error=str(exc))
            schedule.next_run_at = None
            schedule.enabled = False
        else:
            if schedule.next_run_at is None:
                schedule.enabled = False
    schedule.save(update_fields=["last_run_at", "enabled", "next_run_at", "updated_at"])


def create_run_and_outbox(schedule: CampaignSchedule, *, batch_size: int = 500) -> tuple[CampaignRun | None, int, bool]:
    """Generate outbox rows for one schedule occurrence in a bounded batch.

    Large recipient lists are processed across multiple dispatcher ticks: each call
    creates at most ``batch_size`` new rows for the occurrence. The schedule is only
    advanced once *every* recipient has a row, so no recipient is ever dropped.

    Returns ``(None, 0, False)`` when another dispatcher already holds the schedule's lock
    (PostgreSQL SKIP LOCKED): the row is left for that dispatcher rather than blocking, which
    avoids starvation between concurrent dispatchers. See docs/adr/0001-concurrency-and-locking.md.
    """
    with transaction.atomic():
        # Skip a schedule another dispatcher is already working (Postgres); no-op on SQLite.
        skip_locked = connection.features.has_select_for_update_skip_locked
        locked_schedule = (
            CampaignSchedule.objects.select_for_update(skip_locked=skip_locked)
            .select_related("campaign")
            .filter(pk=schedule.pk)
            .first()
        )
        if locked_schedule is None:
            return None, 0, False
        scheduled_for = locked_schedule.next_run_at or locked_schedule.send_at or timezone.now()
        run_key = run_key_for(locked_schedule, scheduled_for)
        run, created = CampaignRun.objects.get_or_create(
            run_key=run_key,
            defaults={
                "campaign": locked_schedule.campaign,
                "schedule": locked_schedule,
                "scheduled_for": scheduled_for,
                "generated_at": timezone.now(),
                "status": CampaignRunStatus.GENERATING_OUTBOX,
            },
        )
        # A run that has already moved past outbox generation is complete; just advance.
        if not created and run.status not in {
            CampaignRunStatus.PENDING,
            CampaignRunStatus.GENERATING_OUTBOX,
            CampaignRunStatus.OUTBOX_GENERATED,
        }:
            _advance_schedule(locked_schedule, scheduled_for)
            return run, 0, False

        if run.status != CampaignRunStatus.GENERATING_OUTBOX:
            run.status = CampaignRunStatus.GENERATING_OUTBOX
            run.generated_at = run.generated_at or timezone.now()
            run.save(update_fields=["status", "generated_at", "updated_at"])

        campaign = locked_schedule.campaign
        template = campaign.template
        all_recipients = campaign.recipient_list.recipients
        already_generated = EmailOutbox.objects.filter(campaign_run=run).values("recipient_id")
        pending_recipients = all_recipients.exclude(id__in=already_generated).order_by("id")[:batch_size]

        created_count = 0
        for recipient in pending_recipients:
            key = idempotency_key(campaign_id=campaign.id, campaign_run_id=run.id, recipient_id=recipient.id)
            try:
                outbox, was_created = EmailOutbox.objects.get_or_create(
                    idempotency_key=key,
                    defaults={
                        "campaign": campaign,
                        "campaign_run": run,
                        "recipient": recipient,
                        "template": template,
                        "subject_snapshot": template.subject_template,
                        "body_snapshot": template.body_template,
                        "required_variables_snapshot": list(template.required_variables or []),
                        "body_format": template.body_format,
                        "scheduled_for": scheduled_for,
                        "next_attempt_at": scheduled_for,
                        "max_attempts": settings.EMAILAUTO_MAX_SEND_ATTEMPTS,
                    },
                )
            except IntegrityError:
                was_created = False
                outbox = EmailOutbox.objects.get(idempotency_key=key)
            if was_created:
                created_count += 1
                record_event(EventType.OUTBOX_CREATED, outbox=outbox)

        total_recipients = all_recipients.count()
        generated_rows = EmailOutbox.objects.filter(campaign_run=run).count()
        occurrence_complete = generated_rows >= total_recipients
        if occurrence_complete:
            run.status = CampaignRunStatus.OUTBOX_GENERATED
            run.save(update_fields=["status", "updated_at"])
            record_event(EventType.SCHEDULED, campaign=campaign, campaign_run=run, metadata={"generated_outbox": generated_rows})
            # Only advance the schedule once the whole occurrence is materialised; an
            # incomplete batch leaves the schedule due so the next tick continues it.
            _advance_schedule(locked_schedule, scheduled_for)
    return run, created_count, created


def _publish_task(outbox_id: int, celery_task_id: str) -> bool:
    """Publish the worker task, swallowing broker errors so one failure can't abort the batch."""
    from emailauto.workers.tasks import send_outbox_email_task

    try:
        send_outbox_email_task.apply_async(args=[outbox_id], task_id=celery_task_id or None)
        return True
    except Exception as exc:  # broker unreachable, serialization error, etc.
        log_event("enqueue_publish_failed", outbox_id=outbox_id, error=str(exc))
        return False


def republish_enqueued_row(outbox_id: int, *, celery_task_id: str | None = None) -> bool:
    """Re-publish a Celery task for a row already marked enqueued (operator retry / recovery)."""
    task_id = celery_task_id or uuid4().hex
    if not EmailOutbox.objects.filter(pk=outbox_id, status=OutboxStatus.ENQUEUED).exists():
        return False
    if not _publish_task(outbox_id, task_id):
        return False
    now = timezone.now()
    EmailOutbox.objects.filter(pk=outbox_id, status=OutboxStatus.ENQUEUED).update(
        enqueued_at=now,
        celery_task_id=task_id,
        next_attempt_at=now,
    )
    return True


def _recover_stale_enqueued(*, now, limit: int, active_statuses: list[str]) -> int:
    """Re-publish rows stuck in 'enqueued' whose task appears lost (never claimed).

    A row that has sat in 'enqueued' longer than the stale window was almost certainly
    lost between mark-enqueued and broker publish; the claim is idempotent, so a duplicate
    publish is safe (only one task can win the claim).
    """
    threshold = now - timedelta(seconds=settings.EMAILAUTO_ENQUEUED_STALE_SECONDS)
    stale = list(
        EmailOutbox.objects.filter(
            status=OutboxStatus.ENQUEUED,
            enqueued_at__lte=threshold,
            campaign__status__in=active_statuses,
        ).order_by("enqueued_at", "id")[:limit]
    )
    recovered = 0
    for row in stale:
        task_id = uuid4().hex
        log_event("enqueue_recovered_stale", outbox_id=row.id, enqueued_at=row.enqueued_at)
        if _publish_task(row.id, task_id):
            # Refresh the enqueue stamp so a still-unclaimed row isn't re-published on every
            # tick (only if it is still enqueued — a just-claimed row must be left alone).
            EmailOutbox.objects.filter(pk=row.id, status=OutboxStatus.ENQUEUED).update(enqueued_at=now, celery_task_id=task_id)
            recovered += 1
    return recovered


# Campaigns whose outbox rows may be stale-recovered (paused rows are not sent until resumed).
_RECOVERABLE_CAMPAIGN_STATUSES = [CampaignStatus.SCHEDULED, CampaignStatus.ACTIVE, CampaignStatus.PAUSED]


def _recover_stale_claims(*, now, limit: int, campaign_statuses: list[str] | None = None) -> int:
    """Release rows stuck in claimed/sending after a worker crash or kill."""
    from emailauto.outbox.services import release_stale_outbox

    statuses = campaign_statuses or _RECOVERABLE_CAMPAIGN_STATUSES
    threshold = now - timedelta(seconds=settings.EMAILAUTO_CLAIMED_STALE_SECONDS)
    stale = list(
        EmailOutbox.objects.filter(
            status__in=[OutboxStatus.CLAIMED, OutboxStatus.SENDING],
            locked_at__lte=threshold,
            campaign__status__in=statuses,
        ).order_by("locked_at", "id")[:limit]
    )
    recovered = 0
    for row in stale:
        log_event("claim_recovered_stale", outbox_id=row.id, locked_at=row.locked_at, status=row.status)
        if release_stale_outbox(row.id, reason="stale worker claim recovered"):
            recovered += 1
    return recovered


def enqueue_outbox_by_id(outbox_id: int, *, enqueue_celery: bool = False) -> bool:
    """Mark one due row enqueued and optionally publish its worker task."""
    celery_task_id = uuid4().hex if enqueue_celery else ""
    enqueued = enqueue_outbox_row(outbox_id, celery_task_id=celery_task_id)
    if enqueued is None:
        return False
    if enqueue_celery:
        _publish_task(outbox_id, celery_task_id)
    return True


def enqueue_due_outbox(*, limit: int = 500, enqueue_celery: bool = False, campaign_run_id: int | None = None) -> int:
    now = timezone.now()
    active_statuses = [CampaignStatus.SCHEDULED, CampaignStatus.ACTIVE]
    # Only enqueue work for campaigns that are actively sending. Paused, cancelled,
    # draft, or completed campaigns keep their rows parked until they are resumed.
    rows = list(
        EmailOutbox.objects.filter(
            status__in=[OutboxStatus.PENDING, OutboxStatus.RETRY_SCHEDULED, OutboxStatus.REQUEUED],
            next_attempt_at__lte=now,
            campaign__status__in=active_statuses,
            **({"campaign_run_id": campaign_run_id} if campaign_run_id is not None else {}),
        ).order_by("next_attempt_at", "id")[:limit]
    )
    count = 0
    for row in rows:
        celery_task_id = uuid4().hex if enqueue_celery else ""
        enqueued = enqueue_outbox_row(row.id, celery_task_id=celery_task_id)
        if enqueued is None:
            continue
        count += 1
        if enqueue_celery:
            _publish_task(row.id, celery_task_id)
    if enqueue_celery:
        _recover_stale_enqueued(now=now, limit=limit, active_statuses=active_statuses)
    return count


def reconcile_campaign_runs(*, limit: int = 500) -> int:
    """Advance CampaignRun status from its outbox rows (dispatched -> completed/failed).

    Uses a single grouped aggregation over the candidate runs rather than one query per
    run, so reconciliation stays cheap as runs accumulate.
    """
    runs = list(
        CampaignRun.objects.select_related("campaign")
        .filter(status__in=[CampaignRunStatus.OUTBOX_GENERATED, CampaignRunStatus.DISPATCHING, CampaignRunStatus.DISPATCHED])
        .order_by("id")[:limit]
    )
    if not runs:
        return 0
    run_ids = [run.id for run in runs]
    counts = {
        row["campaign_run"]: row
        for row in (
            EmailOutbox.objects.filter(campaign_run_id__in=run_ids)
            .values("campaign_run")
            .annotate(
                total=Count("id"),
                terminal=Count("id", filter=Q(status__in=_RUN_TERMINAL)),
                failed=Count("id", filter=Q(status__in=_RUN_FAILED)),
                inflight=Count("id", filter=Q(status__in=_RUN_INFLIGHT)),
            )
        )
    }
    reconciled = 0
    for run in runs:
        agg = counts.get(run.id)
        if not agg or agg["total"] == 0:
            # A generated run with no rows (e.g. an empty recipient list) is complete.
            new_status = CampaignRunStatus.COMPLETED if run.status == CampaignRunStatus.OUTBOX_GENERATED else run.status
        elif agg["terminal"] == agg["total"]:
            new_status = CampaignRunStatus.FAILED if agg["failed"] else CampaignRunStatus.COMPLETED
        elif agg["inflight"]:
            new_status = CampaignRunStatus.DISPATCHED
        elif run.status in {CampaignRunStatus.OUTBOX_GENERATED, CampaignRunStatus.DISPATCHING}:
            new_status = CampaignRunStatus.DISPATCHING
        else:
            new_status = run.status
        if new_status != run.status:
            run.status = new_status
            run.save(update_fields=["status", "updated_at"])
            reconciled += 1
            if new_status == CampaignRunStatus.DISPATCHED:
                record_event(EventType.DISPATCHED, campaign=run.campaign, campaign_run=run)
            else:
                log_event("campaign_run_finished", campaign_run_id=run.id, campaign_id=run.campaign_id, status=new_status)
    return reconciled


def dispatch_due_schedules(*, now=None, batch_size: int = 500, enqueue_celery: bool = False) -> DispatchSummary:
    summary = DispatchSummary()
    for schedule in due_schedules(now=now)[:batch_size]:
        summary.schedules_seen += 1
        try:
            run, created_count, run_created = create_run_and_outbox(schedule, batch_size=batch_size)
        except ValueError as exc:
            # A malformed/impossible schedule (e.g. a cron that never matches) must not
            # halt the whole tick — disable it so it stops failing, and keep going.
            _disable_broken_schedule(schedule, exc)
            continue
        except Exception as exc:  # unexpected/transient error: log and continue
            log_event("schedule_dispatch_error", schedule_id=schedule.id, error=str(exc))
            continue
        if run_created:
            summary.runs_created += 1
        summary.outbox_created += created_count
    summary.outbox_enqueued += enqueue_due_outbox(limit=batch_size, enqueue_celery=enqueue_celery)
    summary.runs_reconciled += reconcile_campaign_runs(limit=batch_size)
    from emailauto.campaigns.services import reconcile_campaigns

    reconcile_campaigns(limit=batch_size)
    now = now or timezone.now()
    if enqueue_celery:
        _recover_stale_enqueued(
            now=now,
            limit=batch_size,
            active_statuses=[CampaignStatus.SCHEDULED, CampaignStatus.ACTIVE],
        )
    _recover_stale_claims(now=now, limit=batch_size)
    return summary


def _disable_broken_schedule(schedule: CampaignSchedule, exc: Exception) -> None:
    log_event("schedule_disabled_broken", schedule_id=schedule.id, error=str(exc))
    CampaignSchedule.objects.filter(pk=schedule.pk).update(enabled=False)

