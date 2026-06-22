""" Test render context for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.templates.renderer import render_template


@pytest.mark.django_db
def test_custom_fields_cannot_shadow_reserved_keys(campaign_fixture):
    recipient = campaign_fixture["recipient"]
    # A malicious/clumsy custom field tries to override the campaign context.
    recipient.custom_fields = {"first_name": "Ada", "campaign": "HACK"}
    recipient.save()

    rendered = render_template(
        email_template=campaign_fixture["template"],
        recipient=recipient,
        campaign=campaign_fixture["campaign"],
        idempotency_key="k",
    )

    # {{ campaign.name }} still resolves to the real campaign, not the custom field.
    assert "Launch" in rendered.body
    assert "HACK" not in rendered.body


@pytest.mark.django_db
def test_custom_fields_remain_available_top_level_and_under_fields(campaign_fixture):
    rendered = render_template(
        email_template=campaign_fixture["template"],
        recipient=campaign_fixture["recipient"],
        campaign=campaign_fixture["campaign"],
        idempotency_key="k",
    )
    # The fixture body uses {{ first_name }} (a top-level custom field).
    assert "Hello Ada" in rendered.body
