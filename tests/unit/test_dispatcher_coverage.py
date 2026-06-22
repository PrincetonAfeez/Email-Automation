""" Test dispatcher coverage for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

import emailauto.scheduling.dispatcher as dispatcher_module
from emailauto.core.states import OutboxStatus, ScheduleType
from emailauto.scheduling.dispatcher import (
    enqueue_outbox_by_id,
    idempotency_key,
    republish_enqueued_row,
    run_key_for,
)
from emailauto.scheduling.models import CampaignSchedule


def test_idempotency_and_run_key_helpers():
    key = idempotency_key(campaign_id=1, campaign_run_id=2, recipient_id=3)
    assert "campaign:1" in key
    now = timezone.now()
    schedule = CampaignSchedule(id=5, schedule_type=ScheduleType.ONE_TIME)
    assert "schedule:5" in run_key_for(schedule, now)


@pytest.mark.django_db
def test_republish_enqueued_row_noop(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    assert republish_enqueued_row(dispatched_row.id) is False


@pytest.mark.django_db
def test_republish_enqueued_row_success(dispatched_row):
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = timezone.now()
    dispatched_row.save()
    with patch.object(dispatcher_module, "_publish_task", return_value=True):
        assert republish_enqueued_row(dispatched_row.id) is True


@pytest.mark.django_db
def test_enqueue_outbox_by_id_wrong_status(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    assert enqueue_outbox_by_id(dispatched_row.id, enqueue_celery=True) is False


@pytest.mark.django_db
def test_create_run_skip_locked_returns_none(campaign_fixture, monkeypatch):
    from emailauto.scheduling.dispatcher import create_run_and_outbox

    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    monkeypatch.setattr(
        "emailauto.scheduling.dispatcher.connection.features.has_select_for_update_skip_locked",
        True,
    )

    class FakeQS:
        def select_for_update(self, **kwargs):
            return self

        def select_related(self, *args):
            return self

        def filter(self, **kwargs):
            return self

        def first(self):
            return None

    monkeypatch.setattr(dispatcher_module.CampaignSchedule.objects, "select_for_update", lambda **kwargs: FakeQS())
    run, created, run_created = create_run_and_outbox(schedule)
    assert run is None and created == 0
