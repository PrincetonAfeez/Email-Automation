"""UNSAFE: a dispatcher without a deterministic idempotency key

Teaching point: the production dispatcher derives a stable key from
campaign + run + recipient and uses get_or_create, so a repeated dispatch is a no-op.
Here we mimic the *broken* version that mints a fresh key each pass, so running the
dispatcher twice creates two outbox rows (and would send the recipient two emails).

The demo runs inside a rolled-back transaction and touches only throwaway rows.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from django.db import transaction

from emailauto.outbox.models import EmailOutbox
from emailauto.teaching._fixtures import build_campaign, build_run, one_time_schedule


def run_demo() -> dict[str, Any]:
    result: dict[str, Any] = {}
    with transaction.atomic():
        template, recipients, _rlist, campaign = build_campaign("unsafe-noidem")
        schedule = one_time_schedule(campaign)
        run = build_run(campaign, schedule)
        recipient = recipients[0]

        # Two "dispatcher passes", each using a non-deterministic key -> two rows.
        for _ in range(2):
            EmailOutbox.objects.create(
                campaign=campaign,
                campaign_run=run,
                recipient=recipient,
                template=template,
                subject_snapshot=template.subject_template,
                body_snapshot=template.body_template,
                body_format=template.body_format,
                idempotency_key=f"unsafe:{uuid4().hex}",  # BUG: not derived from the occurrence
                scheduled_for=run.scheduled_for,
                next_attempt_at=run.scheduled_for,
            )

        result = {
            "outbox_rows": EmailOutbox.objects.filter(campaign_run=run, recipient=recipient).count(),
            "expected_with_idempotency_key": 1,
            "problem": "duplicate dispatcher run created duplicate app-level work",
        }
        transaction.set_rollback(True)
    return result
