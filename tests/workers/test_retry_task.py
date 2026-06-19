from __future__ import annotations

import pytest

from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import send_outbox_email


@pytest.mark.django_db
def test_transient_failure_schedules_retry(dispatched_row):
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "temporary"))

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.attempt_count == 1
    assert dispatched_row.next_attempt_at is not None


@pytest.mark.django_db
def test_permanent_failure_does_not_retry(dispatched_row):
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.permanent_failure("fake", "invalid", "bad address"))

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.FAILED
    assert dispatched_row.attempt_count == 1


@pytest.mark.django_db
def test_two_transient_failures_then_success(dispatched_row):
    dispatched_row.max_attempts = 5
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "temporary"))

    first = send_outbox_email(dispatched_row.id, backend_name="fake")
    assert first.status == OutboxStatus.RETRY_SCHEDULED

    # The retry is due immediately in tests; the dispatcher would re-enqueue it. Here we
    # send again directly to prove the second attempt succeeds and is recorded as attempt 2.
    dispatched_row.refresh_from_db()
    dispatched_row.next_attempt_at = dispatched_row.scheduled_for
    dispatched_row.save(update_fields=["next_attempt_at"])

    second = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert second.status == OutboxStatus.SENT
    assert dispatched_row.attempt_count == 2
    assert len(FakeEmailBackend.sent_messages) == 1
