""" Test max coverage final for EmailAuto."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from emailauto.campaigns.admin import CampaignAdmin, cancel_campaigns
from emailauto.campaigns.models import Campaign
from emailauto.campaigns.services import reconcile_campaigns, resume_campaign, trigger_campaign_now
from emailauto.core.states import CampaignRunStatus, CampaignStatus, OutboxStatus
from emailauto.email_providers.base import EmailBackend
from emailauto.outbox.services import _cancel_inflight_outbox, bulk_cancel_open_outbox
from emailauto.outbox.transitions import _mark_run_dispatching
from emailauto.scheduling.models import CampaignRun, CampaignSchedule


@pytest.mark.django_db
def test_resume_restores_active_when_pause_state_invalid(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.PAUSED
    campaign.status_before_pause = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status", "status_before_pause"])
    resumed = resume_campaign(campaign.id)
    assert resumed.status == CampaignStatus.ACTIVE


@pytest.mark.django_db
def test_reconcile_campaigns_skips_value_error(campaign_fixture, monkeypatch):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    with patch("emailauto.campaigns.services.mark_campaign_completed", side_effect=ValueError("not ready")):
        assert reconcile_campaigns(limit=5) == 0


@pytest.mark.django_db
def test_trigger_raises_when_run_generation_fails(campaign_fixture):
    with patch("emailauto.scheduling.dispatcher.create_run_and_outbox", return_value=(None, 0, False)):
        with pytest.raises(RuntimeError, match="Failed to generate a run"):
            trigger_campaign_now(campaign_fixture["campaign"].id, enqueue_celery=False)


@pytest.mark.django_db
def test_cancel_campaign_admin_error_path(campaign_fixture, admin_request):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status"])
    cancel_campaigns(CampaignAdmin(Campaign, admin.site), admin_request, Campaign.objects.filter(pk=campaign.id))


@pytest.mark.django_db
def test_campaign_cli_missing_template_and_list_and_errors(campaign_fixture):
    with pytest.raises(CommandError, match="No template named"):
        call_command(
            "emailauto_campaign",
            "create",
            "--name",
            "x",
            "--template",
            "missing",
            "--list",
            campaign_fixture["recipient_list"].name,
        )
    with pytest.raises(CommandError, match="No recipient list named"):
        call_command(
            "emailauto_campaign",
            "create",
            "--name",
            "x",
            "--template",
            campaign_fixture["template"].name,
            "--list",
            "missing-list",
        )
    with pytest.raises(CommandError):
        call_command("emailauto_campaign", "status", str(campaign_fixture["campaign"].id), "not-a-status")
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.COMPLETED
    campaign.save(update_fields=["status"])
    with pytest.raises(CommandError):
        call_command("emailauto_campaign", "pause", str(campaign.id))


@pytest.mark.django_db
def test_campaign_cli_status_value_error(campaign_fixture):
    campaign = campaign_fixture["campaign"]
    campaign.status = CampaignStatus.CANCELLED
    campaign.save(update_fields=["status"])
    with pytest.raises(CommandError, match="Cannot complete"):
        call_command("emailauto_campaign", "status", str(campaign.id), CampaignStatus.COMPLETED)


def test_demo_list_command():
    out = StringIO()
    call_command("emailauto_demo", "list", stdout=out)
    assert "idempotency" in out.getvalue()


@pytest.mark.django_db
def test_demo_single_safe_demo():
    out = StringIO()
    call_command("emailauto_demo", "idempotency", stdout=out)
    assert out.getvalue()


def test_email_backend_abstract_send_raises():
    class DelegatingBackend(EmailBackend):
        def send_email(self, message):
            return EmailBackend.send_email(self, message)

    with pytest.raises(NotImplementedError):
        DelegatingBackend().send_email(None)  # type: ignore[arg-type]


def test_mark_run_dispatching_noop_for_missing_id():
    assert _mark_run_dispatching(None) is None


@pytest.mark.django_db
def test_cancel_inflight_invalid_status(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    with pytest.raises(ValueError, match="not in-flight"):
        _cancel_inflight_outbox(dispatched_row.id, last_error="x")


@pytest.mark.django_db
def test_bulk_cancel_inflight_skips_errors(dispatched_row, monkeypatch):
    dispatched_row.status = OutboxStatus.SENDING
    dispatched_row.save(update_fields=["status"])
    with patch("emailauto.outbox.services._cancel_inflight_outbox", side_effect=ValueError("stuck")):
        assert bulk_cancel_open_outbox(dispatched_row.campaign_id) == 0


@pytest.mark.django_db
def test_enqueue_due_outbox_skips_non_enqueueable(dispatched_row):
    from emailauto.scheduling.dispatcher import enqueue_due_outbox

    dispatched_row.status = OutboxStatus.SENT
    campaign = dispatched_row.campaign
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    dispatched_row.save(update_fields=["status"])
    assert enqueue_due_outbox(limit=10, enqueue_celery=False) == 0


@pytest.mark.django_db
def test_enqueue_due_outbox_continues_after_none_enqueue(dispatched_row, monkeypatch):
    from emailauto.scheduling.dispatcher import enqueue_due_outbox

    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.next_attempt_at = timezone.now()
    campaign = dispatched_row.campaign
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    dispatched_row.save()
    calls = {"n": 0}

    def fake_enqueue(row_id, **_kwargs):
        calls["n"] += 1
        return None

    monkeypatch.setattr("emailauto.scheduling.dispatcher.enqueue_outbox_row", fake_enqueue)
    assert enqueue_due_outbox(limit=10, enqueue_celery=False) == 0
    assert calls["n"] >= 1


@pytest.mark.django_db
def test_reconcile_keeps_dispatched_when_counts_incomplete(dispatched_row, monkeypatch):
    import emailauto.scheduling.dispatcher as dispatcher_module

    run = dispatched_row.campaign_run
    run.status = CampaignRunStatus.DISPATCHED
    run.save(update_fields=["status"])

    class FakeQS:
        def annotate(self, **_a):
            return self

        def values(self, *_a):
            return self

        def __iter__(self):
            yield {
                "campaign_run": run.id,
                "total": 2,
                "terminal": 1,
                "failed": 0,
                "inflight": 0,
            }

    monkeypatch.setattr(dispatcher_module.EmailOutbox.objects, "filter", lambda **_kw: FakeQS())
    assert dispatcher_module.reconcile_campaign_runs(limit=10) == 0
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.DISPATCHED


@pytest.mark.django_db
def test_reconcile_outbox_generated_marks_dispatching(dispatched_row, monkeypatch):
    import emailauto.scheduling.dispatcher as dispatcher_module

    run = dispatched_row.campaign_run
    run.status = CampaignRunStatus.OUTBOX_GENERATED
    run.save(update_fields=["status"])

    class FakeQS:
        def annotate(self, **_a):
            return self

        def values(self, *_a):
            return self

        def __iter__(self):
            yield {
                "campaign_run": run.id,
                "total": 2,
                "terminal": 1,
                "failed": 0,
                "inflight": 0,
            }

    monkeypatch.setattr(dispatcher_module.EmailOutbox.objects, "filter", lambda **_kw: FakeQS())
    assert dispatcher_module.reconcile_campaign_runs(limit=10) >= 1
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.DISPATCHING


@pytest.mark.django_db
def test_schedule_and_run_str_and_local_properties(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type="one_time",
        send_at=campaign_fixture["now"],
        timezone_name="UTC",
    )
    assert "one_time" in str(schedule)
    assert schedule.send_at_local is not None
    run = CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key="str-run",
        scheduled_for=campaign_fixture["now"],
    )
    assert "Launch" in str(run)


@pytest.mark.django_db
def test_next_occurrence_without_cron_or_interval(campaign_fixture):
    from emailauto.scheduling.recurrence import next_occurrence

    schedule = CampaignSchedule(
        campaign=campaign_fixture["campaign"],
        schedule_type="recurring",
    )
    assert next_occurrence(schedule, campaign_fixture["now"]) is None


@pytest.mark.django_db
def test_schedule_clean_fetches_campaign_by_id(campaign_fixture):
    from emailauto.campaigns.models import Campaign

    cancelled = campaign_fixture["campaign"]
    cancelled.status = CampaignStatus.CANCELLED
    cancelled.save(update_fields=["status"])
    other = Campaign.objects.create(
        name="Other",
        template=campaign_fixture["template"],
        recipient_list=campaign_fixture["recipient_list"],
        status=CampaignStatus.SCHEDULED,
    )
    schedule = CampaignSchedule.objects.create(
        campaign=other,
        schedule_type="recurring",
        send_at=campaign_fixture["now"],
        cron_expression="0 9 * * MON",
        enabled=False,
    )
    schedule.campaign_id = cancelled.id
    schedule.__dict__["campaign"] = other
    schedule.enabled = True
    with pytest.raises(ValidationError):
        schedule.save()


def test_cron_empty_token_parts_do_not_match():
    from datetime import UTC, datetime

    from emailauto.scheduling.recurrence import cron_matches

    moment = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    assert not cron_matches(moment, "0 9 1,,31 6 *")


def test_weekday_expression_skips_empty_parts():
    from datetime import UTC, datetime

    from emailauto.scheduling.recurrence import _weekday_matches

    cron_weekday = (datetime(2026, 6, 16, 9, 0, tzinfo=UTC).weekday() + 1) % 7
    assert not _weekday_matches(cron_weekday, ",,")


@pytest.mark.django_db
def test_bulk_cancel_runs_skips_terminal_status(campaign_fixture):
    from emailauto.scheduling.run_transitions import bulk_cancel_runs

    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type="one_time",
        send_at=campaign_fixture["now"],
    )
    CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key="terminal-run",
        scheduled_for=campaign_fixture["now"],
        status=CampaignRunStatus.COMPLETED,
    )
    cancelled = bulk_cancel_runs(
        campaign_fixture["campaign"].id,
        open_statuses={CampaignRunStatus.COMPLETED, CampaignRunStatus.DISPATCHING},
    )
    assert cancelled == 0
