""" Test duplicate dispatch for EmailAuto."""

from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.outbox.models import EmailOutbox
from emailauto.recipients.models import Recipient
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignRun, CampaignSchedule


@pytest.mark.django_db
def test_repeated_dispatch_creates_one_row_per_recipient(campaign_fixture):
    recipient_list = campaign_fixture["recipient_list"]
    for index in range(3):
        recipient_list.recipients.add(Recipient.objects.create(email=f"dup{index}@example.com"))

    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    first = dispatch_due_schedules()
    second = dispatch_due_schedules()

    assert first.outbox_created == 4  # fixture recipient + 3
    assert second.outbox_created == 0
    assert CampaignRun.objects.count() == 1
    assert EmailOutbox.objects.count() == 4
