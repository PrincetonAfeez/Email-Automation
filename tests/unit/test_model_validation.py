from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.scheduling.models import CampaignSchedule
from emailauto.templates.models import EmailTemplate


@pytest.mark.django_db
def test_one_time_schedule_requires_send_at(campaign_fixture):
    with pytest.raises(ValidationError):
        CampaignSchedule.objects.create(
            campaign=campaign_fixture["campaign"],
            schedule_type=ScheduleType.ONE_TIME,
        )


@pytest.mark.django_db
def test_recurring_schedule_requires_cron_or_interval(campaign_fixture):
    with pytest.raises(ValidationError):
        CampaignSchedule.objects.create(
            campaign=campaign_fixture["campaign"],
            schedule_type=ScheduleType.RECURRING,
            send_at=timezone.now(),
        )


@pytest.mark.django_db
def test_template_required_variables_must_be_strings():
    with pytest.raises(ValidationError):
        EmailTemplate.objects.create(
            name="bad-template",
            subject_template="s",
            body_template="b",
            required_variables=[123],
        )


@pytest.mark.django_db
def test_template_update_is_also_validated(campaign_fixture):
    template = campaign_fixture["template"]
    template.required_variables = "notalist"  # invalid on update, not only on create
    with pytest.raises(ValidationError):
        template.save()


@pytest.mark.django_db
def test_schedule_update_with_malformed_cron_is_rejected(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        send_at=timezone.now(),
        cron_expression="0 9 * * MON",
    )
    schedule.cron_expression = "0 9 * * NOPE"
    with pytest.raises(ValidationError):
        schedule.save()


@pytest.mark.django_db
def test_schedule_local_display_converts_to_named_timezone(campaign_fixture):
    try:
        ZoneInfo("America/New_York")
    except Exception:  # pragma: no cover - tzdata not installed
        pytest.skip("tzdata not available")

    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        timezone_name="America/New_York",
    )

    local = schedule.next_run_at_local
    assert local is not None
    assert local.hour == 8  # 12:00 UTC is 08:00 EDT in July
    assert local.utcoffset().total_seconds() == -4 * 3600
