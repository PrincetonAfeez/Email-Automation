from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache


@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    reason: str = ""


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


def allow_send(*, campaign_id: int | None = None) -> ThrottleDecision:
    # Check the narrower per-campaign limit first so a campaign-throttled send does not
    # consume a global slot it never used.
    if campaign_id is not None and not _increment_window(f"throttle:campaign:{campaign_id}", settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT):
        return ThrottleDecision(False, "campaign send rate limit exceeded")
    if not _increment_window("throttle:global", settings.EMAILAUTO_SEND_RATE_LIMIT):
        return ThrottleDecision(False, "global send rate limit exceeded")
    return ThrottleDecision(True)


def throttle_status() -> dict[str, int | bool]:
    """Read-only view of the global send-rate window for dashboards (never decides sends)."""
    limit = settings.EMAILAUTO_SEND_RATE_LIMIT
    used = cache.get("throttle:global") or 0
    return {
        "global_limit": limit,
        "global_used": int(used),
        "global_remaining": max(limit - int(used), 0) if limit > 0 else 0,
        "throttled": limit > 0 and int(used) >= limit,
    }

