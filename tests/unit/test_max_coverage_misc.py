""" Test max coverage misc for EmailAuto."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib import admin

from emailauto.campaigns.admin import CampaignAdmin, pause_campaigns, resume_campaigns
from emailauto.campaigns.models import Campaign
from emailauto.core.exceptions import InvalidStateTransition, MissingTemplateVariable
from emailauto.core.states import CampaignRunStatus, CampaignStatus, assert_campaign_run_transition
from emailauto.outbox.models import EmailEventLog, EmailSendAttempt
from emailauto.recipients.models import Recipient, SuppressionEntry
from emailauto.recipients.subscription import set_recipient_subscribed
from emailauto.scheduling.admin import CampaignScheduleAdmin
from emailauto.scheduling.models import CampaignRun, CampaignSchedule
from emailauto.scheduling.run_transitions import bulk_cancel_runs, transition_campaign_run, transition_campaign_run_by_id
from emailauto.templates.models import EmailTemplate
from emailauto.templates.renderer import build_render_context, validate_required_variables


@pytest.mark.django_db
def test_model_str_representations(campaign_fixture, dispatched_row):
    assert "@" in str(dispatched_row.recipient)
    assert str(campaign_fixture["recipient_list"])
    assert str(campaign_fixture["template"])
    assert "[" in str(dispatched_row)
    attempt = EmailSendAttempt.objects.create(
        outbox=dispatched_row,
        attempt_number=1,
        provider_name="fake",
        started_at=dispatched_row.updated_at,
        result="success",
    )
    assert "attempt" in str(attempt)
    event = EmailEventLog.objects.create(event_type="sent", outbox=dispatched_row)
    assert "sent" in str(event)
    entry = SuppressionEntry.objects.create(email="x@example.com", reason="test")
    assert "x@example.com" in str(entry)


@pytest.mark.django_db
def test_recipient_email_normalization():
    recipient = Recipient.objects.create(email="  Mixed@Example.COM  ", name="Mix")
    assert recipient.email == "mixed@example.com"


@pytest.mark.django_db
def test_set_recipient_subscribed_missing_raises():
    with pytest.raises(ValueError, match="No recipient found"):
        set_recipient_subscribed("nobody@example.com", subscribed=True)


@pytest.mark.django_db
def test_illegal_campaign_run_transition():
    with pytest.raises(InvalidStateTransition):
        assert_campaign_run_transition(CampaignRunStatus.COMPLETED, CampaignRunStatus.DISPATCHING)


@pytest.mark.django_db
def test_run_transition_noop_and_by_id(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type="one_time",
        send_at=campaign_fixture["now"],
    )
    run = CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key="noop-run",
        scheduled_for=campaign_fixture["now"],
        status=CampaignRunStatus.OUTBOX_GENERATED,
    )
    same = transition_campaign_run(run, CampaignRunStatus.OUTBOX_GENERATED)
    assert same.id == run.id
    updated = transition_campaign_run_by_id(run.id, CampaignRunStatus.DISPATCHING)
    assert updated.status == CampaignRunStatus.DISPATCHING


@pytest.mark.django_db
def test_bulk_cancel_runs_skips_terminal(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type="one_time",
        send_at=campaign_fixture["now"],
    )
    open_run = CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key="open-run",
        scheduled_for=campaign_fixture["now"],
        status=CampaignRunStatus.DISPATCHING,
    )
    CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key="done-run",
        scheduled_for=campaign_fixture["now"] + timedelta(hours=1),
        status=CampaignRunStatus.COMPLETED,
    )
    cancelled = bulk_cancel_runs(campaign_fixture["campaign"].id, open_statuses={CampaignRunStatus.DISPATCHING})
    assert cancelled == 1
    open_run.refresh_from_db()
    assert open_run.status == CampaignRunStatus.CANCELLED


@pytest.mark.django_db
def test_validate_required_variables_empty_value(campaign_fixture):
    template = EmailTemplate.objects.create(
        name="EmptyField",
        subject_template="Hi",
        body_template="Body",
        required_variables=["recipient.name"],
    )
    recipient = campaign_fixture["recipient"]
    recipient.name = ""
    recipient.save(update_fields=["name"])
    context = build_render_context(recipient=recipient, campaign=campaign_fixture["campaign"])
    with pytest.raises(MissingTemplateVariable):
        validate_required_variables(template, context)


@pytest.mark.django_db
def test_campaign_admin_reports_action_errors(campaign_fixture, admin_request):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status"])
    modeladmin = CampaignAdmin(Campaign, admin.site)
    queryset = Campaign.objects.filter(pk=campaign.id)
    pause_campaigns(modeladmin, admin_request, queryset)
    resume_campaigns(modeladmin, admin_request, queryset)


@pytest.mark.django_db
def test_schedule_admin_next_run_local(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type="one_time",
        send_at=campaign_fixture["now"],
        timezone_name="UTC",
    )
    admin_obj = CampaignScheduleAdmin(CampaignSchedule, admin.site)
    assert admin_obj.next_run_local(schedule) is not None
