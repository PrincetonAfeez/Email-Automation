""" Test outbox services coverage for EmailAuto."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from emailauto.core.exceptions import TemplateRenderError
from emailauto.core.results import SendResult
from emailauto.core.states import OutboxStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import (
    bulk_cancel_open_outbox,
    cancel_outbox,
    release_stale_outbox,
    requeue_dead_letter,
    requeue_outbox,
    retry_outbox,
    send_outbox_email,
)
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule


@pytest.mark.django_db
def test_send_missing_outbox_returns_missing():
    outcome = send_outbox_email(999999, backend_name="fake")
    assert outcome.status == "missing"


@pytest.mark.django_db
def test_requeue_and_retry_paths(dispatched_row):
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.permanent_failure("fake", "bad", "bad"))
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.FAILED

    requeued = requeue_outbox(dispatched_row.id)
    assert requeued.status == OutboxStatus.REQUEUED
    assert requeued.attempt_count == 0

    with pytest.raises(ValueError, match="Only failed or dead-lettered"):
        requeue_outbox(dispatched_row.id)


@pytest.mark.django_db
def test_requeue_dead_letter_alias(dispatched_row):
    dispatched_row.status = OutboxStatus.DEAD_LETTERED
    dispatched_row.save(update_fields=["status"])
    row = requeue_dead_letter(dispatched_row.id)
    assert row.status == OutboxStatus.REQUEUED


@pytest.mark.django_db
def test_retry_enqueued_republish_path(dispatched_row):
    dispatched_row.status = OutboxStatus.ENQUEUED
    dispatched_row.enqueued_at = dispatched_row.updated_at
    dispatched_row.save()
    with patch("emailauto.scheduling.dispatcher.republish_enqueued_row", return_value=True):
        row = retry_outbox(dispatched_row.id)
    assert row.status == OutboxStatus.ENQUEUED


@pytest.mark.django_db
def test_retry_invalid_status_raises(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    with pytest.raises(ValueError, match="Cannot retry"):
        retry_outbox(dispatched_row.id)


@pytest.mark.django_db
def test_cancel_invalid_and_bulk_cancel(campaign_fixture):
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    dispatch_due_schedules()
    row = campaign_fixture["campaign"].outbox_rows.get()
    cancel_outbox(row.id)
    row.refresh_from_db()
    assert row.status == OutboxStatus.CANCELLED
    with pytest.raises(ValueError):
        cancel_outbox(row.id)

    pending = EmailOutbox.objects.create(
        campaign=row.campaign,
        campaign_run=row.campaign_run,
        recipient=row.recipient,
        template=row.template,
        idempotency_key=f"{row.idempotency_key}-bulk",
        status=OutboxStatus.PENDING,
        subject_snapshot=row.subject_snapshot,
        body_snapshot=row.body_snapshot,
        body_format=row.body_format,
        required_variables_snapshot=row.required_variables_snapshot,
        scheduled_for=timezone.now(),
        next_attempt_at=timezone.now(),
    )
    assert bulk_cancel_open_outbox(campaign_fixture["campaign"].id) >= 1
    pending.refresh_from_db()
    assert pending.status == OutboxStatus.CANCELLED


@pytest.mark.django_db
def test_release_stale_noop_and_success(dispatched_row):
    assert release_stale_outbox(dispatched_row.id, reason="noop") is None
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.save(update_fields=["status"])
    released = release_stale_outbox(dispatched_row.id, reason="stale")
    assert released is not None
    assert released.status == OutboxStatus.RETRY_SCHEDULED


@pytest.mark.django_db
def test_template_render_error_marks_failed(dispatched_row):
    with patch("emailauto.outbox.services.render_template", side_effect=TemplateRenderError("bad")):
        outcome = send_outbox_email(dispatched_row.id, backend_name="fake")
    assert outcome.status == OutboxStatus.FAILED
