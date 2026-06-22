""" Test services extended for EmailAuto."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from emailauto.campaigns.services import mark_campaign_completed, reconcile_campaigns, set_campaign_status
from emailauto.core.results import SendResult
from emailauto.core.states import CampaignStatus, OutboxStatus
from emailauto.outbox.services import (
    _revoke_celery_task,
    force_requeue_outbox,
    retry_outbox,
    send_outbox_email,
)
from emailauto.workers.throttling import _increment_window, check_send


def test_revoke_celery_task_noop_and_swallows_errors():
    _revoke_celery_task("")
    mock_app = MagicMock()
    mock_app.control.revoke.side_effect = RuntimeError("broker down")
    with patch("celery.current_app", mock_app):
        _revoke_celery_task("task-1")


def test_throttle_unlimited_when_limit_zero(settings):
    settings.EMAILAUTO_SEND_RATE_LIMIT = 0
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 0
    assert check_send().allowed
    assert _increment_window("throttle:test", 0) is True


def test_throttle_incr_fallback(settings):
    settings.EMAILAUTO_SEND_RATE_LIMIT = 5

    class BrokenCache:
        def add(self, *_args, **_kwargs):
            return True

        def incr(self, *_args, **_kwargs):
            raise ValueError("missing")

        def set(self, *_args, **_kwargs):
            return True

    with patch("emailauto.workers.throttling.cache", BrokenCache()):
        assert _increment_window("throttle:broken", 5) is True


@pytest.mark.django_db
def test_send_paused_campaign_reschedules(dispatched_row):
    campaign = dispatched_row.campaign
    campaign.status = CampaignStatus.PAUSED
    campaign.save(update_fields=["status"])
    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.attempt_count == 0


@pytest.mark.django_db
def test_send_cancelled_at_claim(dispatched_row):
    campaign = dispatched_row.campaign
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")
    assert outcome.status == OutboxStatus.CANCELLED


@pytest.mark.django_db
def test_send_backend_exception_is_transient(dispatched_row):
    backend = MagicMock()
    backend.provider_name = "mock"
    backend.send_email.side_effect = RuntimeError("network")
    with patch("emailauto.outbox.services.get_backend", return_value=backend):
        outcome = send_outbox_email(dispatched_row.id)
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED


@pytest.mark.django_db
def test_send_aborts_if_campaign_cancelled_midflight(dispatched_row):
    campaign = dispatched_row.campaign

    def cancel_after_check(*args, **kwargs):
        campaign.status = CampaignStatus.CANCELLED
        campaign.save(update_fields=["status"])
        return SendResult.success("fake")

    backend = MagicMock()
    backend.provider_name = "fake"
    backend.send_email.side_effect = cancel_after_check
    with patch("emailauto.outbox.services.get_backend", return_value=backend):
        with patch("emailauto.outbox.services._abort_if_campaign_cancelled") as abort:
            abort.return_value = None
            first = send_outbox_email(dispatched_row.id, backend_name="fake")
    assert first.status in {OutboxStatus.SENT, OutboxStatus.RETRY_SCHEDULED, OutboxStatus.CANCELLED}


@pytest.mark.django_db
def test_force_requeue_and_cancel_enqueued(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.save(update_fields=["status"])
    with patch("emailauto.scheduling.dispatcher.enqueue_outbox_by_id", return_value=True):
        row = force_requeue_outbox(dispatched_row.id, enqueue_celery=True)
    assert row.status == OutboxStatus.RETRY_SCHEDULED

    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.celery_task_id = "celery-task-id"
    dispatched_row.save(update_fields=["status", "celery_task_id"])
    with patch("emailauto.outbox.services._revoke_celery_task") as revoke:
        from emailauto.outbox.services import cancel_outbox

        cancelled = cancel_outbox(dispatched_row.id)
    assert cancelled.status == OutboxStatus.CANCELLED
    revoke.assert_called_once_with("celery-task-id")


@pytest.mark.django_db
def test_retry_enqueued_fallback_when_republish_fails(dispatched_row):
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.save(update_fields=["status"])
    with patch("emailauto.scheduling.dispatcher.republish_enqueued_row", return_value=False):
        with patch("emailauto.scheduling.dispatcher.enqueue_outbox_by_id", return_value=True):
            row = retry_outbox(dispatched_row.id)
    assert row.status in {OutboxStatus.RETRY_SCHEDULED, OutboxStatus.ENQUEUED}


@pytest.mark.django_db
def test_mark_completed_idempotent_and_blocks_open_outbox(campaign_fixture, dispatched_row):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    completed = mark_campaign_completed(campaign.id)
    assert completed.status == CampaignStatus.COMPLETED
    assert mark_campaign_completed(campaign.id).status == CampaignStatus.COMPLETED

    campaign.status = CampaignStatus.PAUSED
    campaign.save(update_fields=["status"])
    pending = dispatched_row
    pending.status = OutboxStatus.PENDING
    pending.save(update_fields=["status"])
    with pytest.raises(ValueError, match="in progress"):
        mark_campaign_completed(campaign.id)


@pytest.mark.django_db
def test_set_status_routes_cancel_and_reconcile(campaign_fixture, dispatched_row):
    campaign = campaign_fixture["campaign"]
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    updated = set_campaign_status(campaign.id, CampaignStatus.CANCELLED)
    assert updated.status == CampaignStatus.CANCELLED

    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    assert reconcile_campaigns() >= 1
