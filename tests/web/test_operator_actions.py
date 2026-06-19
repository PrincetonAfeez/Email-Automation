from __future__ import annotations

import pytest

from emailauto.core.results import SendResult
from emailauto.core.states import CampaignStatus, OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import send_outbox_email
from emailauto.recipients.models import SuppressionEntry


@pytest.mark.django_db
def test_pause_resume_cancel_campaign(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]

    assert auth_client.post(f"/campaigns/{campaign.id}/pause/").status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.PAUSED

    auth_client.post(f"/campaigns/{campaign.id}/resume/")
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED

    auth_client.post(f"/campaigns/{campaign.id}/cancel/")
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.CANCELLED


@pytest.mark.django_db
def test_trigger_campaign_creates_outbox(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]

    response = auth_client.post(f"/campaigns/{campaign.id}/trigger/")

    assert response.status_code == 302
    assert EmailOutbox.objects.filter(campaign=campaign).count() == 1


@pytest.mark.django_db
def test_add_suppression_normalises_email(auth_client, campaign_fixture):
    response = auth_client.post("/suppress/", {"email": "Block@Example.com", "reason": "operator"})

    assert response.status_code == 302
    assert SuppressionEntry.objects.filter(email="block@example.com").exists()


@pytest.mark.django_db
def test_requeue_dlq_action(auth_client, dispatched_row):
    dispatched_row.max_attempts = 1
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "temporary"))
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.DEAD_LETTERED

    response = auth_client.post(f"/dlq/{dispatched_row.id}/requeue/")

    assert response.status_code == 302
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.REQUEUED


@pytest.mark.django_db
def test_outbox_cancel_action(auth_client, dispatched_row):
    response = auth_client.post(f"/outbox/{dispatched_row.id}/cancel/")

    assert response.status_code == 302
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.CANCELLED


@pytest.mark.django_db
def test_requeue_dlq_rejects_get(auth_client, dispatched_row):
    # Operator actions are POST-only (and login-protected; auth_client passes the login gate).
    assert auth_client.get(f"/dlq/{dispatched_row.id}/requeue/").status_code == 405


@pytest.mark.django_db
def test_operator_actions_require_login(client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    response = client.post(f"/campaigns/{campaign.id}/cancel/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.headers["Location"]
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED  # unchanged — action never ran


@pytest.mark.django_db
def test_open_redirect_is_blocked(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    response = auth_client.post(f"/campaigns/{campaign.id}/pause/", {"next": "https://evil.example.com/x"})
    # The malicious absolute URL is rejected; we fall back to the dashboard.
    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]
