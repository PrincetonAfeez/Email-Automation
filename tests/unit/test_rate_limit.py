from __future__ import annotations

import pytest

from emailauto.core.states import OutboxStatus
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import send_outbox_email
from emailauto.workers.throttling import allow_send


def test_allow_send_enforces_global_limit(settings):
    settings.EMAILAUTO_SEND_RATE_LIMIT = 2
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 0  # unlimited
    assert allow_send().allowed
    assert allow_send().allowed
    assert not allow_send().allowed


def test_campaign_limit_checked_before_global(settings):
    # A campaign-throttled send must not consume a global slot. With global=2/campaign=1:
    settings.EMAILAUTO_SEND_RATE_LIMIT = 2
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    assert allow_send(campaign_id=1).allowed  # campaign1=1, global=1
    assert not allow_send(campaign_id=1).allowed  # campaign rejects before touching global
    # Because the rejected call never touched the global counter (still 1), a second
    # campaign can still take the remaining global slot. Had global been checked first,
    # it would already be exhausted here.
    assert allow_send(campaign_id=2).allowed  # campaign2=1, global=2


@pytest.mark.django_db
def test_throttled_send_reschedules_without_consuming_attempt(dispatched_row, settings):
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1
    # Consume the campaign's only slot so the actual send is throttled.
    allow_send(campaign_id=dispatched_row.campaign_id)

    outcome = send_outbox_email(dispatched_row.id, backend_name="fake")

    dispatched_row.refresh_from_db()
    assert outcome.status == OutboxStatus.RETRY_SCHEDULED
    assert dispatched_row.attempt_count == 0  # throttling is a delay, not an attempt
    assert len(FakeEmailBackend.sent_messages) == 0
