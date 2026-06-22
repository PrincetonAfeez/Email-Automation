""" Test audit fixes for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from emailauto.campaigns.services import trigger_campaign_now
from emailauto.core.states import CampaignRunStatus, CampaignStatus, OutboxStatus, assert_campaign_run_transition
from emailauto.outbox.models import EmailOutbox


@pytest.mark.django_db
def test_trigger_creates_new_run_on_each_call(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    first = trigger_campaign_now(campaign.id, enqueue_celery=False)
    second = trigger_campaign_now(campaign.id, enqueue_celery=False)
    assert first.run_id != second.run_id
    assert EmailOutbox.objects.filter(campaign=campaign).count() == 2


@pytest.mark.django_db
def test_trigger_rejects_paused_campaign(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.PAUSED
    campaign.save(update_fields=["status"])
    with pytest.raises(ValueError, match="Cannot trigger"):
        trigger_campaign_now(campaign.id)


@pytest.mark.django_db
def test_throttled_reschedule_clears_lock_fields(dispatched_row, settings):
    from emailauto.outbox.services import send_outbox_email
    from emailauto.workers.throttling import record_send

    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    record_send(campaign_id=dispatched_row.campaign_id)
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.locked_by == ""
    assert dispatched_row.claim_token == ""


def test_campaign_run_transition_table():
    assert_campaign_run_transition(CampaignRunStatus.OUTBOX_GENERATED, CampaignRunStatus.DISPATCHING)
    assert_campaign_run_transition(CampaignRunStatus.DISPATCHED, CampaignRunStatus.COMPLETED)


@pytest.mark.django_db
def test_health_deep_probe(client):
    with patch("redis.from_url") as redis_factory:
        redis_factory.return_value.ping.return_value = True
        response = client.get("/health/?deep=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cache"] is True
    assert payload["broker"] is True


@pytest.mark.django_db
def test_operator_action_audit_on_suppress(auth_client):
    from emailauto.outbox.models import EmailEventLog

    auth_client.post("/suppress/", {"email": "audit@example.com", "reason": "test"})
    assert EmailEventLog.objects.filter(event_type="operator_action", metadata__action="suppress").exists()
