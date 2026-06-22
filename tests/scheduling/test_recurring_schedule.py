""" Test recurring schedule for EmailAuto."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_recurring_interval_schedule_advances_next_run(campaign_fixture):
    start = timezone.now() - timedelta(minutes=1)
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        send_at=start,
        interval_every=10,
        interval_period=CampaignSchedule.IntervalPeriod.MINUTES,
    )

    dispatch_due_schedules()

    schedule.refresh_from_db()
    assert schedule.enabled is True
    assert schedule.next_run_at == start + timedelta(minutes=10)

