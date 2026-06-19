from __future__ import annotations

import pytest
from django.core.management import call_command

from emailauto.campaigns.services import pause_campaign, resume_campaign, set_campaign_status
from emailauto.core.states import CampaignStatus


@pytest.mark.django_db
def test_initdb_smoke():
    call_command("emailauto_initdb", "--noinput")


@pytest.mark.django_db
def test_dlq_list_smoke():
    call_command("emailauto_dlq", "list")


@pytest.mark.django_db
def test_pause_resume_restores_prior_status(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    assert campaign.status == CampaignStatus.SCHEDULED

    pause_campaign(campaign.id)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.PAUSED
    assert campaign.status_before_pause == CampaignStatus.SCHEDULED

    resume_campaign(campaign.id)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED
    assert campaign.status_before_pause == ""


@pytest.mark.django_db
def test_set_campaign_status_paused_records_before_pause(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    set_campaign_status(campaign.id, CampaignStatus.PAUSED)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.PAUSED
    assert campaign.status_before_pause == CampaignStatus.SCHEDULED

    set_campaign_status(campaign.id, CampaignStatus.ACTIVE)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED


@pytest.mark.django_db
def test_cancel_completed_campaign_rejected(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status"])

    with pytest.raises(ValueError):
        from emailauto.campaigns.services import cancel_campaign

        cancel_campaign(campaign.id)
