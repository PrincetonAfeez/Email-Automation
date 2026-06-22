""" Test retry policy for EmailAuto."""

from __future__ import annotations

from emailauto.workers.retry_policy import retry_delay_seconds


def test_retry_policy_uses_exponential_backoff_with_cap():
    assert retry_delay_seconds(1) == 60
    assert retry_delay_seconds(2) == 120
    assert retry_delay_seconds(20) == 3600

