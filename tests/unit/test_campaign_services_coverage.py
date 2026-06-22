""" Test campaign services coverage for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.campaigns.services import (
    mark_campaign_completed,
    pause_campaign,
    resume_campaign,
    set_campaign_status,
    trigger_campaign_now,
)
from emailauto.core.states import CampaignStatus


@pytest.mark.django_db
def test_mark_campaign_completed_rejects_invalid_status(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    with pytest.raises(ValueError, match="Cannot complete"):
        mark_campaign_completed(campaign.id)


@pytest.mark.django_db
def test_set_campaign_status_completed_route(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    updated = set_campaign_status(campaign.id, CampaignStatus.COMPLETED)
    assert updated.status == CampaignStatus.COMPLETED


@pytest.mark.django_db
def test_trigger_campaign_promotes_draft(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.DRAFT
    campaign.save(update_fields=["status"])
    result = trigger_campaign_now(campaign.id, enqueue_celery=False)
    assert result.outbox_created >= 1


@pytest.mark.django_db
def test_trigger_rejects_cancelled(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    with pytest.raises(ValueError, match="Cannot trigger"):
        trigger_campaign_now(campaign.id)


@pytest.mark.django_db
def test_pause_resume_invalid(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    with pytest.raises(ValueError, match="Cannot pause"):
        pause_campaign(campaign.id)
    with pytest.raises(ValueError, match="Cannot resume"):
        resume_campaign(campaign.id)


@pytest.mark.django_db
def test_set_unknown_status_raises(campaign_fixture):
    with pytest.raises(ValueError, match="Unknown campaign status"):
        set_campaign_status(campaign_fixture["campaign"].id, "not-a-status")
