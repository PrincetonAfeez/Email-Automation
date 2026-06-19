from __future__ import annotations

from datetime import datetime, timedelta

from emailauto.core import clock


def retry_delay_seconds(attempt_count: int, *, base_seconds: int = 60, max_seconds: int = 3600) -> int:
    exponent = max(attempt_count - 1, 0)
    return min(base_seconds * (2**exponent), max_seconds)


def next_retry_at(attempt_count: int) -> datetime:
    return clock.utcnow() + timedelta(seconds=retry_delay_seconds(attempt_count))

