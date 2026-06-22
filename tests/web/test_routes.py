"""Route-by-route web coverage checklist (see docs/test_matrix.md)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages

from emailauto.core.states import CampaignStatus, OutboxStatus


def _flash_messages(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@pytest.fixture
def viewer_client(client, django_user_model):
    django_user_model.objects.create_user(username="viewer", password="pw")
    client.login(username="viewer", password="pw")
    return client


@pytest.mark.django_db
def test_route_health_get_returns_json_status(client):
    response = client.get("/health/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] is True


@pytest.mark.django_db
def test_route_health_deep_get_returns_json_probe_keys(client, monkeypatch):
    class FakeRedis:
        def ping(self):
            return True

    monkeypatch.setattr("redis.from_url", lambda *_args, **_kwargs: FakeRedis())
    response = client.get("/health/?deep=1")
    assert response.status_code in {200, 503}
    payload = response.json()
    assert "status" in payload
    assert "cache" in payload
    assert "broker" in payload


@pytest.mark.django_db
def test_route_dashboard_anonymous_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_route_dashboard_authenticated_returns_200(auth_client):
    assert auth_client.get("/").status_code == 200


@pytest.mark.django_db
def test_route_schedules_authenticated_returns_200(auth_client):
    assert auth_client.get("/schedules/").status_code == 200


@pytest.mark.django_db
def test_route_campaign_run_detail_existing_and_missing(auth_client, dispatched_row):
    run_id = dispatched_row.campaign_run_id
    assert auth_client.get(f"/runs/{run_id}/").status_code == 200
    assert auth_client.get("/runs/999999/").status_code == 404


@pytest.mark.django_db
def test_route_campaign_detail_existing_and_missing(auth_client, campaign_fixture):
    campaign_id = campaign_fixture["campaign"].id
    assert auth_client.get(f"/campaigns/{campaign_id}/").status_code == 200
    assert auth_client.get("/campaigns/999999/").status_code == 404


@pytest.mark.django_db
def test_route_campaign_trigger_requires_operator_permission(viewer_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    response = viewer_client.post(f"/campaigns/{campaign.id}/trigger/")
    assert response.status_code == 403
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED


@pytest.mark.django_db
def test_route_campaign_pause_rejects_invalid_state(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    response = auth_client.post(f"/campaigns/{campaign.id}/pause/", follow=True)
    assert response.status_code == 200
    assert any("Cannot pause" in message for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_campaign_resume_rejects_invalid_state(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    response = auth_client.post(f"/campaigns/{campaign.id}/resume/", follow=True)
    assert response.status_code == 200
    assert any("Cannot resume" in message for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_campaign_cancel_succeeds_for_cancellable_campaign(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    response = auth_client.post(f"/campaigns/{campaign.id}/cancel/")
    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.CANCELLED


@pytest.mark.django_db
def test_route_outbox_detail_existing_and_missing(auth_client, dispatched_row):
    assert auth_client.get(f"/outbox/{dispatched_row.id}/").status_code == 200
    assert auth_client.get("/outbox/999999/").status_code == 404


@pytest.mark.django_db
def test_route_outbox_retry_rejects_invalid_status(auth_client, dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    response = auth_client.post(f"/outbox/{dispatched_row.id}/retry/", follow=True)
    assert response.status_code == 200
    assert any("Cannot retry" in message for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_outbox_cancel_rejects_invalid_status(auth_client, dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    response = auth_client.post(f"/outbox/{dispatched_row.id}/cancel/", follow=True)
    assert response.status_code == 200
    assert any("can be cancelled" in message.lower() for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_outbox_force_requeue_rejects_invalid_status(auth_client, dispatched_row):
    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.save(update_fields=["status"])
    response = auth_client.post(f"/outbox/{dispatched_row.id}/force_requeue/", follow=True)
    assert response.status_code == 200
    assert any("Only claimed or sending" in message for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_dlq_list_returns_200(auth_client):
    assert auth_client.get("/dlq/").status_code == 200


@pytest.mark.django_db
def test_route_dlq_requeue_rejects_non_retriable_row(auth_client, dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    response = auth_client.post(f"/dlq/{dispatched_row.id}/requeue/", follow=True)
    assert response.status_code == 200
    assert any("Cannot retry" in message for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_suppress_rejects_missing_email(auth_client):
    response = auth_client.post("/suppress/", {"email": "", "reason": "test"}, follow=True)
    assert response.status_code == 200
    assert any("email address is required" in message.lower() for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_unsuppress_rejects_missing_email(auth_client):
    response = auth_client.post("/unsuppress/", {"email": ""}, follow=True)
    assert response.status_code == 200
    assert any("email address is required" in message.lower() for message in _flash_messages(response))


@pytest.mark.django_db
def test_route_subscription_rejects_missing_email_and_unknown_action(auth_client, campaign_fixture):
    recipient = campaign_fixture["recipient"]
    missing = auth_client.post("/subscription/", {"email": "", "action": "subscribe"}, follow=True)
    assert any("email address is required" in message.lower() for message in _flash_messages(missing))

    unknown = auth_client.post(
        "/subscription/",
        {"email": recipient.email, "action": "invalid"},
        follow=True,
    )
    assert any("unknown subscription action" in message.lower() for message in _flash_messages(unknown))


@pytest.mark.django_db
def test_route_partials_stats_returns_200(auth_client):
    assert auth_client.get("/partials/stats/").status_code == 200


@pytest.mark.django_db
def test_route_partials_outbox_returns_200(auth_client):
    assert auth_client.get("/partials/outbox/").status_code == 200


@pytest.mark.django_db
def test_route_partials_system_returns_200(auth_client):
    assert auth_client.get("/partials/system/").status_code == 200


@pytest.mark.django_db
def test_route_login_page_renders(client):
    assert client.get("/accounts/login/").status_code == 200


@pytest.mark.django_db
def test_route_logout_post_redirects_to_login(auth_client):
    response = auth_client.post("/accounts/logout/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_route_campaign_trigger_succeeds_with_operator(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    with patch("emailauto.web.views.trigger_campaign_now") as trigger:
        trigger.return_value = type("R", (), {"outbox_created": 1, "outbox_enqueued": 0})()
        response = auth_client.post(f"/campaigns/{campaign.id}/trigger/")
    assert response.status_code == 302
