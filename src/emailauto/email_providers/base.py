from __future__ import annotations

from abc import ABC, abstractmethod

from django.conf import settings

from emailauto.core.results import RenderedEmail, SendResult


class EmailBackend(ABC):
    provider_name = "base"

    @abstractmethod
    def send_email(self, message: RenderedEmail) -> SendResult:
        raise NotImplementedError


def get_backend(name: str | None = None) -> EmailBackend:
    backend_name = (name or settings.EMAILAUTO_EMAIL_BACKEND).lower()
    if backend_name == "console":
        from emailauto.email_providers.console import ConsoleEmailBackend

        return ConsoleEmailBackend()
    if backend_name == "fake":
        from emailauto.email_providers.fake import FakeEmailBackend

        return FakeEmailBackend()
    if backend_name == "smtp":
        from emailauto.email_providers.smtp import SMTPEmailBackend

        return SMTPEmailBackend()
    raise ValueError(f"Unknown EMAIL_BACKEND: {backend_name}")

