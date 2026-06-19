"""Safe, self-contained demonstrations of the real (correct) pipeline.

Each demo builds a tiny campaign, exercises the production code paths through the fake
backend, captures observable results, and rolls back so the database is left untouched
and the demo can be run repeatedly.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from emailauto.core import clock
from emailauto.core.results import SendResult
from emailauto.core.states import ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import send_outbox_email
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignRun, CampaignSchedule
from emailauto.teaching._fixtures import build_campaign, one_time_schedule


def run_basic() -> dict[str, Any]:
    FakeEmailBackend.clear()
    result: dict[str, Any] = {}
    with transaction.atomic():
        _template, _recipients, _rlist, campaign = build_campaign("demo-basic")
        one_time_schedule(campaign)
        summary = dispatch_due_schedules()
        outcomes = [send_outbox_email(row.id, backend_name="fake") for row in EmailOutbox.objects.filter(campaign=campaign)]
        result = {
            "outbox_created": summary.outbox_created,
            "statuses": [o.status for o in outcomes],
            "provider_sends": len(FakeEmailBackend.sent_messages),
        }
        transaction.set_rollback(True)
    return result


def run_scheduler() -> dict[str, Any]:
    result: dict[str, Any] = {}
    with transaction.atomic():
        _template, _recipients, _rlist, campaign = build_campaign("demo-sched")
        schedule = CampaignSchedule.objects.create(
            campaign=campaign,
            schedule_type=ScheduleType.RECURRING,
            send_at=clock.utcnow() - timedelta(minutes=1),
            interval_every=10,
            interval_period=CampaignSchedule.IntervalPeriod.MINUTES,
        )
        dispatch_due_schedules()
        schedule.refresh_from_db()
        result = {
            "runs_created": CampaignRun.objects.filter(campaign=campaign).count(),
            "outbox_rows": EmailOutbox.objects.filter(campaign=campaign).count(),
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            "still_enabled": schedule.enabled,
        }
        transaction.set_rollback(True)
    return result


def run_retry() -> dict[str, Any]:
    FakeEmailBackend.clear()
    result: dict[str, Any] = {}
    with transaction.atomic():
        _template, recipients, _rlist, campaign = build_campaign("demo-retry")
        one_time_schedule(campaign)
        dispatch_due_schedules()
        row = EmailOutbox.objects.get(campaign=campaign)
        FakeEmailBackend.fail_next(recipients[0].email, SendResult.transient_failure("fake", "timeout", "temporary"))
        outcome = send_outbox_email(row.id, backend_name="fake")
        row.refresh_from_db()
        result = {
            "status": outcome.status,
            "attempt_count": row.attempt_count,
            "scheduled_retry": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
        }
        transaction.set_rollback(True)
    return result


def run_idempotency() -> dict[str, Any]:
    FakeEmailBackend.clear()
    result: dict[str, Any] = {}
    with transaction.atomic():
        _template, _recipients, _rlist, campaign = build_campaign("demo-idem")
        one_time_schedule(campaign)
        first = dispatch_due_schedules()
        second = dispatch_due_schedules()
        row = EmailOutbox.objects.get(campaign=campaign)
        first_send = send_outbox_email(row.id, backend_name="fake")
        second_send = send_outbox_email(row.id, backend_name="fake")
        result = {
            "first_dispatch_created": first.outbox_created,
            "second_dispatch_created": second.outbox_created,
            "outbox_rows": EmailOutbox.objects.filter(campaign=campaign).count(),
            "first_send": first_send.status,
            "second_send": second_send.status,
            "provider_sends": len(FakeEmailBackend.sent_messages),
        }
        transaction.set_rollback(True)
    return result


def run_suppression() -> dict[str, Any]:
    FakeEmailBackend.clear()
    result: dict[str, Any] = {}
    with transaction.atomic():
        _template, _recipients, _rlist, campaign = build_campaign("demo-supp", suppressed=True)
        one_time_schedule(campaign)
        dispatch_due_schedules()
        row = EmailOutbox.objects.get(campaign=campaign)
        outcome = send_outbox_email(row.id, backend_name="fake")
        result = {
            "status": outcome.status,
            "provider_sends": len(FakeEmailBackend.sent_messages),
        }
        transaction.set_rollback(True)
    return result


def run_rate_limit() -> dict[str, Any]:
    FakeEmailBackend.clear()
    cache.clear()
    result: dict[str, Any] = {}
    original_limit = settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    try:
        with transaction.atomic():
            _template, _recipients, _rlist, campaign = build_campaign("demo-rl", recipients=3)
            one_time_schedule(campaign)
            dispatch_due_schedules()
            outcomes = [
                send_outbox_email(row.id, backend_name="fake")
                for row in EmailOutbox.objects.filter(campaign=campaign).order_by("id")
            ]
            statuses = [o.status for o in outcomes]
            result = {
                "statuses": statuses,
                "provider_sends": len(FakeEmailBackend.sent_messages),
                "throttled": sum(1 for status in statuses if status == "retry_scheduled"),
            }
            transaction.set_rollback(True)
    finally:
        settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = original_limit
    return result


def run_all() -> dict[str, Any]:
    return {name: runner() for name, runner in SAFE_DEMOS.items()}


SAFE_DEMOS: dict[str, Callable[[], dict[str, Any]]] = {
    "basic": run_basic,
    "scheduler": run_scheduler,
    "retry": run_retry,
    "idempotency": run_idempotency,
    "suppression": run_suppression,
    "rate-limit": run_rate_limit,
}
