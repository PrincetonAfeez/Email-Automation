""" Test max coverage outbox for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from emailauto.core.exceptions import InvalidStateTransition, StaleClaimToken
from emailauto.core.results import SendResult
from emailauto.core.states import CampaignRunStatus, OutboxStatus
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import (
    _cancel_inflight_outbox,
    _finish_result,
    bulk_cancel_open_outbox,
    cancel_outbox,
    force_requeue_outbox,
    release_stale_outbox,
)
from emailauto.outbox.transitions import enqueue_outbox_row


@pytest.mark.django_db
def test_finish_result_success_stale_claim_fallback(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "token"
    dispatched_row.save()
    with patch("emailauto.outbox.services._mark_sent_after_delivery", side_effect=StaleClaimToken("stale")):
        outcome = _finish_result(dispatched_row, "token", SendResult.success("fake"))
    assert outcome.status == OutboxStatus.SENT


@pytest.mark.django_db
def test_finish_result_failure_stale_claim_fallback(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "token"
    dispatched_row.save()
    with patch(
        "emailauto.outbox.services._transition_after_send_attempt",
        side_effect=InvalidStateTransition("bad"),
    ):
        outcome = _finish_result(
            dispatched_row,
            "token",
            SendResult.permanent_failure("fake", "bad", "bad"),
        )
    assert outcome.status == OutboxStatus.FAILED


@pytest.mark.django_db
def test_finish_result_dead_letter_stale_claim_fallback(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "token"
    dispatched_row.attempt_count = 2
    dispatched_row.max_attempts = 3
    dispatched_row.save()
    with patch(
        "emailauto.outbox.services._transition_after_send_attempt",
        side_effect=InvalidStateTransition("bad"),
    ):
        outcome = _finish_result(
            dispatched_row,
            "token",
            SendResult.transient_failure("fake", "timeout", "timeout"),
        )
    assert outcome.status == OutboxStatus.DEAD_LETTERED


@pytest.mark.django_db
def test_finish_result_retry_stale_claim_fallback(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "token"
    dispatched_row.attempt_count = 0
    dispatched_row.max_attempts = 3
    dispatched_row.save()
    with patch(
        "emailauto.outbox.services._transition_after_send_attempt",
        side_effect=InvalidStateTransition("bad"),
    ):
        outcome = _finish_result(
            dispatched_row,
            "token",
            SendResult.transient_failure("fake", "timeout", "timeout"),
        )
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED


@pytest.mark.django_db
def test_release_stale_revokes_celery_task(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.celery_task_id = "task-456"
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()
    with patch("emailauto.outbox.services._revoke_celery_task") as revoke:
        release_stale_outbox(dispatched_row.id, reason="stale")
    revoke.assert_called_once_with("task-456")


@pytest.mark.django_db
def test_force_requeue_invalid_status(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    with pytest.raises(ValueError, match="Only claimed or sending"):
        force_requeue_outbox(dispatched_row.id, enqueue_celery=False)


@pytest.mark.django_db
def test_force_requeue_enqueues_celery(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()
    with patch("emailauto.scheduling.dispatcher.enqueue_outbox_by_id") as enqueue:
        force_requeue_outbox(dispatched_row.id, enqueue_celery=True)
    enqueue.assert_called_once()


@pytest.mark.django_db
def test_cancel_enqueued_revokes_task(dispatched_row):
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.celery_task_id = "task-789"
    dispatched_row.save()
    with patch("emailauto.outbox.services._revoke_celery_task") as revoke:
        cancel_outbox(dispatched_row.id)
    revoke.assert_called_once_with("task-789")


@pytest.mark.django_db
def test_cancel_inflight_outbox(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.celery_task_id = "task-inflight"
    dispatched_row.save()
    with patch("emailauto.outbox.services._revoke_celery_task") as revoke:
        updated = _cancel_inflight_outbox(dispatched_row.id, last_error="campaign is cancelled")
    assert updated.status == OutboxStatus.CANCELLED
    revoke.assert_called_once_with("task-inflight")


@pytest.mark.django_db
def test_bulk_cancel_skips_errors(dispatched_row, monkeypatch):
    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.save(update_fields=["status"])
    with patch("emailauto.outbox.services.cancel_outbox", side_effect=ValueError("gone")):
        assert bulk_cancel_open_outbox(dispatched_row.campaign_id) == 0


@pytest.mark.django_db
def test_enqueue_outbox_row_missing_raises():

    with pytest.raises(EmailOutbox.DoesNotExist):
        enqueue_outbox_row(999999)


@pytest.mark.django_db
def test_enqueue_marks_run_dispatching(dispatched_row):

    run = dispatched_row.campaign_run
    run.status = CampaignRunStatus.OUTBOX_GENERATED
    run.save(update_fields=["status"])
    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.save(update_fields=["status"])
    enqueue_outbox_row(dispatched_row.id, celery_task_id="cid")
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.DISPATCHING


@pytest.mark.django_db
def test_bulk_cancel_inflight_row(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()
    cancelled = bulk_cancel_open_outbox(dispatched_row.campaign_id)
    assert cancelled >= 1
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.CANCELLED
