""" Test max coverage dispatcher for EmailAuto."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

import emailauto.scheduling.dispatcher as dispatcher_module
from emailauto.core.states import CampaignRunStatus, CampaignStatus, OutboxStatus, ScheduleType
from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.dispatcher import (
    _disable_broken_schedule,
    _publish_task,
    _recover_stale_enqueued,
    create_run_and_outbox,
    dispatch_due_schedules,
    enqueue_due_outbox,
    enqueue_outbox_by_id,
    reconcile_campaign_runs,
    republish_enqueued_row,
)
from emailauto.scheduling.models import CampaignRun, CampaignSchedule


@pytest.mark.django_db
def test_create_run_transitions_pending_run(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    scheduled_for = schedule.next_run_at
    run_key = f"schedule:{schedule.id}:{scheduled_for.isoformat()}"
    CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key=run_key,
        scheduled_for=scheduled_for,
        status=CampaignRunStatus.PENDING,
    )
    run, created, _ = create_run_and_outbox(schedule)
    run.refresh_from_db()
    assert run.status in {CampaignRunStatus.GENERATING_OUTBOX, CampaignRunStatus.OUTBOX_GENERATED}
    assert created >= 0


@pytest.mark.django_db
def test_create_run_generating_without_generated_at(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    scheduled_for = schedule.next_run_at
    run_key = f"schedule:{schedule.id}:{scheduled_for.isoformat()}"
    CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key=run_key,
        scheduled_for=scheduled_for,
        status=CampaignRunStatus.GENERATING_OUTBOX,
        generated_at=None,
    )
    run, created, _ = create_run_and_outbox(schedule)
    run.refresh_from_db()
    assert run.generated_at is not None


@pytest.mark.django_db
def test_create_run_skips_when_run_already_terminal(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
        enabled=True,
    )
    scheduled_for = schedule.next_run_at
    run_key = f"schedule:{schedule.id}:{scheduled_for.isoformat()}"
    CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key=run_key,
        scheduled_for=scheduled_for,
        status=CampaignRunStatus.COMPLETED,
    )
    run, created, _ = create_run_and_outbox(schedule)
    schedule.refresh_from_db()
    assert created == 0
    assert run is not None
    assert schedule.enabled is False


@pytest.mark.django_db
def test_create_run_integrity_error_race(campaign_fixture, monkeypatch):
    from django.db import IntegrityError

    from emailauto.recipients.models import Recipient

    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    run, created, _ = create_run_and_outbox(schedule)
    existing = EmailOutbox.objects.get(campaign_run=run)
    assert created >= 1

    recipient2 = Recipient.objects.create(email="race@example.com", name="Race")
    campaign_fixture["recipient_list"].recipients.add(recipient2)
    schedule.enabled = True
    schedule.next_run_at = timezone.now()
    schedule.save(update_fields=["enabled", "next_run_at"])

    real_get = EmailOutbox.objects.get

    def race_get_or_create(*args, **kwargs):
        if kwargs.get("defaults", {}).get("recipient") == recipient2:
            raise IntegrityError("duplicate")
        return EmailOutbox.objects.get_or_create(*args, **kwargs)

    def get_existing(**kwargs):
        if kwargs.get("idempotency_key", "").endswith(":recipient:2"):
            return existing
        return real_get(**kwargs)

    monkeypatch.setattr(EmailOutbox.objects, "get_or_create", race_get_or_create)
    monkeypatch.setattr(EmailOutbox.objects, "get", get_existing)
    run2, created2, _ = create_run_and_outbox(schedule)
    assert run2 is not None
    assert created2 == 0


@pytest.mark.django_db
def test_advance_schedule_disables_when_next_occurrence_none(campaign_fixture, monkeypatch):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        send_at=timezone.now() - timedelta(minutes=1),
        cron_expression="0 9 * * MON",
    )
    monkeypatch.setattr(
        "emailauto.scheduling.dispatcher.next_occurrence",
        lambda _schedule, _when: None,
    )
    dispatch_due_schedules()
    schedule.refresh_from_db()
    assert schedule.enabled is False


@pytest.mark.django_db
def test_advance_schedule_value_error_disables_without_rollback(campaign_fixture, monkeypatch):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.RECURRING,
        send_at=timezone.now() - timedelta(minutes=1),
        cron_expression="0 9 * * MON",
    )

    def boom(_schedule, _when):
        raise ValueError("impossible cron horizon")

    monkeypatch.setattr("emailauto.scheduling.dispatcher.next_occurrence", boom)
    dispatch_due_schedules()
    schedule.refresh_from_db()
    assert schedule.enabled is False
    assert EmailOutbox.objects.filter(campaign=campaign_fixture["campaign"]).exists()


@pytest.mark.django_db
def test_publish_task_swallows_broker_errors():
    with patch("emailauto.workers.tasks.send_outbox_email_task.apply_async", side_effect=RuntimeError("broker down")):
        assert _publish_task(1, "task-id") is False


@pytest.mark.django_db
def test_republish_fails_when_publish_fails(dispatched_row):
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = timezone.now()
    dispatched_row.save()
    with patch.object(dispatcher_module, "_publish_task", return_value=False):
        assert republish_enqueued_row(dispatched_row.id) is False


@pytest.mark.django_db
def test_enqueue_outbox_rollback_on_publish_failure(dispatched_row):
    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.next_attempt_at = timezone.now()
    dispatched_row.save()
    with patch.object(dispatcher_module, "_publish_task", return_value=False):
        assert enqueue_outbox_by_id(dispatched_row.id, enqueue_celery=True) is False
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.RETRY_SCHEDULED


@pytest.mark.django_db
def test_enqueue_due_outbox_publish_failure_decrements_count(dispatched_row):
    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.next_attempt_at = timezone.now()
    campaign = dispatched_row.campaign
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    dispatched_row.save()
    with patch.object(dispatcher_module, "_publish_task", return_value=False):
        count = enqueue_due_outbox(limit=10, enqueue_celery=True)
    assert count == 0


@pytest.mark.django_db
def test_recover_stale_enqueued_republishes(dispatched_row, settings):
    settings.EMAILAUTO_ENQUEUED_STALE_SECONDS = 0
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = timezone.now() - timedelta(minutes=10)
    campaign = dispatched_row.campaign
    campaign.status = CampaignStatus.ACTIVE
    campaign.save(update_fields=["status"])
    dispatched_row.save()
    with patch.object(dispatcher_module, "_publish_task", return_value=True):
        recovered = _recover_stale_enqueued(
            now=timezone.now(),
            limit=10,
            active_statuses=[CampaignStatus.ACTIVE],
        )
    assert recovered == 1


@pytest.mark.django_db
def test_reconcile_empty_generated_run_completes(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    run = CampaignRun.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule=schedule,
        run_key="empty-run",
        scheduled_for=timezone.now(),
        status=CampaignRunStatus.OUTBOX_GENERATED,
    )
    assert reconcile_campaign_runs(limit=10) >= 1
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.COMPLETED


@pytest.mark.django_db
def test_reconcile_all_failed_marks_run_failed(dispatched_row):
    run = dispatched_row.campaign_run
    run.status = CampaignRunStatus.DISPATCHING
    run.save(update_fields=["status"])
    dispatched_row.status = OutboxStatus.FAILED
    dispatched_row.save(update_fields=["status"])
    assert reconcile_campaign_runs(limit=10) >= 1
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.FAILED


@pytest.mark.django_db
def test_reconcile_inflight_marks_dispatched(dispatched_row):
    run = dispatched_row.campaign_run
    run.status = CampaignRunStatus.DISPATCHING
    run.save(update_fields=["status"])
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.save(update_fields=["status"])
    assert reconcile_campaign_runs(limit=10) >= 1
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.DISPATCHED


@pytest.mark.django_db
def test_reconcile_partial_inflight_marks_dispatched(dispatched_row, campaign_fixture):
    from emailauto.recipients.models import Recipient

    run = dispatched_row.campaign_run
    run.status = CampaignRunStatus.DISPATCHING
    run.save(update_fields=["status"])
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    recipient2 = Recipient.objects.create(email="partial@example.com", name="Partial")
    EmailOutbox.objects.create(
        campaign=dispatched_row.campaign,
        campaign_run=run,
        recipient=recipient2,
        template=dispatched_row.template,
        idempotency_key=f"{dispatched_row.idempotency_key}:partial",
        status=OutboxStatus.PENDING,
        subject_snapshot="s",
        body_snapshot="b",
        scheduled_for=timezone.now(),
        next_attempt_at=timezone.now(),
    )
    assert reconcile_campaign_runs(limit=10) >= 1
    run.refresh_from_db()
    assert run.status == CampaignRunStatus.DISPATCHED


@pytest.mark.django_db
def test_disable_broken_schedule(campaign_fixture):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
        enabled=True,
    )
    _disable_broken_schedule(schedule, ValueError("broken"))
    schedule.refresh_from_db()
    assert schedule.enabled is False


@pytest.mark.django_db
def test_dispatch_disables_schedule_on_value_error(campaign_fixture, monkeypatch):
    schedule = CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now() - timedelta(minutes=1),
        enabled=True,
    )

    def boom(_schedule, **_kwargs):
        if _schedule.id == schedule.id:
            raise ValueError("bad schedule")
        return None, 0, False

    monkeypatch.setattr(dispatcher_module, "create_run_and_outbox", boom)
    dispatch_due_schedules()
    schedule.refresh_from_db()
    assert schedule.enabled is False
