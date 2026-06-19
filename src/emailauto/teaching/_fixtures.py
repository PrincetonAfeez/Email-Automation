"""Tiny in-DB fixtures for the teaching demos.

Every demo runs inside an ``atomic()`` block that is rolled back at the end, so these
helpers can create freely-named rows without polluting the database or colliding across
repeated demo runs.
"""

from __future__ import annotations

from emailauto.campaigns.models import Campaign
from emailauto.core import clock
from emailauto.core.states import CampaignStatus, ScheduleType
from emailauto.recipients.models import Recipient, RecipientList
from emailauto.recipients.suppression import suppress_email
from emailauto.scheduling.models import CampaignRun, CampaignSchedule
from emailauto.templates.models import EmailTemplate


def build_campaign(
    name: str,
    *,
    recipients: int = 1,
    suppressed: bool = False,
    subscribed: bool = True,
) -> tuple[EmailTemplate, list[Recipient], RecipientList, Campaign]:
    template = EmailTemplate.objects.create(
        name=f"{name}-tpl",
        subject_template="Hi {{ recipient.name }}",
        body_template="Hello {{ recipient.name }}",
        required_variables=[],
    )
    recipient_list = RecipientList.objects.create(name=f"{name}-list")
    created: list[Recipient] = []
    for index in range(recipients):
        recipient = Recipient.objects.create(email=f"{name}-{index}@example.com", name=f"User {index}", subscribed=subscribed)
        recipient_list.recipients.add(recipient)
        created.append(recipient)
        if suppressed:
            suppress_email(recipient.email, reason="demo suppression")
    campaign = Campaign.objects.create(
        name=f"{name}-campaign",
        template=template,
        recipient_list=recipient_list,
        status=CampaignStatus.SCHEDULED,
    )
    return template, created, recipient_list, campaign


def one_time_schedule(campaign: Campaign) -> CampaignSchedule:
    return CampaignSchedule.objects.create(
        campaign=campaign,
        schedule_type=ScheduleType.ONE_TIME,
        send_at=clock.utcnow(),
    )


def build_run(campaign: Campaign, schedule: CampaignSchedule) -> CampaignRun:
    return CampaignRun.objects.create(
        campaign=campaign,
        schedule=schedule,
        run_key=f"demo-run:{campaign.id}:{schedule.id}",
        scheduled_for=clock.utcnow(),
    )
