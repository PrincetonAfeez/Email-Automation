from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from emailauto.core.states import ScheduleType
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_all_display_routes_render(auth_client, dispatched_row):
    run = dispatched_row.campaign_run
    paths = [
        "/",
        "/schedules/",
        "/dlq/",
        "/partials/outbox/",
        "/partials/system/",
        "/partials/stats/",
        f"/campaigns/{dispatched_row.campaign_id}/",
        f"/outbox/{dispatched_row.id}/",
        f"/runs/{run.id}/",
    ]
    for path in paths:
        assert auth_client.get(path).status_code == 200, path


@pytest.mark.django_db
def test_run_page_shows_per_run_stats(auth_client, dispatched_row):
    response = auth_client.get(f"/runs/{dispatched_row.campaign_run_id}/")
    assert response.status_code == 200
    assert b"Per-run stats" in response.content


@pytest.mark.django_db
def test_system_panel_reports_rate_limit_status(auth_client):
    response = auth_client.get("/partials/system/")
    assert response.status_code == 200
    assert b"rate-limit status" in response.content


@pytest.mark.django_db
def test_schedules_page_lists_enabled_schedule(auth_client, campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        send_at=timezone.now() + timedelta(days=1),
        cron_expression="0 9 * * MON",
    )
    response = auth_client.get("/schedules/")
    assert response.status_code == 200
    assert b"0 9 * * MON" in response.content


@pytest.mark.django_db
def test_missing_outbox_returns_404_not_500(auth_client):
    assert auth_client.get("/outbox/999999/").status_code == 404


@pytest.mark.django_db
def test_missing_run_returns_404_not_500(auth_client):
    assert auth_client.get("/runs/999999/").status_code == 404
