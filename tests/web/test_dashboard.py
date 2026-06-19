from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_dashboard_renders(auth_client):
    response = auth_client.get("/")

    assert response.status_code == 200
    assert b"Outbox Stats" in response.content


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    # Anonymous users are redirected to the login page, not served the dashboard.
    response = client.get("/")

    assert response.status_code == 302
    assert "/accounts/login/" in response.headers["Location"]
