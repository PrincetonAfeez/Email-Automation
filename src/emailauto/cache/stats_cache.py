from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from emailauto.observability.stats import outbox_counts


def _stats_key(campaign_id: int | None = None) -> str:
    return f"stats:campaign:{campaign_id or 'all'}"


def get_dashboard_stats(*, campaign_id: int | None = None) -> dict[str, int]:
    key = _stats_key(campaign_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    stats = outbox_counts(campaign_id=campaign_id)
    cache.set(key, stats, timeout=settings.EMAILAUTO_DASHBOARD_CACHE_TTL)
    return stats


def invalidate_dashboard_stats(*, campaign_id: int | None = None) -> None:
    cache.delete(_stats_key(campaign_id))
    cache.delete(_stats_key(None))

