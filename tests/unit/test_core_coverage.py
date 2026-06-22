""" Test core coverage for EmailAuto."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from emailauto.core import clock
from emailauto.core.exceptions import InvalidStateTransition, MissingTemplateVariable, StaleClaimToken, TemplateRenderError
from emailauto.core.results import RenderedEmail, SendResult
from emailauto.core.states import CampaignStatus, Choice, OutboxStatus, assert_campaign_transition, assert_outbox_transition
from emailauto.email_providers.base import get_backend
from emailauto.observability.logging import EVENT_LOGGER, WORKER_LOGGER, get_logger, log_event


def test_clock_utcnow_and_timezones():
    now = clock.utcnow()
    assert now.tzinfo is not None
    assert clock.to_timezone(None, "UTC") is None
    converted = clock.to_timezone(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), "America/New_York")
    assert converted is not None
    fallback = clock.to_timezone(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), "Not/A_Real_Zone")
    assert fallback is not None


def test_state_helpers_and_exceptions():
    assert Choice("a", "A").tuple() == ("a", "A")
    assert_campaign_transition(CampaignStatus.ACTIVE, CampaignStatus.PAUSED)
    with pytest.raises(InvalidStateTransition):
        assert_campaign_transition(CampaignStatus.COMPLETED, CampaignStatus.ACTIVE)
    assert_outbox_transition(OutboxStatus.PENDING, OutboxStatus.ENQUEUED)
    with pytest.raises(InvalidStateTransition):
        assert_outbox_transition(OutboxStatus.SENT, OutboxStatus.PENDING)

    assert "x" in str(StaleClaimToken("x"))
    assert "field" in str(MissingTemplateVariable("field"))
    assert str(TemplateRenderError("bad")) == "bad"


def test_send_result_and_rendered_email():
    ok = SendResult.success("fake")
    assert ok.result == "success"
    transient = SendResult.transient_failure("smtp", "timeout", "slow")
    assert transient.result == "transient_failure"
    permanent = SendResult.permanent_failure("smtp", "auth", "bad")
    assert permanent.result == "permanent_failure"
    rendered = RenderedEmail(
        to_email="a@example.com",
        subject="Hi",
        body="Body",
        body_format="text",
        from_email="noreply@example.com",
        idempotency_key="k",
        metadata={},
    )
    assert rendered.to_email == "a@example.com"


def test_get_backend_variants(settings):
    assert get_backend("console").provider_name == "console"
    assert get_backend("fake").provider_name == "fake"
    settings.SMTP_HOST = "smtp.example.com"
    assert get_backend("smtp").provider_name == "smtp"
    with pytest.raises(ValueError, match="Unknown EMAIL_BACKEND"):
        get_backend("nope")


def test_log_event_respects_log_level(monkeypatch):
    logger = logging.getLogger(EVENT_LOGGER)
    calls: list[str] = []

    def capture_info(msg, *args):
        calls.append(msg % args if args else msg)

    monkeypatch.setattr(logger, "info", capture_info)
    monkeypatch.setattr(logger, "isEnabledFor", lambda level: level >= logging.WARNING)
    log_event("ignored", outbox_id=1)
    assert not calls

    monkeypatch.setattr(logger, "isEnabledFor", lambda level: level >= logging.INFO)
    log_event("visible", outbox_id=2, campaign_id=3)
    assert any("event=visible" in line for line in calls)
    assert get_logger(WORKER_LOGGER).name == WORKER_LOGGER
