""" Test renderer coverage for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.core.exceptions import MissingTemplateVariable, TemplateRenderError
from emailauto.templates.models import EmailTemplate
from emailauto.templates.renderer import TemplateSnapshot, build_render_context, render_template, validate_required_variables


@pytest.mark.django_db
def test_template_snapshot_from_outbox(dispatched_row):
    snap = TemplateSnapshot.from_outbox(dispatched_row)
    assert snap.subject_template
    assert isinstance(snap.required_variables, list)


@pytest.mark.django_db
def test_build_render_context_extra_and_shadowing(campaign_fixture, dispatched_row):
    recipient = campaign_fixture["recipient"]
    recipient.custom_fields = {"first_name": "Ada", "campaign": "shadow"}
    context = build_render_context(
        recipient=recipient,
        campaign=campaign_fixture["campaign"],
        campaign_run=dispatched_row.campaign_run,
        extra={"custom": "value"},
    )
    assert context["campaign"]["name"] == campaign_fixture["campaign"].name
    assert context["custom"] == "value"


@pytest.mark.django_db
def test_render_template_syntax_and_empty_subject(campaign_fixture):
    template = EmailTemplate.objects.create(
        name="Bad",
        subject_template="{% if %}",
        body_template="Body",
    )
    with pytest.raises(TemplateRenderError):
        render_template(
            email_template=template,
            recipient=campaign_fixture["recipient"],
            campaign=campaign_fixture["campaign"],
            idempotency_key="k",
        )

    template.subject_template = "   "
    template.body_template = "Body"
    template.save()
    with pytest.raises(TemplateRenderError, match="empty"):
        render_template(
            email_template=template,
            recipient=campaign_fixture["recipient"],
            campaign=campaign_fixture["campaign"],
            idempotency_key="k",
        )


@pytest.mark.django_db
def test_validate_required_variables_missing(campaign_fixture):
    template = EmailTemplate.objects.create(
        name="Req",
        subject_template="Hi",
        body_template="Body",
        required_variables=["missing.field"],
    )
    context = build_render_context(
        recipient=campaign_fixture["recipient"],
        campaign=campaign_fixture["campaign"],
    )
    with pytest.raises(MissingTemplateVariable):
        validate_required_variables(template, context)
