""" Test auth and partials for EmailAuto."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_stats_partial_ignores_malformed_campaign_id(auth_client):
    # A bad ?campaign_id must degrade to global stats, not 500.
    response = auth_client.get("/partials/stats/?campaign_id=abc")
    assert response.status_code == 200


@pytest.mark.django_db
def test_non_staff_operator_can_log_in_and_use_dashboard(client, django_user_model):
    # Any active user can view the dashboard; mutations require operate_campaign permission.
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from emailauto.campaigns.models import Campaign

    user = django_user_model.objects.create_user(username="operator", password="pw", is_staff=False)
    content_type = ContentType.objects.get_for_model(Campaign)
    permission = Permission.objects.get(content_type=content_type, codename="operate_campaign")
    user.user_permissions.add(permission)

    login = client.post("/accounts/login/", {"username": "operator", "password": "pw"})
    assert login.status_code == 302  # authenticated -> redirected to dashboard

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert b"Outbox Stats" in dashboard.content


@pytest.mark.django_db
def test_logout_requires_post_and_redirects(auth_client):
    response = auth_client.post("/accounts/logout/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.headers["Location"]
