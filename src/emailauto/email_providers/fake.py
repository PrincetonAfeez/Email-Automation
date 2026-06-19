from __future__ import annotations

from collections import defaultdict
from typing import ClassVar

from emailauto.core.results import RenderedEmail, SendResult
from emailauto.email_providers.base import EmailBackend


class FakeEmailBackend(EmailBackend):
    provider_name = "fake"
    sent_messages: ClassVar[list[RenderedEmail]] = []
    failures_by_email: ClassVar[dict[str, list[SendResult]]] = defaultdict(list)

    @classmethod
    def clear(cls) -> None:
        cls.sent_messages.clear()
        cls.failures_by_email.clear()

    @classmethod
    def fail_next(cls, email: str, result: SendResult) -> None:
        cls.failures_by_email[email.lower()].append(result)

    def send_email(self, message: RenderedEmail) -> SendResult:
        failures = self.failures_by_email[message.to_email.lower()]
        if failures:
            return failures.pop(0)
        self.sent_messages.append(message)
        return SendResult.success(self.provider_name, fake=True)

