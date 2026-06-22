""" Run transitions for EmailAuto."""

from __future__ import annotations

from emailauto.core.states import CampaignRunStatus, assert_campaign_run_transition
from emailauto.scheduling.models import CampaignRun


def transition_campaign_run(run: CampaignRun, target_status: str) -> CampaignRun:
    """Move a campaign run to ``target_status`` through the enforced state machine."""
    if run.status == target_status:
        return run
    assert_campaign_run_transition(run.status, target_status)
    run.status = target_status
    run.save(update_fields=["status", "updated_at"])
    return run


def transition_campaign_run_by_id(run_id: int, target_status: str) -> CampaignRun:
    run = CampaignRun.objects.get(pk=run_id)
    return transition_campaign_run(run, target_status)


def bulk_cancel_runs(campaign_id: int, *, open_statuses: set[str]) -> int:
    runs = list(CampaignRun.objects.filter(campaign_id=campaign_id, status__in=open_statuses))
    cancelled = 0
    for run in runs:
        if run.status in CampaignRunStatus.TERMINAL:
            continue
        transition_campaign_run(run, CampaignRunStatus.CANCELLED)
        cancelled += 1
    return cancelled
