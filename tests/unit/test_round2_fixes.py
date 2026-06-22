""" Test round2 fixes for EmailAuto."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from emailauto.campaigns.services import mark_campaign_completed, promote_campaign_to_active
from emailauto.core.results import SendResult
from emailauto.core.states import CampaignStatus, OutboxStatus, ScheduleType
from emailauto.outbox.services import force_requeue_outbox
from emailauto.scheduling.models import CampaignSchedule
from emailauto.scheduling.recurrence import cron_matches


def test_cron_dom_or_dow_when_both_restricted():
    # 15th and Monday both match on 2026-06-15.
    assert cron_matches(datetime(2026, 6, 15, 9, 0, tzinfo=UTC), "0 9 15 * MON")
    # Neither 15th nor Monday on 2026-06-16 (Tuesday the 16th).
    assert not cron_matches(datetime(2026, 6, 16, 9, 0, tzinfo=UTC), "0 9 15 * MON")
    # Day-of-month alone matches on the 16th even though it is not Monday.
    assert cron_matches(datetime(2026, 6, 16, 9, 0, tzinfo=UTC), "0 9 16 * MON")
    # Day-of-week alone matches on Monday the 15th even though DOM is 30.
    assert cron_matches(datetime(2026, 6, 15, 9, 0, tzinfo=UTC), "0 9 30 * MON")


@pytest.mark.django_db
def test_mark_completed_disables_schedules(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        cron_expression="0 9 * * MON",
        send_at=timezone.now(),
    )
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    mark_campaign_completed(campaign.id)
    assert not CampaignSchedule.objects.filter(campaign=campaign, enabled=True).exists()


@pytest.mark.django_db
def test_dispatch_promotes_scheduled_to_active(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    from emailauto.scheduling.dispatcher import dispatch_due_schedules

    dispatch_due_schedules()
    campaign_fixture["campaign"].refresh_from_db()
    assert campaign_fixture["campaign"].status == CampaignStatus.ACTIVE


@pytest.mark.django_db
def test_promote_campaign_to_active_idempotent(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    promote_campaign_to_active(campaign.id)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.ACTIVE


@pytest.mark.django_db
def test_finish_result_marks_sent_after_midflight_release(dispatched_row):
    """Provider success after force-requeue must reconcile to sent (no duplicate retry)."""
    from emailauto.outbox.services import _finish_result

    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "worker-token"
    dispatched_row.locked_by = "worker"
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()
    force_requeue_outbox(dispatched_row.id, enqueue_celery=False)
    outcome = _finish_result(dispatched_row, "worker-token", SendResult.success("fake"))
    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.SENT
    assert dispatched_row.status == OutboxStatus.SENT


@pytest.mark.django_db
def test_force_requeue_revokes_celery_task(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.celery_task_id = "task-123"
    dispatched_row.locked_by = "worker"
    dispatched_row.claim_token = "token"
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()

    with patch("emailauto.outbox.services._revoke_celery_task") as revoke:
        force_requeue_outbox(dispatched_row.id, enqueue_celery=False)
    revoke.assert_called_once_with("task-123")


@pytest.mark.django_db
def test_schedule_cannot_enable_on_paused_campaign(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.PAUSED
    campaign.save(update_fields=["status"])
    schedule = CampaignSchedule(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
        enabled=True,
    )
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        schedule.save()


@pytest.mark.django_db
def test_trigger_promotes_to_active(campaign_fixture):
    from emailauto.campaigns.services import trigger_campaign_now

    trigger_campaign_now(campaign_fixture["campaign"].id, enqueue_celery=False)
    campaign_fixture["campaign"].refresh_from_db()
    assert campaign_fixture["campaign"].status == CampaignStatus.ACTIVE
