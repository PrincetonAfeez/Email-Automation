""" Test rate limit for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import send_outbox_email
from emailauto.workers.throttling import allow_send, check_send, record_send


def test_record_send_enforces_global_limit(settings):
    settings.EMAILAUTO_SEND_RATE_LIMIT = 2
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 0
    assert check_send().allowed
    record_send()
    assert check_send().allowed
    record_send()
    assert not check_send().allowed


def test_campaign_limit_checked_before_global(settings):
    settings.EMAILAUTO_SEND_RATE_LIMIT = 2
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    record_send(campaign_id=1)
    assert not check_send(campaign_id=1).allowed
    assert check_send(campaign_id=2).allowed
    record_send(campaign_id=2)
    assert not check_send().allowed


def test_allow_send_still_checks_and_records(settings):
    settings.EMAILAUTO_SEND_RATE_LIMIT = 1
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 0
    assert allow_send().allowed
    assert not allow_send().allowed


@pytest.mark.django_db
def test_throttled_send_reschedules_without_consuming_attempt(dispatched_row, settings):
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    record_send(campaign_id=dispatched_row.campaign_id)

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.attempt_count == 0
    assert len(FakeEmailBackend.sent_messages) == 0


@pytest.mark.django_db
def test_failed_send_does_not_consume_throttle_slot(dispatched_row, settings):
    from emailauto.core.results import SendResult

    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "temporary"))

    send_outbox_email(dispatched_row.id, backend_name="fake")

    assert check_send(campaign_id=dispatched_row.campaign_id).allowed
