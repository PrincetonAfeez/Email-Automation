from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

import emailauto.scheduling.dispatcher as dispatcher_module
from emailauto.core.states import ScheduleType
from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule
from emailauto.scheduling.recurrence import next_cron_after


@pytest.mark.django_db
def test_one_failing_schedule_does_not_block_the_tick(campaign_fixture, monkeypatch):
    campaign = campaign_fixture["campaign"]
    bad = CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now() - timedelta(minutes=1),  # sorts first
    )
    CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    real = dispatcher_module.create_run_and_outbox

    def flaky(schedule, **kwargs):
        if schedule.id == bad.id:
            raise RuntimeError("boom")
        return real(schedule, **kwargs)

    monkeypatch.setattr(dispatcher_module, "create_run_and_outbox", flaky)

    summary = dispatcher_module.dispatch_due_schedules()

    # The healthy schedule still produced its row despite the other raising mid-tick.
    assert EmailOutbox.objects.filter(campaign=campaign).count() == 1
    assert summary.outbox_created == 1


@pytest.mark.django_db
def test_malformed_cron_is_rejected_at_creation(campaign_fixture):
    with pytest.raises(ValidationError):
        CampaignSchedule.objects.create(
            campaign=campaign_fixture["campaign"],
            schedule_type=ScheduleType.RECURRING,
            send_at=timezone.now(),
            cron_expression="0 9 * * FUNKY",
        )


def test_next_cron_after_resolves_leap_day():
    # A Feb-29 cron's next occurrence is years out; it must resolve, not raise.
    start = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert next_cron_after(start, "0 0 29 2 *") == datetime(2028, 2, 29, 0, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_impossible_date_cron_fires_once_then_disables(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    # "0 0 30 2 *" is syntactically valid but Feb 30 never exists.
    schedule = CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.RECURRING,
        send_at=timezone.now() - timedelta(minutes=1),
        cron_expression="0 0 30 2 *",
    )

    dispatch_due_schedules()

    schedule.refresh_from_db()
    # The explicitly-scheduled first occurrence still fired (rows not rolled back)...
    assert EmailOutbox.objects.filter(campaign=campaign).count() == 1
    # ...and the schedule is disabled because no next occurrence exists in the horizon.
    assert schedule.enabled is False
