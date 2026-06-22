""" Test max coverage recurrence for EmailAuto."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from emailauto.scheduling.models import CampaignSchedule
from emailauto.scheduling.recurrence import (
    add_interval,
    cron_matches,
    next_occurrence,
    validate_cron_expression,
)


def test_add_interval_unsupported_period():
    with pytest.raises(ValueError, match="Unsupported interval period"):
        add_interval(datetime(2026, 1, 1, tzinfo=UTC), every=1, period="weeks")


def test_field_matches_step_and_range_and_names():
    moment = datetime(2026, 6, 15, 9, 30, tzinfo=UTC)
    assert cron_matches(moment, "30 9 15 6 MON")
    assert cron_matches(moment, "*/15 9 15 6 MON")
    assert cron_matches(moment, "30 9 15 JUN MON")
    assert cron_matches(datetime(2026, 6, 10, 9, 30, tzinfo=UTC), "30 9 10-20 6 MON")


def test_field_matches_empty_token_parts():
    assert cron_matches(datetime(2026, 6, 15, 9, 30, tzinfo=UTC), "30 9 15, 6 MON")


def test_weekday_step_and_range():
    assert cron_matches(datetime(2026, 6, 15, 9, 0, tzinfo=UTC), "0 9 * * MON-WED")
    assert cron_matches(datetime(2026, 6, 14, 9, 0, tzinfo=UTC), "0 9 * * */2")


def test_validate_cron_expression_rejects_bad_field_count():
    with pytest.raises(ValueError, match="exactly five fields"):
        validate_cron_expression("0 9 * *")


def test_validate_cron_expression_rejects_bad_tokens():
    with pytest.raises(ValueError):
        validate_cron_expression("0 9 * * NOPE")


@pytest.mark.django_db
def test_next_occurrence_non_recurring_returns_none(campaign_fixture):
    schedule = CampaignSchedule(
        campaign=campaign_fixture["campaign"],
        schedule_type="one_time",
        send_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert next_occurrence(schedule, datetime(2026, 1, 1, tzinfo=UTC)) is None


@pytest.mark.django_db
def test_next_occurrence_interval_path(campaign_fixture):
    schedule = CampaignSchedule(
        campaign=campaign_fixture["campaign"],
        schedule_type="recurring",
        interval_every=2,
        interval_period=CampaignSchedule.IntervalPeriod.HOURS,
    )
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    nxt = next_occurrence(schedule, start)
    assert nxt == datetime(2026, 1, 1, 14, 0, tzinfo=UTC)
