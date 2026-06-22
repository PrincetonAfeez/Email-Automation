""" States for EmailAuto."""

from __future__ import annotations

from dataclasses import dataclass

from .exceptions import InvalidStateTransition


@dataclass(frozen=True)
class Choice:
    value: str
    label: str

    def tuple(self) -> tuple[str, str]:
        return self.value, self.label


class CampaignStatus:
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PAUSED = "paused"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    CHOICES = [
        (DRAFT, "Draft"),
        (SCHEDULED, "Scheduled"),
        (PAUSED, "Paused"),
        (ACTIVE, "Active"),
        (COMPLETED, "Completed"),
        (CANCELLED, "Cancelled"),
    ]

    PAUSABLE = frozenset({SCHEDULED, ACTIVE})
    TRIGGERABLE = frozenset({SCHEDULED, ACTIVE})
    CANCELLABLE = frozenset({DRAFT, SCHEDULED, ACTIVE, PAUSED})


CAMPAIGN_TRANSITIONS: dict[str, set[str]] = {
    CampaignStatus.DRAFT: {CampaignStatus.SCHEDULED, CampaignStatus.CANCELLED},
    CampaignStatus.SCHEDULED: {CampaignStatus.ACTIVE, CampaignStatus.PAUSED, CampaignStatus.CANCELLED, CampaignStatus.COMPLETED},
    CampaignStatus.ACTIVE: {CampaignStatus.PAUSED, CampaignStatus.COMPLETED, CampaignStatus.CANCELLED},
    CampaignStatus.PAUSED: set(),  # resume restores status_before_pause via service layer
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.CANCELLED: set(),
}


def assert_campaign_transition(current: str, target: str) -> None:
    if target not in CAMPAIGN_TRANSITIONS.get(current, set()):
        raise InvalidStateTransition(f"Illegal Campaign transition: {current} -> {target}")


class CampaignRunStatus:
    PENDING = "pending"
    GENERATING_OUTBOX = "generating_outbox"
    OUTBOX_GENERATED = "outbox_generated"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    CHOICES = [
        (PENDING, "Pending"),
        (GENERATING_OUTBOX, "Generating outbox"),
        (OUTBOX_GENERATED, "Outbox generated"),
        (DISPATCHING, "Dispatching"),
        (DISPATCHED, "Dispatched"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
        (CANCELLED, "Cancelled"),
    ]

    TERMINAL = frozenset({COMPLETED, FAILED, CANCELLED})


CAMPAIGN_RUN_TRANSITIONS: dict[str, set[str]] = {
    CampaignRunStatus.PENDING: {CampaignRunStatus.GENERATING_OUTBOX, CampaignRunStatus.CANCELLED},
    CampaignRunStatus.GENERATING_OUTBOX: {CampaignRunStatus.OUTBOX_GENERATED, CampaignRunStatus.CANCELLED},
    CampaignRunStatus.OUTBOX_GENERATED: {
        CampaignRunStatus.DISPATCHING,
        CampaignRunStatus.COMPLETED,
        CampaignRunStatus.CANCELLED,
    },
    CampaignRunStatus.DISPATCHING: {
        CampaignRunStatus.DISPATCHED,
        CampaignRunStatus.COMPLETED,
        CampaignRunStatus.FAILED,
        CampaignRunStatus.CANCELLED,
    },
    CampaignRunStatus.DISPATCHED: {CampaignRunStatus.COMPLETED, CampaignRunStatus.FAILED, CampaignRunStatus.CANCELLED},
    CampaignRunStatus.COMPLETED: set(),
    CampaignRunStatus.FAILED: set(),
    CampaignRunStatus.CANCELLED: set(),
}


def assert_campaign_run_transition(current: str, target: str) -> None:
    if target not in CAMPAIGN_RUN_TRANSITIONS.get(current, set()):
        raise InvalidStateTransition(f"Illegal CampaignRun transition: {current} -> {target}")


class OutboxStatus:
    PENDING = "pending"
    ENQUEUED = "enqueued"
    CLAIMED = "claimed"
    SENDING = "sending"
    SENT = "sent"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    REQUEUED = "requeued"
    SKIPPED_SUPPRESSED = "skipped_suppressed"
    CANCELLED = "cancelled"

    CHOICES = [
        (PENDING, "Pending"),
        (ENQUEUED, "Enqueued"),
        (CLAIMED, "Claimed"),
        (SENDING, "Sending"),
        (SENT, "Sent"),
        (RETRY_SCHEDULED, "Retry scheduled"),
        (FAILED, "Failed"),
        (DEAD_LETTERED, "Dead-lettered"),
        (REQUEUED, "Requeued"),
        (SKIPPED_SUPPRESSED, "Skipped suppressed"),
        (CANCELLED, "Cancelled"),
    ]


class AttemptResult:
    SUCCESS = "success"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"

    CHOICES = [
        (SUCCESS, "Success"),
        (TRANSIENT_FAILURE, "Transient failure"),
        (PERMANENT_FAILURE, "Permanent failure"),
    ]


class ScheduleType:
    ONE_TIME = "one_time"
    RECURRING = "recurring"

    CHOICES = [(ONE_TIME, "One time"), (RECURRING, "Recurring")]


class EventType:
    SCHEDULED = "scheduled"
    OUTBOX_CREATED = "outbox_created"
    ENQUEUED = "enqueued"
    CLAIMED = "claimed"
    SEND_ATTEMPT_STARTED = "send_attempt_started"
    SENT = "sent"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    REQUEUED = "requeued"
    SKIPPED_SUPPRESSED = "skipped_suppressed"
    CANCELLED = "cancelled"
    DISPATCHED = "dispatched"
    CAMPAIGN_COMPLETED = "campaign_completed"
    OPERATOR_ACTION = "operator_action"

    CHOICES = [
        (SCHEDULED, "Scheduled"),
        (OUTBOX_CREATED, "Outbox created"),
        (ENQUEUED, "Enqueued"),
        (CLAIMED, "Claimed"),
        (SEND_ATTEMPT_STARTED, "Send attempt started"),
        (SENT, "Sent"),
        (RETRY_SCHEDULED, "Retry scheduled"),
        (FAILED, "Failed"),
        (DEAD_LETTERED, "Dead-lettered"),
        (REQUEUED, "Requeued"),
        (SKIPPED_SUPPRESSED, "Skipped suppressed"),
        (CANCELLED, "Cancelled"),
        (DISPATCHED, "Dispatched"),
        (CAMPAIGN_COMPLETED, "Campaign completed"),
        (OPERATOR_ACTION, "Operator action"),
    ]


OUTBOX_TRANSITIONS: dict[str, set[str]] = {
    OutboxStatus.PENDING: {OutboxStatus.ENQUEUED, OutboxStatus.CLAIMED, OutboxStatus.SKIPPED_SUPPRESSED, OutboxStatus.CANCELLED},
    OutboxStatus.ENQUEUED: {OutboxStatus.CLAIMED, OutboxStatus.CANCELLED, OutboxStatus.RETRY_SCHEDULED},
    OutboxStatus.REQUEUED: {OutboxStatus.ENQUEUED, OutboxStatus.CLAIMED, OutboxStatus.CANCELLED},
    # A pre-send check (suppression, cancelled/paused campaign) is resolved while the
    # row is still CLAIMED, before it ever moves to SENDING. RETRY_SCHEDULED lets a
    # claim holder release a row it cannot send yet (e.g. a paused campaign).
    OutboxStatus.CLAIMED: {
        OutboxStatus.SENDING,
        OutboxStatus.SENT,
        OutboxStatus.SKIPPED_SUPPRESSED,
        OutboxStatus.CANCELLED,
        OutboxStatus.RETRY_SCHEDULED,
    },
    OutboxStatus.SENDING: {OutboxStatus.SENT, OutboxStatus.RETRY_SCHEDULED, OutboxStatus.FAILED, OutboxStatus.DEAD_LETTERED, OutboxStatus.CANCELLED},
    # Retries are re-enqueued or claimed directly; post-attempt reconcile may also land here.
    OutboxStatus.RETRY_SCHEDULED: {
        OutboxStatus.ENQUEUED,
        OutboxStatus.CLAIMED,
        OutboxStatus.SENT,
        OutboxStatus.FAILED,
        OutboxStatus.DEAD_LETTERED,
        OutboxStatus.CANCELLED,
    },
    OutboxStatus.DEAD_LETTERED: {OutboxStatus.REQUEUED},
    # FAILED rows are terminal under automatic processing but an operator may requeue them.
    OutboxStatus.FAILED: {OutboxStatus.REQUEUED},
    OutboxStatus.SENT: set(),
    OutboxStatus.CANCELLED: set(),
    OutboxStatus.SKIPPED_SUPPRESSED: set(),
}


PROTECTED_OUTBOX_TARGETS = {
    OutboxStatus.SENDING,
    OutboxStatus.SENT,
    OutboxStatus.RETRY_SCHEDULED,
    OutboxStatus.FAILED,
    OutboxStatus.DEAD_LETTERED,
    OutboxStatus.SKIPPED_SUPPRESSED,
}


def assert_outbox_transition(current: str, target: str) -> None:
    if target not in OUTBOX_TRANSITIONS.get(current, set()):
        raise InvalidStateTransition(f"Illegal EmailOutbox transition: {current} -> {target}")

