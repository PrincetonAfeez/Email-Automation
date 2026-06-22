""" Test round3 fixes for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from emailauto.campaigns.services import cancel_campaign, reconcile_campaigns, set_campaign_status
from emailauto.core.results import SendResult
from emailauto.core.states import CampaignStatus, OutboxStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import force_requeue_outbox, send_outbox_email
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_cancel_campaign_bulk_cancels_open_outbox(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    dispatch_due_schedules()
    row = campaign_fixture["campaign"].outbox_rows.get()
    assert row.status in {OutboxStatus.PENDING, OutboxStatus.ENQUEUED}

    cancel_campaign(campaign_fixture["campaign"].id)

    row.refresh_from_db()
    assert row.status == OutboxStatus.CANCELLED
    assert "campaign is cancelled" in row.last_error


@pytest.mark.django_db
def test_reconcile_completes_campaign_with_no_outbox_rows(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])

    assert reconcile_campaigns() == 1
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.COMPLETED


@pytest.mark.django_db
def test_set_completed_rejected_with_open_outbox(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    dispatch_due_schedules()
    campaign_fixture["campaign"].status = CampaignStatus.ACTIVE
    campaign_fixture["campaign"].save(update_fields=["status"])

    with pytest.raises(ValueError, match="outbox work is still in progress"):
        set_campaign_status(campaign_fixture["campaign"].id, CampaignStatus.COMPLETED)


@pytest.mark.django_db
def test_force_requeue_releases_claimed_row(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.locked_by = "worker"
    dispatched_row.claim_token = "token"
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()

    row = force_requeue_outbox(dispatched_row.id)

    assert row.status == OutboxStatus.RETRY_SCHEDULED
    assert row.locked_by == ""
    assert row.claim_token == ""


@pytest.mark.django_db
def test_requeue_dlq_calls_enqueue(auth_client, dispatched_row):
    dispatched_row.max_attempts = 1
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "temporary"))
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.DEAD_LETTERED

    with patch("emailauto.scheduling.dispatcher.enqueue_outbox_by_id", return_value=True) as enqueue:
        response = auth_client.post(f"/dlq/{dispatched_row.id}/requeue/")

    assert response.status_code == 302
    enqueue.assert_called_once()
    dispatched_row.refresh_from_db()
    assert dispatched_row.status != OutboxStatus.DEAD_LETTERED
    assert dispatched_row.attempt_count == 0
