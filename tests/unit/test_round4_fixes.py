""" Test round4 fixes for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from emailauto.campaigns.services import cancel_campaign, mark_campaign_completed, reconcile_campaigns
from emailauto.core.states import CampaignStatus, OutboxStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import force_requeue_outbox, send_outbox_email
from emailauto.scheduling.dispatcher import enqueue_outbox_by_id
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_cancel_campaign_cancels_sending_row(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    from emailauto.scheduling.dispatcher import dispatch_due_schedules

    dispatch_due_schedules()
    row = campaign_fixture["campaign"].outbox_rows.get()
    row.status = OutboxStatus.SENDING
    row.locked_by = "worker"
    row.claim_token = "token"
    row.locked_at = timezone.now()
    row.save()

    cancel_campaign(campaign_fixture["campaign"].id)

    row.refresh_from_db()
    assert row.status == OutboxStatus.CANCELLED


@pytest.mark.django_db
def test_send_aborts_when_campaign_cancelled_during_sending(dispatched_row):
    campaign = dispatched_row.campaign

    def cancel_campaign_then_allow(*, campaign_id):
        campaign.status = CampaignStatus.CANCELLED
        campaign.save(update_fields=["status"])
        from emailauto.workers.throttling import ThrottleDecision

        return ThrottleDecision(True)

    with patch("emailauto.outbox.services.check_send", side_effect=cancel_campaign_then_allow):
        outcome = send_outbox_email(dispatched_row.id, worker_id="cli", backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.CANCELLED
    assert len(FakeEmailBackend.sent_messages) == 0


@pytest.mark.django_db
def test_enqueue_outbox_by_id_rolls_back_on_publish_failure(dispatched_row):
    dispatched_row.status = OutboxStatus.RETRY_SCHEDULED
    dispatched_row.next_attempt_at = timezone.now()
    dispatched_row.save()

    with patch("emailauto.scheduling.dispatcher._publish_task", return_value=False):
        assert enqueue_outbox_by_id(dispatched_row.id, enqueue_celery=True) is False

    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.RETRY_SCHEDULED
    assert "publish failed" in dispatched_row.last_error


@pytest.mark.django_db
def test_force_requeue_enqueues_immediately(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.locked_by = "worker"
    dispatched_row.claim_token = "token"
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()

    with patch("emailauto.scheduling.dispatcher.enqueue_outbox_by_id", return_value=True) as enqueue:
        force_requeue_outbox(dispatched_row.id)

    enqueue.assert_called_once_with(dispatched_row.id, enqueue_celery=True)


@pytest.mark.django_db
def test_reconcile_does_not_complete_paused_campaign(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.PAUSED
    campaign.status_before_pause = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status", "status_before_pause"])

    assert reconcile_campaigns() == 0
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.PAUSED


@pytest.mark.django_db
def test_mark_campaign_completed_records_event(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])

    mark_campaign_completed(campaign.id)
    assert campaign.event_logs.filter(event_type="campaign_completed").exists()


@pytest.mark.django_db
def test_health_endpoint_reports_database(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json()["database"] is True


@pytest.mark.django_db
def test_cli_campaign_create_rejects_duplicate_name(campaign_fixture):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="already exists"):
        call_command(
            "emailauto_campaign",
            "create",
            "--name",
            campaign_fixture["campaign"].name,
            "--template",
            campaign_fixture["template"].name,
            "--list",
            campaign_fixture["recipient_list"].name,
        )


@pytest.mark.django_db
def test_schedule_cannot_enable_on_cancelled_campaign(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    schedule = CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
        enabled=False,
    )
    schedule.enabled = True
    with pytest.raises(ValidationError):
        schedule.save()
