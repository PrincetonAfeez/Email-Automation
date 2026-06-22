""" Test large campaign batches for EmailAuto."""

from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.outbox.models import EmailOutbox
from emailauto.recipients.models import Recipient
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_every_recipient_gets_a_row_across_bounded_batches(campaign_fixture):
    # 6 recipients total (1 from the fixture + 5 more).
    recipient_list = campaign_fixture["recipient_list"]
    for index in range(5):
        recipient = Recipient.objects.create(email=f"batch{index}@example.com", name=f"Batch {index}")
        recipient_list.recipients.add(recipient)

    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    # batch_size=2 forces the occurrence to be materialised over several ticks.
    ticks = 0
    while ticks < 10:
        dispatch_due_schedules(batch_size=2)
        ticks += 1
        schedule.refresh_from_db()
        if not schedule.enabled:
            break

    assert EmailOutbox.objects.filter(campaign=campaign_fixture["campaign"]).count() == 6
    assert schedule.enabled is False  # only disabled once the whole occurrence exists


@pytest.mark.django_db
def test_partial_batch_keeps_schedule_due(campaign_fixture):
    recipient_list = campaign_fixture["recipient_list"]
    for index in range(3):
        recipient_list.recipients.add(Recipient.objects.create(email=f"more{index}@example.com"))

    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )

    dispatch_due_schedules(batch_size=2)  # 4 recipients, only 2 created so far

    schedule.refresh_from_db()
    assert schedule.enabled is True  # not advanced yet
    assert EmailOutbox.objects.filter(campaign=campaign_fixture["campaign"]).count() == 2
