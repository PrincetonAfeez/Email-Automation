from __future__ import annotations

from emailauto.core.results import RenderedEmail
from emailauto.email_providers.fake import FakeEmailBackend


def run_demo() -> dict[str, int | str]:
    FakeEmailBackend.clear()
    backend = FakeEmailBackend()
    message = RenderedEmail(
        to_email="retry@example.com",
        subject="Unsafe retry",
        body="The task sent twice.",
        body_format="text",
        from_email="demo@example.com",
        idempotency_key="same-logical-email",
    )
    backend.send_email(message)
    backend.send_email(message)
    return {"sent_messages": len(FakeEmailBackend.sent_messages), "problem": "retry path sent without a claim/state check"}

