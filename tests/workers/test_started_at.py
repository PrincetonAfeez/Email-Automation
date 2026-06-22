""" Test started at for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import send_outbox_email
from emailauto.recipients.suppression import suppress_email


@pytest.mark.django_db
def test_started_at_records_first_send_not_last_reclaim(dispatched_row):
    dispatched_row.max_attempts = 5
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "t", "t"))

    send_outbox_email(dispatched_row.id, backend_name="fake")  # first attempt fails -> retry_scheduled
    dispatched_row.refresh_from_db()
    first_started_at = dispatched_row.started_at
    assert first_started_at is not None

    # Make the retry due and send again (succeeds).
    dispatched_row.next_attempt_at = dispatched_row.scheduled_for
    dispatched_row.save(update_fields=["next_attempt_at"])
    send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.SENT
    # started_at reflects when sending FIRST began, unchanged by the re-claim.
    assert dispatched_row.started_at == first_started_at


@pytest.mark.django_db
def test_suppressed_row_never_records_started_at(dispatched_row):
    suppress_email(dispatched_row.recipient.email, reason="blocked")

    send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.SKIPPED_SUPPRESSED
    assert dispatched_row.started_at is None  # never entered the sending path
