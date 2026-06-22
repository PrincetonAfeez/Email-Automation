""" Claim for EmailAuto."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from emailauto.core.states import EventType, OutboxStatus
from emailauto.observability.events import record_event
from emailauto.outbox.models import EmailOutbox

CLAIMABLE_STATUSES = [
    OutboxStatus.PENDING,
    OutboxStatus.ENQUEUED,
    OutboxStatus.RETRY_SCHEDULED,
    OutboxStatus.REQUEUED,
]


@dataclass(frozen=True)
class Claim:
    outbox: EmailOutbox
    token: str


def claim_outbox(outbox_id: int, *, worker_id: str, celery_task_id: str = "") -> Claim | None:
    now = timezone.now()
    token = uuid4().hex
    with transaction.atomic():
        updated = (
            EmailOutbox.objects.filter(pk=outbox_id, status__in=CLAIMABLE_STATUSES)
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .update(
                status=OutboxStatus.CLAIMED,
                locked_by=worker_id,
                locked_at=now,
                claim_token=token,
                lock_version=F("lock_version") + 1,
                celery_task_id=celery_task_id,
                # started_at is intentionally NOT set here: the SENDING transition stamps it
                # once (`started_at or now`), so it records when sending first began rather
                # than the most recent (re)claim.
            )
        )
        if updated != 1:
            return None
        outbox = EmailOutbox.objects.select_related("campaign", "campaign_run", "recipient", "template").get(pk=outbox_id)
        record_event(EventType.CLAIMED, outbox=outbox, metadata={"worker_id": worker_id, "celery_task_id": celery_task_id})
    return Claim(outbox=outbox, token=token)

