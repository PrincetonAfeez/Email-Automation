from __future__ import annotations

import pytest

from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import requeue_outbox, send_outbox_email


@pytest.mark.django_db
def test_exhausted_job_dead_letters_then_requeues(dispatched_row):
    dispatched_row.max_attempts = 1
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "temporary"))

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")
    assert outcome.status == OutboxStatus.DEAD_LETTERED

    requeued = requeue_outbox(dispatched_row.id)
    requeued.refresh_from_db()
    assert requeued.status == OutboxStatus.REQUEUED
    assert requeued.attempt_count == 0
    assert requeued.dead_lettered_at is None


@pytest.mark.django_db
def test_failed_row_can_be_requeued(dispatched_row):
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.permanent_failure("fake", "invalid", "bad"))
    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")
    assert outcome.status == OutboxStatus.FAILED

    requeued = requeue_outbox(dispatched_row.id)
    assert requeued.status == OutboxStatus.REQUEUED


@pytest.mark.django_db
def test_requeue_rejects_non_failed_rows(dispatched_row):
    with pytest.raises(ValueError):
        requeue_outbox(dispatched_row.id)
