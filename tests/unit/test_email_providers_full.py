""" Test email providers full for EmailAuto."""

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


def test_smtp_not_configured(settings):
    settings.SMTP_HOST = ""
    result = SMTPEmailBackend().send_email(_message())
    assert result.error_code == "smtp_not_configured"


@patch("emailauto.email_providers.smtp.smtplib.SMTP_SSL")
def test_smtp_ssl_html_success(mock_ssl, settings):
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_USE_SSL = True
    settings.SMTP_USE_TLS = False
    settings.SMTP_USERNAME = "user"
    settings.SMTP_PASSWORD = "pass"
    client = MagicMock()
    client.send_message.return_value = {}
    mock_ssl.return_value.__enter__.return_value = client

    result = SMTPEmailBackend().send_email(_message(body="<p>Hi</p>", body_format="html"))
    assert result.result == "success"
    client.login.assert_called_once()


@patch("emailauto.email_providers.smtp.smtplib.SMTP")
def test_smtp_recipient_refused_is_permanent(mock_smtp, settings):
    settings.SMTP_HOST = "smtp.example.com"
    client = MagicMock()
    client.send_message.side_effect = smtplib.SMTPRecipientsRefused({})
    mock_smtp.return_value.__enter__.return_value = client

    result = SMTPEmailBackend().send_email(_message())
    assert result.result == "permanent_failure"
    assert result.error_code == "recipient_refused"


@patch("emailauto.email_providers.smtp.smtplib.SMTP")
def test_smtp_generic_exception_is_transient(mock_smtp, settings):
    settings.SMTP_HOST = "smtp.example.com"
    client = MagicMock()
    client.starttls.side_effect = smtplib.SMTPException("tls failed")
    mock_smtp.return_value.__enter__.return_value = client

    result = SMTPEmailBackend().send_email(_message())
    assert result.result == "transient_failure"
