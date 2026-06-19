from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.scheduling.dispatcher import enqueue_due_outbox


@pytest.mark.django_db
def test_stale_enqueued_row_is_recovered_and_sent(dispatched_row, settings):
    settings.EMAILAUTO_ENQUEUED_STALE_SECONDS = 60
    # Simulate a lost task: the row is 'enqueued' but was never claimed and has gone stale.
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = timezone.now() - timedelta(seconds=300)
    dispatched_row.save(update_fields=["status", "enqueued_at"])

    # enqueue_celery=True runs the recovered task eagerly (CELERY_TASK_ALWAYS_EAGER).
    enqueue_due_outbox(enqueue_celery=True)

    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.SENT
    assert len(FakeEmailBackend.sent_messages) == 1


@pytest.mark.django_db
def test_recovery_refreshes_enqueued_at_so_it_is_not_republished_every_tick(dispatched_row, settings, monkeypatch):
    import emailauto.scheduling.dispatcher as dispatcher_module

    settings.EMAILAUTO_ENQUEUED_STALE_SECONDS = 60
    stale_time = timezone.now() - timedelta(seconds=300)
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = stale_time
    dispatched_row.save(update_fields=["status", "enqueued_at"])

    # Simulate a broker publish that succeeds but is processed asynchronously (row stays
    # enqueued), so we can observe the enqueued_at refresh.
    monkeypatch.setattr(dispatcher_module, "_publish_task", lambda outbox_id, celery_task_id: True)

    dispatcher_module.enqueue_due_outbox(enqueue_celery=True)

    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.ENQUEUED
    assert dispatched_row.enqueued_at > stale_time  # refreshed -> won't re-fire next tick


@pytest.mark.django_db
def test_fresh_enqueued_row_is_not_recovered(dispatched_row, settings):
    settings.EMAILAUTO_ENQUEUED_STALE_SECONDS = 300
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = timezone.now()  # fresh, still being processed
    dispatched_row.save(update_fields=["status", "enqueued_at"])

    enqueue_due_outbox(enqueue_celery=True)

    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.ENQUEUED  # left alone
    assert len(FakeEmailBackend.sent_messages) == 0
