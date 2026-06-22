""" Test max coverage web for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from emailauto.core.states import OutboxStatus
from emailauto.recipients.suppression import suppress_email
from emailauto.web.views import _recent_outbox


@pytest.mark.django_db
def test_recent_outbox_helper(dispatched_row):
    rows = list(_recent_outbox(limit=5))
    assert any(row.id == dispatched_row.id for row in rows)


@pytest.mark.django_db
def test_health_deep_probe_ok(client, monkeypatch):
    class FakeRedis:
        def ping(self):
            return True

    monkeypatch.setattr("redis.from_url", lambda *_a, **_k: FakeRedis())
    response = client.get("/health/?deep=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cache"] is True
    assert payload["broker"] is True


@pytest.mark.django_db
def test_health_deep_degraded_on_cache_failure(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("cache down")

    monkeypatch.setattr("emailauto.web.views.cache.set", boom)
    response = client.get("/health/?deep=1")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.django_db
def test_health_deep_degraded_on_broker_failure(client, monkeypatch):
    class BrokenRedis:
        @staticmethod
        def from_url(*_args, **_kwargs):
            raise ConnectionError("no redis")

    monkeypatch.setattr("redis.from_url", BrokenRedis.from_url)
    response = client.get("/health/?deep=1")
    assert response.status_code == 503
    assert response.json()["broker"] is False


@pytest.mark.django_db
def test_health_deep_cache_get_mismatch(client, monkeypatch):
    monkeypatch.setattr("emailauto.web.views.cache.set", lambda *_a, **_k: True)
    monkeypatch.setattr("emailauto.web.views.cache.get", lambda *_a, **_k: None)
    response = client.get("/health/?deep=1")
    assert response.status_code == 503
    assert response.json()["cache"] is False


@pytest.mark.django_db
def test_remove_suppression_paths(auth_client):
    suppress_email("remove-me@example.com", reason="test")
    response = auth_client.post("/unsuppress/", {"email": ""})
    assert response.status_code == 302

    response = auth_client.post("/unsuppress/", {"email": "remove-me@example.com"})
    assert response.status_code == 302

    response = auth_client.post("/unsuppress/", {"email": "missing@example.com"})
    assert response.status_code == 302


@pytest.mark.django_db
def test_set_subscription_paths(auth_client, campaign_fixture):
    recipient = campaign_fixture["recipient"]
    response = auth_client.post("/subscription/", {"email": "", "action": "subscribe"})
    assert response.status_code == 302

    response = auth_client.post("/subscription/", {"email": recipient.email, "action": "bad"})
    assert response.status_code == 302

    response = auth_client.post("/subscription/", {"email": "unknown@example.com", "action": "subscribe"})
    assert response.status_code == 302

    response = auth_client.post("/subscription/", {"email": recipient.email, "action": "unsubscribe"})
    assert response.status_code == 302
    recipient.refresh_from_db()
    assert recipient.subscribed is False

    response = auth_client.post("/subscription/", {"email": recipient.email, "action": "subscribe"})
    assert response.status_code == 302
    recipient.refresh_from_db()
    assert recipient.subscribed is True


@pytest.mark.django_db
def test_operator_rate_limit_blocks_excess(auth_client, campaign_fixture, settings):
    settings.EMAILAUTO_OPERATOR_RATE_LIMIT = 1
    campaign = campaign_fixture["campaign"]
    auth_client.post(f"/campaigns/{campaign.id}/pause/")
    response = auth_client.post(f"/campaigns/{campaign.id}/resume/")
    assert response.status_code == 302
    assert response.url == reverse("emailauto:dashboard")


@pytest.mark.django_db
def test_dashboard_and_schedules_pagination(auth_client, campaign_fixture):
    assert auth_client.get("/?campaign_page=1&outbox_page=1").status_code == 200
    assert auth_client.get("/schedules/?page=1").status_code == 200


@pytest.mark.django_db
def test_outbox_detail_action_flags(auth_client, dispatched_row):
    dispatched_row.status = OutboxStatus.FAILED
    dispatched_row.save(update_fields=["status"])
    response = auth_client.get(f"/outbox/{dispatched_row.id}/")
    assert response.status_code == 200
    assert b"Retry" in response.content or b"retry" in response.content.lower()


@pytest.mark.django_db
def test_campaign_action_runtime_error(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    with patch("emailauto.web.views.trigger_campaign_now", side_effect=RuntimeError("boom")):
        response = auth_client.post(f"/campaigns/{campaign.id}/trigger/")
    assert response.status_code == 302
