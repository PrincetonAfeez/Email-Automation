""" Test concurrent claim for EmailAuto."""

from __future__ import annotations

import threading

import pytest
from django.db import OperationalError, connection
from django.utils import timezone

from emailauto.campaigns.models import Campaign
from emailauto.core.states import CampaignStatus, OutboxStatus, ScheduleType
from emailauto.outbox.claim import claim_outbox
from emailauto.outbox.models import EmailOutbox
from emailauto.recipients.models import Recipient, RecipientList
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule
from emailauto.templates.models import EmailTemplate


@pytest.mark.django_db(transaction=True)
def test_two_threads_racing_one_row_produce_exactly_one_claim():
    # transaction=True (committed data) so the worker threads see the row on their own
    # connections — a genuine race, not the sequential simulation in test_worker_claim.
    template = EmailTemplate.objects.create(name="race-tpl", subject_template="Hi {{ recipient.name }}", body_template="B")
    recipient = Recipient.objects.create(email="race@example.com", name="Race")
    recipient_list = RecipientList.objects.create(name="race-list")
    recipient_list.recipients.add(recipient)
    campaign = Campaign.objects.create(name="race-campaign", template=template, recipient_list=recipient_list, status=CampaignStatus.SCHEDULED)
    CampaignSchedule.objects.create(campaign=campaign, schedule_type=ScheduleType.ONE_TIME, send_at=timezone.now())
    dispatch_due_schedules()
    row_id = EmailOutbox.objects.get().id

    results: dict[int, bool] = {}
    barrier = threading.Barrier(2)

    def worker(idx: int) -> None:
        barrier.wait()  # release both threads together to maximise contention
        try:
            claim = claim_outbox(row_id, worker_id=f"w{idx}")
            results[idx] = claim is not None
        except OperationalError:
            results[idx] = False  # a lock failure is still "did not claim" — invariant holds
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Exactly one winner, and the row really is claimed.
    assert sum(1 for won in results.values() if won) == 1
    assert EmailOutbox.objects.get(pk=row_id).status == OutboxStatus.CLAIMED

    EmailOutbox.objects.all().delete()  # transactional test: clean up explicitly
    CampaignSchedule.objects.all().delete()
    Campaign.objects.all().delete()
    RecipientList.objects.all().delete()
    Recipient.objects.all().delete()
    EmailTemplate.objects.all().delete()
