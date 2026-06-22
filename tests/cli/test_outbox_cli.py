""" Test outbox CLI for EmailAuto."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from emailauto.core.states import CampaignRunStatus, OutboxStatus, ScheduleType
from emailauto.scheduling.models import CampaignRun


@pytest.mark.django_db
def test_outbox_list_and_inspect_smoke(dispatched_row):
    out = StringIO()
    call_command("emailauto_outbox", "list", stdout=out)
    assert str(dispatched_row.id) in out.getvalue()

    call_command("emailauto_outbox", "inspect", "--id", str(dispatched_row.id), stdout=out)
    assert dispatched_row.recipient.email in out.getvalue()


@pytest.mark.django_db
def test_outbox_send_smoke(dispatched_row):
    call_command("emailauto_outbox", "send", str(dispatched_row.id), "--backend", "fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.SENT


@pytest.mark.django_db
def test_cancel_campaign_cancels_open_runs(campaign_fixture):
    from django.utils import timezone

    from emailauto.campaigns.services import cancel_campaign
    from emailauto.scheduling.dispatcher import dispatch_due_schedules
    from emailauto.scheduling.models import CampaignSchedule

    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    dispatch_due_schedules()
    run = CampaignRun.objects.get()
    cancel_campaign(campaign_fixture["campaign"].id)
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.CANCELLED
