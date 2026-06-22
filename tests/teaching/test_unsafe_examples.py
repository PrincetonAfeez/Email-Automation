""" Test unsafe examples for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.teaching import (
    safe_demos,
    unsafe_cache_as_truth,
    unsafe_direct_send,
    unsafe_double_dispatch,
    unsafe_no_idempotency,
    unsafe_retry_duplicate,
)

# --- Safe demos exercise the real pipeline and reach the correct end state -----------


@pytest.mark.django_db
def test_safe_basic_demo_sends_once():
    result = safe_demos.run_basic()
    assert result["statuses"] == ["sent"]
    assert result["provider_sends"] == 1


@pytest.mark.django_db
def test_safe_idempotency_demo_sends_once():
    result = safe_demos.run_idempotency()
    assert result["outbox_rows"] == 1
    assert result["second_dispatch_created"] == 0
    assert result["provider_sends"] == 1


@pytest.mark.django_db
def test_safe_suppression_demo_skips_send():
    result = safe_demos.run_suppression()
    assert result["status"] == "skipped_suppressed"
    assert result["provider_sends"] == 0


@pytest.mark.django_db
def test_safe_rate_limit_demo_throttles():
    result = safe_demos.run_rate_limit()
    assert result["provider_sends"] == 1
    assert result["throttled"] == 2


@pytest.mark.django_db
def test_safe_demos_leave_no_rows():
    from emailauto.campaigns.models import Campaign
    from emailauto.outbox.models import EmailOutbox

    safe_demos.run_all()

    assert Campaign.objects.count() == 0
    assert EmailOutbox.objects.count() == 0


# --- Unsafe demos reproduce the failure they teach -----------------------------------


@pytest.mark.django_db
def test_unsafe_no_idempotency_creates_duplicate_rows():
    result = unsafe_no_idempotency.run_demo()
    assert result["outbox_rows"] == 2
    assert result["expected_with_idempotency_key"] == 1


@pytest.mark.django_db
def test_unsafe_double_dispatch_sends_twice():
    result = unsafe_double_dispatch.run_demo()
    assert result["provider_sends"] == 2
    assert result["expected_with_claim"] == 1


def test_unsafe_direct_send_sends_without_outbox():
    result = unsafe_direct_send.run_demo()
    assert result["sent_messages"] == 1


def test_unsafe_retry_duplicate_sends_twice():
    result = unsafe_retry_duplicate.run_demo()
    assert result["sent_messages"] == 2


def test_unsafe_cache_as_truth_makes_bad_decision():
    result = unsafe_cache_as_truth.run_demo()
    assert result["bad_decision"] == "send"
