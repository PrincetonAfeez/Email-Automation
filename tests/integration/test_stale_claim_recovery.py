""" Test stale claim recovery for EmailAuto."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from emailauto.core.states import OutboxStatus
from emailauto.outbox.services import release_stale_outbox
from emailauto.scheduling.dispatcher import _recover_stale_claims


@pytest.mark.django_db
def test_stale_claimed_row_is_recovered(dispatched_row, settings):
    settings.EMAILAUTO_CLAIMED_STALE_SECONDS = 60
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.locked_at = timezone.now() - timedelta(seconds=300)
    dispatched_row.claim_token = "stale-token"
    dispatched_row.save(update_fields=["status", "locked_at", "claim_token"])

    recovered = _recover_stale_claims(
        now=timezone.now(),
        limit=10,
    )

    assert recovered == 1
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.claim_token == ""


@pytest.mark.django_db
def test_release_stale_outbox_is_noop_for_sent(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    assert release_stale_outbox(dispatched_row.id, reason="noop") is None
