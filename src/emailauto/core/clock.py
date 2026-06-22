""" Clock for EmailAuto."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone


def utcnow() -> datetime:
    """Single source of "now" (UTC, timezone-aware).

    Call as ``clock.utcnow()`` rather than importing the function directly so tests can
    monkeypatch the clock to drive schedule-due logic deterministically.
    """
    return timezone.now()


def to_timezone(value: datetime | None, timezone_name: str) -> datetime | None:
    """Convert a stored UTC datetime to a named timezone for display at the edges."""
    if value is None:
        return None
    try:
        tzinfo = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        tzinfo = ZoneInfo("UTC")
    return value.astimezone(tzinfo)

