""" Test outbox flow for EmailAuto."""

from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox, EmailSendAttempt
from emailauto.outbox.services import send_outbox_email
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_worker_sends_once_and_duplicate_task_is_noop(campaign_fixture):
    CampaignSchedule.objects.create(campaign=campaign_fixture["campaign"], schedule_type=ScheduleType.ONE_TIME, send_at=timezone.now())
    dispatch_due_schedules()
    row = EmailOutbox.objects.get()

    first = send_outbox_email(row.id, worker_id="w1", celery_task_id="task-1", backend_name="fake")
    second = send_outbox_email(row.id, worker_id="w2", celery_task_id="task-2", backend_name="fake")

    row.refresh_from_db()
    assert first.status == OutboxStatus.SENT
    assert second.status == OutboxStatus.SENT
    assert row.status == OutboxStatus.SENT
    assert len(FakeEmailBackend.sent_messages) == 1
    assert EmailSendAttempt.objects.count() == 1


@pytest.mark.django_db
def test_worker_dead_letters_exhausted_transient_failure(campaign_fixture):
    CampaignSchedule.objects.create(campaign=campaign_fixture["campaign"], schedule_type=ScheduleType.ONE_TIME, send_at=timezone.now())
    dispatch_due_schedules()
    row = EmailOutbox.objects.get()
    row.max_attempts = 1
    row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(row.recipient.email, result=SendResult.transient_failure("fake", "timeout", "temporary"))

    outcome = send_outbox_email(row.id, worker_id="w1", celery_task_id="task-1", backend_name="fake")

    row.refresh_from_db()
    assert outcome.status == OutboxStatus.DEAD_LETTERED
    assert row.status == OutboxStatus.DEAD_LETTERED
    assert row.attempt_count == 1
