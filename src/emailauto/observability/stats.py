""" Stats for EmailAuto."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count

from emailauto.core import clock
from emailauto.core.states import EventType, OutboxStatus
from emailauto.outbox.models import EmailEventLog, EmailOutbox


def outbox_counts(*, campaign_id: int | None = None) -> dict[str, int]:
    qs = EmailOutbox.objects.all()
    if campaign_id is not None:
        qs = qs.filter(campaign_id=campaign_id)
    grouped = qs.values("status").annotate(total=Count("id"))
    counts = {status: 0 for status, _label in OutboxStatus.CHOICES}
    counts.update({row["status"]: row["total"] for row in grouped})
    counts["total"] = sum(counts.values())
    return counts


def run_counts(*, campaign_run_id: int) -> dict[str, int]:
    """Per-run status counts for one campaign occurrence."""
    grouped = EmailOutbox.objects.filter(campaign_run_id=campaign_run_id).values("status").annotate(total=Count("id"))
    counts = {status: 0 for status, _label in OutboxStatus.CHOICES}
    counts.update({row["status"]: row["total"] for row in grouped})
    counts["total"] = sum(counts.values())
    return counts


def recent_send_throughput(*, window_seconds: int = 60) -> int:
    """Number of successful sends recorded in the last window (a simple throughput gauge)."""
    cutoff = clock.utcnow() - timedelta(seconds=window_seconds)
    return EmailEventLog.objects.filter(event_type=EventType.SENT, created_at__gte=cutoff).count()


def recent_failures(limit: int = 10):
    # Only genuine failures — a retry_scheduled row has not failed, it is waiting to retry.
    return (
        EmailOutbox.objects.select_related("campaign", "recipient")
        .filter(status__in=[OutboxStatus.FAILED, OutboxStatus.DEAD_LETTERED])
        .order_by("-updated_at")[:limit]
    )

