from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from emailauto.outbox.models import EmailOutbox
from emailauto.scheduling.dispatcher import idempotency_key


def test_key_is_deterministic():
    key = idempotency_key(campaign_id=1, campaign_run_id=2, recipient_id=3)
    assert key == idempotency_key(campaign_id=1, campaign_run_id=2, recipient_id=3)


def test_key_varies_by_recipient_and_run():
    base = idempotency_key(campaign_id=1, campaign_run_id=2, recipient_id=3)
    assert base != idempotency_key(campaign_id=1, campaign_run_id=2, recipient_id=4)
    assert base != idempotency_key(campaign_id=1, campaign_run_id=9, recipient_id=3)


def test_key_includes_its_components():
    key = idempotency_key(campaign_id=7, campaign_run_id=8, recipient_id=9)
    assert "campaign:7" in key and "run:8" in key and "recipient:9" in key


@pytest.mark.django_db
def test_unique_constraint_blocks_duplicate_outbox(dispatched_row):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EmailOutbox.objects.create(
                campaign=dispatched_row.campaign,
                campaign_run=dispatched_row.campaign_run,
                recipient=dispatched_row.recipient,
                template=dispatched_row.template,
                subject_snapshot="x",
                body_snapshot="y",
                idempotency_key=dispatched_row.idempotency_key,
                scheduled_for=dispatched_row.scheduled_for,
            )
