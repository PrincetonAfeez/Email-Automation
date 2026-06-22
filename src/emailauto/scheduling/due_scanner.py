""" Due scanner for EmailAuto."""

from __future__ import annotations

from datetime import datetime

from django.db.models import QuerySet

from emailauto.core import clock
from emailauto.core.states import CampaignStatus
from emailauto.scheduling.models import CampaignSchedule


def due_schedules(*, now: datetime | None = None) -> QuerySet[CampaignSchedule]:
    current = now or clock.utcnow()
    return (
        CampaignSchedule.objects.select_related("campaign", "campaign__template", "campaign__recipient_list")
        .filter(
            enabled=True,
            next_run_at__isnull=False,
            next_run_at__lte=current,
            campaign__status__in=[CampaignStatus.SCHEDULED, CampaignStatus.ACTIVE],
        )
        .order_by("next_run_at", "id")
    )

