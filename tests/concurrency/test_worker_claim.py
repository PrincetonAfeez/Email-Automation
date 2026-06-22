""" Test worker claim for EmailAuto."""

from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.core.exceptions import StaleClaimToken
from emailauto.core.states import OutboxStatus, ScheduleType
from emailauto.outbox.claim import claim_outbox
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.transitions import transition_outbox
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_two_workers_racing_one_row_produce_one_claim(campaign_fixture):
    CampaignSchedule.objects.create(campaign=campaign_fixture["campaign"], schedule_type=ScheduleType.ONE_TIME, send_at=timezone.now())
    dispatch_due_schedules()
    row = EmailOutbox.objects.get()

    first = claim_outbox(row.id, worker_id="w1", celery_task_id="task-1")
    second = claim_outbox(row.id, worker_id="w2", celery_task_id="task-2")

    assert first is not None
    assert second is None


@pytest.mark.django_db
def test_stale_claim_token_cannot_mark_sent(campaign_fixture):
    CampaignSchedule.objects.create(campaign=campaign_fixture["campaign"], schedule_type=ScheduleType.ONE_TIME, send_at=timezone.now())
    dispatch_due_schedules()
    row = EmailOutbox.objects.get()
    claim = claim_outbox(row.id, worker_id="w1", celery_task_id="task-1")
    assert claim is not None
    transition_outbox(row.id, OutboxStatus.SENDING, claim_token=claim.token)

    with pytest.raises(StaleClaimToken):
        transition_outbox(row.id, OutboxStatus.SENT, claim_token="stale")

