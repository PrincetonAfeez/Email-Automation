""" Unsafe direct send for EmailAuto."""

from __future__ import annotations

from emailauto.core.results import RenderedEmail
from emailauto.email_providers.fake import FakeEmailBackend


def run_demo() -> dict[str, int | str]:
    FakeEmailBackend.clear()
    backend = FakeEmailBackend()
    message = RenderedEmail(
        to_email="learner@example.com",
        subject="Unsafe direct send",
        body="This bypasses the outbox.",
        body_format="text",
        from_email="demo@example.com",
        idempotency_key="not-recorded",
    )
    backend.send_email(message)
    return {"sent_messages": len(FakeEmailBackend.sent_messages), "problem": "no durable outbox row or audit trail"}

