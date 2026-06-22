""" Test cron for EmailAuto."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from emailauto.core.states import ScheduleType
from emailauto.scheduling.models import CampaignSchedule
from emailauto.scheduling.recurrence import add_interval, cron_matches, next_cron_after, next_occurrence


def _utc(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _monday_9am():
    base = _utc(2026, 6, 15, 9, 0)
    return base - timedelta(days=base.weekday())  # normalise to a real Monday 09:00


def test_named_weekday_uses_cron_convention():
    monday = _monday_9am()
    tuesday = monday + timedelta(days=1)
    sunday = monday + timedelta(days=6)
    assert cron_matches(monday, "0 9 * * MON")
    assert not cron_matches(tuesday, "0 9 * * MON")
    assert cron_matches(sunday, "0 9 * * SUN")
    # Sunday is both 0 and 7 in cron.
    assert cron_matches(sunday, "0 9 * * 0")
    assert cron_matches(sunday, "0 9 * * 7")


def test_weekday_range_with_names():
    monday = _monday_9am()
    friday = monday + timedelta(days=4)
    saturday = monday + timedelta(days=5)
    assert cron_matches(friday, "0 9 * * MON-FRI")
    assert not cron_matches(saturday, "0 9 * * MON-FRI")


def test_minute_step_expression():
    assert cron_matches(_utc(2026, 6, 15, 9, 15), "*/15 * * * *")
    assert not cron_matches(_utc(2026, 6, 15, 9, 16), "*/15 * * * *")


def test_next_cron_after_advances_to_next_week():
    monday = _monday_9am()
    assert next_cron_after(monday, "0 9 * * MON") == monday + timedelta(days=7)


def test_next_cron_after_rejects_malformed_expression():
    with pytest.raises(ValueError):
        next_cron_after(_monday_9am(), "0 9 * *")


def test_add_interval_supports_each_period():
    start = _utc(2026, 6, 15, 9, 0)
    assert add_interval(start, every=30, period="minutes") == start + timedelta(minutes=30)
    assert add_interval(start, every=2, period="hours") == start + timedelta(hours=2)
    assert add_interval(start, every=3, period="days") == start + timedelta(days=3)


@pytest.mark.django_db
def test_next_occurrence_prefers_interval(campaign_fixture):
    start = _utc(2026, 6, 15, 9, 0)
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        send_at=start,
        interval_every=2,
        interval_period=CampaignSchedule.IntervalPeriod.HOURS,
    )
    assert next_occurrence(schedule, start) == start + timedelta(hours=2)
