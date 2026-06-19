from __future__ import annotations

from emailauto.core.results import RenderedEmail, SendResult
from emailauto.email_providers.base import EmailBackend


class ConsoleEmailBackend(EmailBackend):
    provider_name = "console"

    def send_email(self, message: RenderedEmail) -> SendResult:
        print("=" * 72)
        print(f"From: {message.from_email}")
        print(f"To: {message.to_email}")
        print(f"Subject: {message.subject}")
        print(f"Idempotency-Key: {message.idempotency_key}")
        print("-" * 72)
        print(message.body)
        print("=" * 72)
        return SendResult.success(self.provider_name, delivered=False, console=True)

