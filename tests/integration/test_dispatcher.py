from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignRun, CampaignSchedule


@pytest.mark.django_db
def test_dispatcher_creates_run_and_idempotent_outbox(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    first = dispatch_due_schedules()
    second = dispatch_due_schedules()

    assert first.runs_created == 1
    assert first.outbox_created == 1
    assert second.outbox_created == 0
    assert CampaignRun.objects.count() == 1
    assert EmailOutbox.objects.count() == 1

