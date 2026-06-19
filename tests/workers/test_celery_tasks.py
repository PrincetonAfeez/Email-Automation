from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from emailauto.core.states import OutboxStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.models import CampaignSchedule
from emailauto.scheduling.tasks import dispatch_due_schedules_task
from emailauto.workers.tasks import send_outbox_email_task


@pytest.mark.django_db
def test_send_outbox_email_task_sends_through_the_real_task(dispatched_row, settings):
    settings.EMAILAUTO_EMAIL_BACKEND = "fake"

    result = send_outbox_email_task.apply(args=[dispatched_row.id]).get()

    dispatched_row.refresh_from_db()
    assert result["status"] == OutboxStatus.SENT
    assert dispatched_row.status == OutboxStatus.SENT
    assert len(FakeEmailBackend.sent_messages) == 1


@pytest.mark.django_db
def test_dispatch_due_schedules_task_runs_the_pipeline(campaign_fixture, settings):
    settings.EMAILAUTO_EMAIL_BACKEND = "fake"
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    # Beat path: enqueue_celery=True; nested send task runs eagerly (CELERY_TASK_ALWAYS_EAGER).
    summary = dispatch_due_schedules_task.apply().get()

    assert summary["outbox_created"] == 1
    assert EmailOutbox.objects.get().status == OutboxStatus.SENT


@pytest.mark.django_db
def test_emailauto_beat_registers_dispatcher_periodic_task():
    from django_celery_beat.models import PeriodicTask

    call_command("emailauto_beat", "ensure-dispatcher", stdout=StringIO())

    assert PeriodicTask.objects.filter(task="emailauto.scheduling.dispatch_due_schedules", enabled=True).exists()
