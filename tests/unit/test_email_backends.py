""" Test email backends for EmailAuto."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

from emailauto.core.results import RenderedEmail
from emailauto.email_providers.smtp import SMTPEmailBackend


def _message(**overrides):
    defaults = {
        "to_email": "user@example.com",
        "subject": "Hello",
        "body": "Body",
        "body_format": "text",
        "from_email": "no-reply@example.com",
        "idempotency_key": "key-1",
        "metadata": {},
    }
    defaults.update(overrides)
    return RenderedEmail(**defaults)


@patch("emailauto.email_providers.smtp.smtplib.SMTP")
def test_smtp_auth_failure_is_permanent(mock_smtp, settings):
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_USERNAME = "user"
    settings.SMTP_PASSWORD = "pass"
    client = MagicMock()
    client.starttls.return_value = None
    client.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad auth")
    mock_smtp.return_value.__enter__.return_value = client

    result = SMTPEmailBackend().send_email(_message())

    assert result.result == "permanent_failure"
    assert result.error_code == "auth_failed"


@patch("emailauto.email_providers.smtp.smtplib.SMTP")
def test_smtp_timeout_is_transient(mock_smtp, settings):
    settings.SMTP_HOST = "smtp.example.com"
    mock_smtp.return_value.__enter__.side_effect = TimeoutError("timed out")

    result = SMTPEmailBackend().send_email(_message())

    assert result.result == "transient_failure"


def test_console_backend_prints_and_succeeds(capsys):
    from emailauto.email_providers.console import ConsoleEmailBackend

    result = ConsoleEmailBackend().send_email(_message())

    captured = capsys.readouterr()
    assert result.result == "success"
    assert "user@example.com" in captured.out
    assert "Idempotency-Key: key-1" in captured.out
