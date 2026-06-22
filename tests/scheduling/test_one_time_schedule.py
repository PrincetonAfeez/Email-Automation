""" Test one time schedule for EmailAuto."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_one_time_schedule_runs_once_then_disables(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    assert schedule.next_run_at == schedule.send_at  # mirrored in save()

    first = dispatch_due_schedules()
    schedule.refresh_from_db()
    assert first.outbox_created == 1
    assert schedule.enabled is False

    second = dispatch_due_schedules()
    assert second.schedules_seen == 0
    assert second.outbox_created == 0


@pytest.mark.django_db
def test_future_one_time_schedule_is_not_due(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now() + timedelta(hours=1),
    )

    summary = dispatch_due_schedules()

    assert summary.schedules_seen == 0
    assert summary.outbox_created == 0
