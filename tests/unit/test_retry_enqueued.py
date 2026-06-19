from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from emailauto.core.states import OutboxStatus
from emailauto.outbox.services import retry_outbox


@pytest.mark.django_db
def test_retry_enqueued_republishes_when_not_eager(dispatched_row, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False

    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = timezone.now()
    dispatched_row.save(update_fields=["status", "enqueued_at"])

    with patch("emailauto.scheduling.dispatcher._publish_task", return_value=True) as publish:
        row = retry_outbox(dispatched_row.id)

    publish.assert_called_once()
    row.refresh_from_db()
    assert row.status == OutboxStatus.ENQUEUED


@pytest.mark.django_db
def test_retry_pending_enqueues_immediately(dispatched_row, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.next_attempt_at = timezone.now() + timedelta(days=1)
    dispatched_row.save(update_fields=["status", "next_attempt_at"])

    row = retry_outbox(dispatched_row.id)

    row.refresh_from_db()
    assert row.status == OutboxStatus.SENT
