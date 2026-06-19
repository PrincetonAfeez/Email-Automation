from __future__ import annotations

import pytest

from emailauto.core.exceptions import InvalidStateTransition
from emailauto.core.states import OutboxStatus, assert_outbox_transition


def test_legal_normal_path():
    assert_outbox_transition(OutboxStatus.PENDING, OutboxStatus.ENQUEUED)
    assert_outbox_transition(OutboxStatus.ENQUEUED, OutboxStatus.CLAIMED)
    assert_outbox_transition(OutboxStatus.ENQUEUED, OutboxStatus.RETRY_SCHEDULED)
    assert_outbox_transition(OutboxStatus.CLAIMED, OutboxStatus.SENDING)
    assert_outbox_transition(OutboxStatus.SENDING, OutboxStatus.SENT)


def test_suppression_is_legal_from_claimed_but_not_from_sending():
    assert_outbox_transition(OutboxStatus.CLAIMED, OutboxStatus.SKIPPED_SUPPRESSED)
    with pytest.raises(InvalidStateTransition):
        assert_outbox_transition(OutboxStatus.SENDING, OutboxStatus.SKIPPED_SUPPRESSED)


def test_paused_or_throttled_release_is_legal_from_claimed():
    assert_outbox_transition(OutboxStatus.CLAIMED, OutboxStatus.RETRY_SCHEDULED)


def test_failed_and_dead_lettered_can_be_requeued():
    assert_outbox_transition(OutboxStatus.FAILED, OutboxStatus.REQUEUED)
    assert_outbox_transition(OutboxStatus.DEAD_LETTERED, OutboxStatus.REQUEUED)


def test_retry_scheduled_can_dead_letter():
    assert_outbox_transition(OutboxStatus.RETRY_SCHEDULED, OutboxStatus.DEAD_LETTERED)


@pytest.mark.parametrize(
    "current,target",
    [
        (OutboxStatus.SENT, OutboxStatus.SENDING),
        (OutboxStatus.SENT, OutboxStatus.RETRY_SCHEDULED),
        (OutboxStatus.DEAD_LETTERED, OutboxStatus.SENDING),
        (OutboxStatus.CANCELLED, OutboxStatus.SENDING),
        (OutboxStatus.SKIPPED_SUPPRESSED, OutboxStatus.SENDING),
    ],
)
def test_illegal_transitions_rejected(current, target):
    with pytest.raises(InvalidStateTransition):
        assert_outbox_transition(current, target)
