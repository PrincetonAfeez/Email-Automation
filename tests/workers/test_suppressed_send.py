from __future__ import annotations

import pytest

from emailauto.campaigns.services import cancel_campaign, pause_campaign
from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import send_outbox_email
from emailauto.recipients.suppression import suppress_email


@pytest.mark.django_db
def test_suppressed_recipient_is_skipped_not_sent(dispatched_row):
    # Regression test for the suppression-at-send bug: a suppressed recipient must end in
    # skipped_suppressed (a legal claimed->skipped transition), never crash from sending.
    suppress_email(dispatched_row.recipient.email, reason="manual block")

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.SKIPPED_SUPPRESSED
    assert dispatched_row.status == OutboxStatus.SKIPPED_SUPPRESSED
    assert dispatched_row.failed_at is None  # suppression is not a failure
    assert len(FakeEmailBackend.sent_messages) == 0


@pytest.mark.django_db
def test_unsubscribed_recipient_is_skipped(dispatched_row):
    dispatched_row.recipient.subscribed = False
    dispatched_row.recipient.save(update_fields=["subscribed"])

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    assert outcome.status == OutboxStatus.SKIPPED_SUPPRESSED
    assert len(FakeEmailBackend.sent_messages) == 0


@pytest.mark.django_db
def test_cancelled_campaign_row_is_cancelled(dispatched_row):
    cancel_campaign(dispatched_row.campaign_id)

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.CANCELLED
    assert dispatched_row.status == OutboxStatus.CANCELLED
    assert len(FakeEmailBackend.sent_messages) == 0


@pytest.mark.django_db
def test_paused_campaign_holds_without_consuming_attempt(dispatched_row):
    pause_campaign(dispatched_row.campaign_id)

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.attempt_count == 0  # a paused hold must not burn an attempt
    assert len(FakeEmailBackend.sent_messages) == 0
