""" Test polish fixes for EmailAuto."""

from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.campaigns.services import trigger_campaign_now
from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus
from emailauto.outbox.services import _finish_result, force_requeue_outbox
from emailauto.recipients.subscription import set_recipient_subscribed


@pytest.mark.django_db
def test_finish_result_failed_after_midflight_release(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "worker-token"
    dispatched_row.locked_by = "worker"
    dispatched_row.locked_at = timezone.now()
    dispatched_row.save()
    force_requeue_outbox(dispatched_row.id, enqueue_celery=False)
    outcome = _finish_result(
        dispatched_row,
        "worker-token",
        SendResult.permanent_failure("fake", "bad", "bad"),
    )
    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.FAILED
    assert dispatched_row.status == OutboxStatus.FAILED


@pytest.mark.django_db
def test_finish_result_dead_letter_after_midflight_release(dispatched_row):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.claim_token = "worker-token"
    dispatched_row.attempt_count = 2
    dispatched_row.max_attempts = 3
    dispatched_row.save()
    force_requeue_outbox(dispatched_row.id, enqueue_celery=False)
    outcome = _finish_result(
        dispatched_row,
        "worker-token",
        SendResult.transient_failure("fake", "timeout", "timeout"),
    )
    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.DEAD_LETTERED
    assert dispatched_row.status == OutboxStatus.DEAD_LETTERED


@pytest.mark.django_db
def test_trigger_rejects_empty_recipient_list(campaign_fixture):
    campaign_fixture["recipient_list"].recipients.clear()
    with pytest.raises(ValueError, match="empty recipient list"):
        trigger_campaign_now(campaign_fixture["campaign"].id)


@pytest.mark.django_db
def test_set_recipient_subscribed(campaign_fixture):
    recipient = campaign_fixture["recipient"]
    set_recipient_subscribed(recipient.email, subscribed=False)
    recipient.refresh_from_db()
    assert recipient.subscribed is False
    set_recipient_subscribed(recipient.email, subscribed=True)
    recipient.refresh_from_db()
    assert recipient.subscribed is True


@pytest.mark.django_db
def test_outbox_partial_preserves_page_param(auth_client):
    response = auth_client.get("/partials/outbox/?outbox_page=1")
    assert response.status_code == 200
    assert "Recent Outbox Activity" in response.content.decode()
