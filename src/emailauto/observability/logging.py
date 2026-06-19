from __future__ import annotations

import logging
from typing import Any

EVENT_LOGGER = "emailauto.events"
WORKER_LOGGER = "emailauto.worker"


def get_logger(name: str = "emailauto") -> logging.Logger:
    return logging.getLogger(name)


def _format_fields(fields: dict[str, Any]) -> str:
    return " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)


def log_event(event_type: str, *, logger_name: str = EVENT_LOGGER, **fields: Any) -> None:
    """Emit one structured, greppable log line for a lifecycle event.

    Mirrors the durable EmailEventLog row so an operator can trace one outbox row
    through the logs (event=... outbox_id=... campaign_id=... recipient_id=...).
    """
    logger = logging.getLogger(logger_name)
    # Skip building the field string entirely when the level would discard the record.
    if not logger.isEnabledFor(logging.INFO):
        return
    logger.info("event=%s %s", event_type, _format_fields(fields))
