""" Test run lifecycle for EmailAuto."""

from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.core.results import SendResult
from emailauto.core.states import CampaignRunStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import send_outbox_email
from emailauto.scheduling.dispatcher import dispatch_due_schedules, reconcile_campaign_runs
from emailauto.scheduling.models import CampaignRun, CampaignSchedule


@pytest.mark.django_db
def test_run_advances_to_dispatched_then_completed(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    dispatch_due_schedules()  # creates rows, enqueues, and reconciles
    run = CampaignRun.objects.get()
    assert run.status == CampaignRunStatus.DISPATCHED  # rows are in flight

    for row in EmailOutbox.objects.filter(campaign_run=run):
        send_outbox_email(row.id, backend_name="fake")
    reconcile_campaign_runs()

    run.refresh_from_db()
    assert run.status == CampaignRunStatus.COMPLETED


@pytest.mark.django_db
def test_run_with_empty_recipient_list_completes(campaign_fixture):
    campaign_fixture["recipient_list"].recipients.clear()
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    dispatch_due_schedules()

    run = CampaignRun.objects.get()
    assert run.status == CampaignRunStatus.COMPLETED  # no rows to send -> done, not stuck


@pytest.mark.django_db
def test_run_marked_failed_when_a_row_dead_letters(dispatched_row):
    dispatched_row.max_attempts = 1
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "t", "t"))

    send_outbox_email(dispatched_row.id, backend_name="fake")
    reconcile_campaign_runs()

    run = dispatched_row.campaign_run
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.FAILED
