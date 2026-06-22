""" Campaign services """

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Exists, OuterRef

from emailauto.campaigns.models import Campaign
from emailauto.core.states import CampaignRunStatus, CampaignStatus, EventType, OutboxStatus, ScheduleType, assert_campaign_transition
from emailauto.observability.events import record_event
from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.models import CampaignSchedule


@dataclass(frozen=True)
class TriggerResult:
    campaign_id: int
    run_id: int
    outbox_created: int
    outbox_enqueued: int


_OPEN_RUN_STATUSES = {
    CampaignRunStatus.PENDING,
    CampaignRunStatus.GENERATING_OUTBOX,
    CampaignRunStatus.OUTBOX_GENERATED,
    CampaignRunStatus.DISPATCHING,
    CampaignRunStatus.DISPATCHED,
}

_CAMPAIGN_TERMINAL_OUTBOX = {
    OutboxStatus.SENT,
    OutboxStatus.FAILED,
    OutboxStatus.DEAD_LETTERED,
    OutboxStatus.CANCELLED,
    OutboxStatus.SKIPPED_SUPPRESSED,
}

_OPEN_OUTBOX_STATUSES = {
    OutboxStatus.PENDING,
    OutboxStatus.ENQUEUED,
    OutboxStatus.CLAIMED,
    OutboxStatus.SENDING,
    OutboxStatus.RETRY_SCHEDULED,
    OutboxStatus.REQUEUED,
}

CREATABLE_CAMPAIGN_STATUSES = {CampaignStatus.DRAFT, CampaignStatus.SCHEDULED}

_RECONCILABLE_CAMPAIGN_STATUSES = {
    CampaignStatus.ACTIVE,
    CampaignStatus.SCHEDULED,
}


def _assert_no_open_outbox(campaign_id: int) -> None:
    if EmailOutbox.objects.filter(campaign_id=campaign_id, status__in=_OPEN_OUTBOX_STATUSES).exists():
        raise ValueError("Cannot mark a campaign completed while outbox work is still in progress.")


def promote_campaign_to_active(campaign_id: int) -> None:
    """Move a scheduled campaign to active when dispatch begins sending work."""
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().filter(pk=campaign_id, status=CampaignStatus.SCHEDULED).first()
        if campaign is None:
            return
        assert_campaign_transition(CampaignStatus.SCHEDULED, CampaignStatus.ACTIVE)
        campaign.status = CampaignStatus.ACTIVE
        campaign.save(update_fields=["status", "updated_at"])


def mark_campaign_completed(campaign_id: int, *, reconciled: bool = False) -> Campaign:
    """Transition a campaign to completed when all outbox work is terminal."""
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status == CampaignStatus.COMPLETED:
            return campaign
        if campaign.status == CampaignStatus.PAUSED:
            _assert_no_open_outbox(campaign_id)
        elif campaign.status in {CampaignStatus.ACTIVE, CampaignStatus.SCHEDULED}:
            assert_campaign_transition(campaign.status, CampaignStatus.COMPLETED)
            _assert_no_open_outbox(campaign_id)
        else:
            raise ValueError(f"Cannot complete a campaign in status '{campaign.status}'.")
        CampaignSchedule.objects.filter(campaign=campaign, enabled=True).update(enabled=False)
        campaign.status = CampaignStatus.COMPLETED
        campaign.status_before_pause = ""
        campaign.save(update_fields=["status", "status_before_pause", "updated_at"])
        record_event(
            EventType.CAMPAIGN_COMPLETED,
            campaign=campaign,
            metadata={"reconciled": reconciled},
        )
    return campaign


def set_campaign_status(campaign_id: int, status: str) -> Campaign:
    """Change a campaign's lifecycle status through the service layer."""
    valid = {value for value, _label in CampaignStatus.CHOICES}
    if status not in valid:
        raise ValueError(f"Unknown campaign status: {status}")
    if status == CampaignStatus.PAUSED:
        return pause_campaign(campaign_id)
    if status == CampaignStatus.CANCELLED:
        return cancel_campaign(campaign_id)
    if status == CampaignStatus.COMPLETED:
        return mark_campaign_completed(campaign_id)
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status == CampaignStatus.PAUSED and status in {CampaignStatus.ACTIVE, CampaignStatus.SCHEDULED}:
            return resume_campaign(campaign_id)
        assert_campaign_transition(campaign.status, status)
        campaign.status = status
        campaign.save(update_fields=["status", "updated_at"])
    return campaign


def pause_campaign(campaign_id: int) -> Campaign:
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status not in CampaignStatus.PAUSABLE:
            raise ValueError(f"Cannot pause a campaign in status '{campaign.status}'.")
        campaign.status_before_pause = campaign.status
        campaign.status = CampaignStatus.PAUSED
        campaign.save(update_fields=["status", "status_before_pause", "updated_at"])
    return campaign


def resume_campaign(campaign_id: int) -> Campaign:
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status != CampaignStatus.PAUSED:
            raise ValueError(f"Cannot resume a campaign in status '{campaign.status}'.")
        restored = campaign.status_before_pause or CampaignStatus.ACTIVE
        if restored not in {CampaignStatus.SCHEDULED, CampaignStatus.ACTIVE}:
            restored = CampaignStatus.ACTIVE
        campaign.status = restored
        campaign.status_before_pause = ""
        campaign.save(update_fields=["status", "status_before_pause", "updated_at"])
    return campaign


def cancel_campaign(campaign_id: int) -> Campaign:
    from emailauto.outbox.services import bulk_cancel_open_outbox
    from emailauto.scheduling.run_transitions import bulk_cancel_runs

    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
        if campaign.status not in CampaignStatus.CANCELLABLE:
            raise ValueError(f"Cannot cancel a campaign in status '{campaign.status}'.")
        campaign.status = CampaignStatus.CANCELLED
        campaign.status_before_pause = ""
        campaign.save(update_fields=["status", "status_before_pause", "updated_at"])
        CampaignSchedule.objects.filter(campaign=campaign, enabled=True).update(enabled=False)
        bulk_cancel_runs(campaign.id, open_statuses=_OPEN_RUN_STATUSES)
        bulk_cancel_open_outbox(campaign_id, reason="campaign is cancelled")
    return campaign


def reconcile_campaigns(*, limit: int = 100) -> int:
    """Mark campaigns completed when all outbox work is terminal and no schedules remain enabled."""
    enabled_schedules = CampaignSchedule.objects.filter(campaign_id=OuterRef("pk"), enabled=True)
    non_terminal_outbox = EmailOutbox.objects.filter(campaign_id=OuterRef("pk")).exclude(status__in=_CAMPAIGN_TERMINAL_OUTBOX)
    candidates = (
        Campaign.objects.filter(status__in=_RECONCILABLE_CAMPAIGN_STATUSES)
        .annotate(has_enabled_schedule=Exists(enabled_schedules), has_open_outbox=Exists(non_terminal_outbox))
        .filter(has_enabled_schedule=False, has_open_outbox=False)
        .order_by("id")[:limit]
    )
    reconciled = 0
    for campaign in candidates:
        try:
            mark_campaign_completed(campaign.id, reconciled=True)
        except ValueError:
            continue
        reconciled += 1
    return reconciled


def _assert_recipients_present(campaign: Campaign) -> None:
    if not campaign.recipient_list.recipients.exists():
        raise ValueError(f"Campaign '{campaign.name}' has an empty recipient list.")


def trigger_campaign_now(campaign_id: int, *, enqueue_celery: bool = True) -> TriggerResult:
    """Send a campaign immediately by creating a one-time 'now' occurrence and dispatching it.

    Each trigger is an explicit new occurrence (a deliberate resend), so it gets its own
    CampaignRun and idempotency keys.
    """
    from emailauto.core import clock
    from emailauto.scheduling.dispatcher import create_run_and_outbox, enqueue_due_outbox

    campaign = Campaign.objects.get(pk=campaign_id)
    if campaign.status in {CampaignStatus.CANCELLED, CampaignStatus.COMPLETED}:
        raise ValueError(f"Cannot trigger a campaign in status '{campaign.status}'.")
    if campaign.status == CampaignStatus.DRAFT:
        assert_campaign_transition(CampaignStatus.DRAFT, CampaignStatus.SCHEDULED)
        campaign.status = CampaignStatus.SCHEDULED
        campaign.save(update_fields=["status", "updated_at"])
    elif campaign.status not in CampaignStatus.TRIGGERABLE:
        raise ValueError(f"Cannot trigger a campaign in status '{campaign.status}'.")
    _assert_recipients_present(campaign)

    now = clock.utcnow()
    schedule = CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=now,
        enabled=True,
    )
    record_event(EventType.SCHEDULED, campaign=campaign, metadata={"trigger": "manual"})
    promote_campaign_to_active(campaign.id)
    run, created_count, _run_created = create_run_and_outbox(schedule)
    if run is None:
        raise RuntimeError("Failed to generate a run for the triggered campaign.")
    enqueued = enqueue_due_outbox(enqueue_celery=enqueue_celery, campaign_run_id=run.id)
    return TriggerResult(campaign_id=campaign.id, run_id=run.id, outbox_created=created_count, outbox_enqueued=enqueued)
