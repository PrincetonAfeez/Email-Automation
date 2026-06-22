""" Audit for EmailAuto."""

from __future__ import annotations

from typing import Any

from emailauto.core.states import EventType
from emailauto.observability.events import record_event


def record_operator_action(
    *,
    user,
    action: str,
    campaign=None,
    outbox=None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a durable audit record for an operator mutation."""
    payload = {"action": action, "username": getattr(user, "username", ""), "user_id": getattr(user, "pk", None)}
    if metadata:
        payload.update(metadata)
    record_event(
        EventType.OPERATOR_ACTION,
        outbox=outbox,
        campaign=campaign or (outbox.campaign if outbox is not None else None),
        message=action,
        metadata=payload,
    )
