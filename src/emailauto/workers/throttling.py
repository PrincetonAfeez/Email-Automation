""" Throttling for EmailAuto."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    reason: str = ""


def _window_count(key: str) -> int:
    return int(cache.get(key) or 0)


def _increment_window(key: str, limit: int, window_seconds: int = 60) -> bool:
    if limit <= 0:
        return True
    cache.add(key, 0, timeout=window_seconds)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    return count <= limit


def check_send(*, campaign_id: int | None = None) -> ThrottleDecision:
    """Read-only rate-limit check (does not consume a send slot)."""
    campaign_limit = settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT
    if campaign_id is not None and campaign_limit > 0:
        used = _window_count(f"throttle:campaign:{campaign_id}")
        if used >= campaign_limit:
            return ThrottleDecision(False, "campaign send rate limit exceeded")
    global_limit = settings.EMAILAUTO_SEND_RATE_LIMIT
    if global_limit > 0 and _window_count("throttle:global") >= global_limit:
        return ThrottleDecision(False, "global send rate limit exceeded")
    return ThrottleDecision(True)


def record_send(*, campaign_id: int | None = None) -> None:
    """Consume one send slot after a successful provider delivery."""
    if campaign_id is not None:
        _increment_window(f"throttle:campaign:{campaign_id}", settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT)
    _increment_window("throttle:global", settings.EMAILAUTO_SEND_RATE_LIMIT)


def allow_send(*, campaign_id: int | None = None) -> ThrottleDecision:
    """Check and consume a send slot in one step (used by teaching demos)."""
    decision = check_send(campaign_id=campaign_id)
    if decision.allowed:
        record_send(campaign_id=campaign_id)
    return decision


def throttle_status() -> dict[str, int | bool]:
    """Read-only view of the global send-rate window for dashboards (never decides sends)."""
    limit = settings.EMAILAUTO_SEND_RATE_LIMIT
    used = _window_count("throttle:global")
    return {
        "global_limit": limit,
        "global_used": used,
        "global_remaining": max(limit - used, 0) if limit > 0 else 0,
        "throttled": limit > 0 and used >= limit,
    }
