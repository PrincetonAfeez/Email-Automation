""" Test operator permission for EmailAuto."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_operator_actions_require_permission(client, campaign_fixture, django_user_model):
    django_user_model.objects.create_user(username="viewer", password="pw")
    client.login(username="viewer", password="pw")
    campaign = campaign_fixture["campaign"]

    response = client.post(f"/campaigns/{campaign.id}/cancel/")

    assert response.status_code == 403
    campaign.refresh_from_db()
    assert campaign.status == "scheduled"
