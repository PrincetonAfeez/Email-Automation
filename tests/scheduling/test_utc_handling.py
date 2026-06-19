from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from emailauto.cli.management.commands.emailauto_schedule import parse_dt
from emailauto.core import clock
from emailauto.core.states import ScheduleType
from emailauto.scheduling.due_scanner import due_schedules
from emailauto.scheduling.models import CampaignSchedule


def test_parse_dt_keeps_explicit_utc():
    parsed = parse_dt("2026-07-01T09:00:00Z")
    assert parsed.utcoffset() == timedelta(0)
    assert (parsed.year, parsed.month, parsed.day, parsed.hour) == (2026, 7, 1, 9)


def test_parse_dt_converts_naive_input_to_utc():
    # TIME_ZONE is UTC, so a naive 09:00 becomes 09:00 UTC.
    parsed = parse_dt("2026-07-01T09:00:00")
    assert parsed.utcoffset() == timedelta(0)
    assert parsed.hour == 9


def test_parse_dt_rejects_garbage():
    with pytest.raises(ValueError):
        parse_dt("not-a-date")


@pytest.mark.django_db
def test_due_scanner_follows_the_clock(campaign_fixture, monkeypatch):
    send_at = timezone.now() + timedelta(days=1)
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=send_at,
    )
    # Not due at the real "now".
    assert due_schedules().count() == 0

    # Advance the (monkeypatched) clock past send_at and it becomes due — this is the
    # fake-clock hook the scheduler relies on.
    monkeypatch.setattr(clock, "utcnow", lambda: send_at + timedelta(minutes=1))
    assert due_schedules().count() == 1
