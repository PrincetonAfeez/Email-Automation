""" Test admin actions for EmailAuto."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.utils import timezone

from emailauto.campaigns.admin import CampaignAdmin, cancel_campaigns, pause_campaigns, resume_campaigns
from emailauto.campaigns.models import Campaign
from emailauto.core.states import CampaignStatus, OutboxStatus, ScheduleType
from emailauto.outbox.admin import EmailOutboxAdmin, requeue_failed_or_dead_lettered
from emailauto.outbox.models import EmailOutbox
from emailauto.recipients.admin import RecipientListAdmin
from emailauto.recipients.models import RecipientList
from emailauto.scheduling.admin import CampaignScheduleAdmin, generate_outbox
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_campaign_admin_actions(admin_client, admin_request, campaign_fixture):
    campaign = campaign_fixture["campaign"]
    changelist = admin_client.get("/admin/campaigns/campaign/")
    assert changelist.status_code == 200

    modeladmin = CampaignAdmin(Campaign, admin.site)
    queryset = Campaign.objects.filter(pk=campaign.id)

    pause_campaigns(modeladmin, admin_request, queryset)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.PAUSED

    resume_campaigns(modeladmin, admin_request, queryset)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED

    cancel_campaigns(modeladmin, admin_request, queryset)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.CANCELLED


@pytest.mark.django_db
def test_campaign_admin_action_errors_on_completed(campaign_fixture, admin_request):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status"])
    modeladmin = CampaignAdmin(Campaign, admin.site)
    pause_campaigns(modeladmin, admin_request, Campaign.objects.filter(pk=campaign.id))


@pytest.mark.django_db
def test_campaign_admin_resume_and_cancel_errors(campaign_fixture, admin_request):
    campaign = campaign_fixture["campaign"]
    modeladmin = CampaignAdmin(Campaign, admin.site)
    queryset = Campaign.objects.filter(pk=campaign.id)
    resume_campaigns(modeladmin, admin_request, queryset)
    cancel_campaigns(modeladmin, admin_request, queryset)


@pytest.mark.django_db
def test_outbox_admin_requeue_action(dispatched_row, admin_request):
    dispatched_row.status = OutboxStatus.DEAD_LETTERED
    dispatched_row.save(update_fields=["status"])
    modeladmin = EmailOutboxAdmin(EmailOutbox, admin.site)
    requeue_failed_or_dead_lettered(modeladmin, admin_request, EmailOutbox.objects.filter(pk=dispatched_row.id))
    dispatched_row.refresh_from_db()
    assert dispatched_row.status != OutboxStatus.DEAD_LETTERED


@pytest.mark.django_db
def test_schedule_admin_generate_outbox(campaign_fixture, admin_request):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    generate_outbox(CampaignScheduleAdmin(CampaignSchedule, admin.site), admin_request, CampaignSchedule.objects.filter(pk=schedule.id))


@pytest.mark.django_db
def test_schedule_admin_generate_skips_cancelled(campaign_fixture, admin_request):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    schedule = CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
        enabled=False,
    )
    generate_outbox(CampaignScheduleAdmin(CampaignSchedule, admin.site), admin_request, CampaignSchedule.objects.filter(pk=schedule.id))


@pytest.mark.django_db
def test_recipient_list_admin_count(campaign_fixture):
    admin_obj = RecipientListAdmin(RecipientList, admin.site)
    assert admin_obj.recipient_count(campaign_fixture["recipient_list"]) == 1


@pytest.mark.django_db
def test_campaign_run_admin_readonly(admin_client):
    response = admin_client.get("/admin/scheduling/campaignrun/")
    assert response.status_code == 200
