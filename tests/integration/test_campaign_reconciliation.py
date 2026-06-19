from __future__ import annotations

import pytest
from django.utils import timezone

from emailauto.campaigns.services import reconcile_campaigns
from emailauto.core.states import CampaignStatus, ScheduleType
from emailauto.outbox.services import send_outbox_email
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_reconcile_campaigns_marks_completed(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    dispatch_due_schedules()
    for row in campaign_fixture["campaign"].outbox_rows.all():
        send_outbox_email(row.id, backend_name="fake")

    assert reconcile_campaigns() == 1
    campaign_fixture["campaign"].refresh_from_db()
    assert campaign_fixture["campaign"].status == CampaignStatus.COMPLETED
