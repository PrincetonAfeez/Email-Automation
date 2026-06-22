""" Test recent failures for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.observability.stats import recent_failures
from emailauto.outbox.services import send_outbox_email


@pytest.mark.django_db
def test_retry_scheduled_is_not_counted_as_a_failure(dispatched_row):
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "t", "t"))
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.RETRY_SCHEDULED

    failure_ids = [row.id for row in recent_failures()]
    assert dispatched_row.id not in failure_ids


@pytest.mark.django_db
def test_dead_lettered_is_counted_as_a_failure(dispatched_row):
    dispatched_row.max_attempts = 1
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "t", "t"))
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.DEAD_LETTERED

    failure_ids = [row.id for row in recent_failures()]
    assert dispatched_row.id in failure_ids
