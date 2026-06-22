""" Test web coverage for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from emailauto.core.states import OutboxStatus


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json()["database"] is True


@pytest.mark.django_db
def test_health_degraded_when_db_fails(client, monkeypatch):
    class BrokenCursor:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("db down")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "emailauto.web.views.connection.cursor",
        lambda: BrokenCursor(),
    )
    response = client.get("/health/")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.django_db
def test_safe_redirect_with_next(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    next_url = reverse("emailauto:campaign_detail", args=[campaign.id])
    response = auth_client.post(
        f"/campaigns/{campaign.id}/pause/",
        {"next": next_url},
    )
    assert response.status_code == 302
    assert response.url == next_url


@pytest.mark.django_db
def test_campaign_action_unknown_trigger_and_errors(auth_client, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    with patch("emailauto.web.views.pause_campaign", side_effect=ValueError("cannot pause")):
        response = auth_client.post(f"/campaigns/{campaign.id}/pause/")
    assert response.status_code == 302

    response = auth_client.post(f"/campaigns/{campaign.id}/unknown/")
    assert response.status_code == 302

    with patch("emailauto.web.views.trigger_campaign_now") as trigger:
        trigger.return_value = type("R", (), {"outbox_created": 2, "outbox_enqueued": 1})()
        response = auth_client.post(f"/campaigns/{campaign.id}/trigger/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_outbox_action_paths(auth_client, dispatched_row):
    row = dispatched_row
    row.status = OutboxStatus.FAILED
    row.save(update_fields=["status"])
    with patch("emailauto.web.views.retry_outbox", return_value=row):
        response = auth_client.post(f"/outbox/{row.id}/retry/")
    assert response.status_code == 302

    row.status = OutboxStatus.PENDING
    row.save(update_fields=["status"])
    response = auth_client.post(f"/outbox/{row.id}/cancel/")
    assert response.status_code == 302

    row.status = OutboxStatus.CLAIMED
    row.save(update_fields=["status"])
    with patch("emailauto.web.views.force_requeue_outbox", return_value=row):
        response = auth_client.post(f"/outbox/{row.id}/force_requeue/")
    assert response.status_code == 302

    response = auth_client.post(f"/outbox/{row.id}/unknown/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_outbox_action_error_message(auth_client, dispatched_row):
    with patch("emailauto.web.views.retry_outbox", side_effect=ValueError("nope")):
        response = auth_client.post(f"/outbox/{dispatched_row.id}/retry/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_requeue_dlq_success_and_error(auth_client, dispatched_row):
    dispatched_row.status = OutboxStatus.DEAD_LETTERED
    dispatched_row.save(update_fields=["status"])
    with patch("emailauto.web.views.retry_outbox", return_value=dispatched_row):
        response = auth_client.post(f"/dlq/{dispatched_row.id}/requeue/")
    assert response.status_code == 302

    with patch("emailauto.web.views.retry_outbox", side_effect=ValueError("bad")):
        response = auth_client.post(f"/dlq/{dispatched_row.id}/requeue/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_add_suppression_validation_and_success(auth_client):
    response = auth_client.post("/suppress/", {"email": "", "reason": "test"})
    assert response.status_code == 302

    response = auth_client.post("/suppress/", {"email": "blocked@example.com", "reason": "test"})
    assert response.status_code == 302


@pytest.mark.django_db
def test_stats_partial_invalid_campaign_id(auth_client):
    response = auth_client.get("/partials/stats/?campaign_id=not-a-number")
    assert response.status_code == 200


@pytest.mark.django_db
def test_partials_render(auth_client):
    assert auth_client.get("/partials/outbox/").status_code == 200
    assert auth_client.get("/partials/system/").status_code == 200


@pytest.mark.django_db
def test_dlq_and_detail_pages(auth_client, dispatched_row):
    assert auth_client.get("/dlq/").status_code == 200
    assert auth_client.get(f"/outbox/{dispatched_row.id}/").status_code == 200
    assert auth_client.get(f"/campaigns/{dispatched_row.campaign_id}/").status_code == 200
    assert auth_client.get(f"/runs/{dispatched_row.campaign_run_id}/").status_code == 200


@pytest.mark.django_db
def test_operator_rate_limit_cache_incr_fallback(auth_client, campaign_fixture, settings):
    settings.EMAILAUTO_OPERATOR_RATE_LIMIT = 5
    campaign = campaign_fixture["campaign"]

    class BrokenCache:
        def add(self, *_args, **_kwargs):
            return True

        def incr(self, *_args, **_kwargs):
            raise ValueError("missing")

        def set(self, *_args, **_kwargs):
            return True

    with patch("emailauto.web.decorators.cache", BrokenCache()):
        response = auth_client.post(f"/campaigns/{campaign.id}/pause/")
    assert response.status_code == 302
