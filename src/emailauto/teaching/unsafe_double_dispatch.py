"""UNSAFE: sending a row without the database claim step 

Teaching point: the production worker claims an outbox row with an atomic
compare-and-swap before sending, so two tasks racing for one row produce exactly one
send. Here we mimic the *broken* worker that renders and sends straight from a row
without claiming, so two "dispatches" of the same row send the recipient twice.

The demo runs inside a rolled-back transaction and touches only throwaway rows.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.dispatcher import idempotency_key
from emailauto.teaching._fixtures import build_campaign, build_run, one_time_schedule
from emailauto.templates.renderer import render_template


def run_demo() -> dict[str, Any]:
    FakeEmailBackend.clear()
    backend = FakeEmailBackend()
    result: dict[str, Any] = {}
    with transaction.atomic():
        template, recipients, _rlist, campaign = build_campaign("unsafe-double")
        schedule = one_time_schedule(campaign)
        run = build_run(campaign, schedule)
        recipient = recipients[0]
        row = EmailOutbox.objects.create(
            campaign=campaign,
            campaign_run=run,
            recipient=recipient,
            template=template,
            subject_snapshot=template.subject_template,
            body_snapshot=template.body_template,
            body_format=template.body_format,
            idempotency_key=idempotency_key(campaign_id=campaign.id, campaign_run_id=run.id, recipient_id=recipient.id),
            scheduled_for=run.scheduled_for,
            next_attempt_at=run.scheduled_for,
        )

        # Two dispatches of the SAME row, neither claiming it first -> two sends.
        for _ in range(2):
            rendered = render_template(
                email_template=template,
                recipient=recipient,
                campaign=campaign,
                campaign_run=run,
                idempotency_key=row.idempotency_key,
            )
            backend.send_email(rendered)

        result = {
            "provider_sends": len(FakeEmailBackend.sent_messages),
            "expected_with_claim": 1,
            "problem": "same durable row was sent twice without a protected claim",
        }
        transaction.set_rollback(True)
    return result
