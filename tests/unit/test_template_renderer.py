from __future__ import annotations

import pytest

from emailauto.core.exceptions import MissingTemplateVariable
from emailauto.templates.renderer import render_template


@pytest.mark.django_db
def test_template_renderer_renders_required_context(campaign_fixture):
    rendered = render_template(
        email_template=campaign_fixture["template"],
        recipient=campaign_fixture["recipient"],
        campaign=campaign_fixture["campaign"],
        idempotency_key="key",
    )

    assert rendered.subject == "Hi Person"
    assert "Hello Ada" in rendered.body
    assert rendered.to_email == "person@example.com"


@pytest.mark.django_db
def test_template_renderer_rejects_missing_required_variable(campaign_fixture):
    recipient = campaign_fixture["recipient"]
    recipient.custom_fields = {}
    recipient.save()

    with pytest.raises(MissingTemplateVariable):
        render_template(
            email_template=campaign_fixture["template"],
            recipient=recipient,
            campaign=campaign_fixture["campaign"],
            idempotency_key="key",
        )

