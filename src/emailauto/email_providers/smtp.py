from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

from django.conf import settings
from django.utils.html import strip_tags

from emailauto.core.results import RenderedEmail, SendResult
from emailauto.email_providers.base import EmailBackend


class SMTPEmailBackend(EmailBackend):
    provider_name = "smtp"

    def send_email(self, message: RenderedEmail) -> SendResult:
        if not settings.SMTP_HOST:
            return SendResult.permanent_failure(self.provider_name, "smtp_not_configured", "SMTP_HOST is required for real sending.")

        email_message = EmailMessage()
        email_message["From"] = message.from_email
        email_message["To"] = message.to_email
        email_message["Subject"] = message.subject
        email_message["X-Idempotency-Key"] = message.idempotency_key
        if message.body_format == "html":
            email_message.set_content(html.unescape(strip_tags(message.body)))
            email_message.add_alternative(message.body, subtype="html")
        else:
            email_message.set_content(message.body)

        try:
            if settings.SMTP_USE_SSL:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as client:
                    if settings.SMTP_USERNAME:
                        client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    response = client.send_message(email_message)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as client:
                    if settings.SMTP_USE_TLS:
                        client.starttls()
                    if settings.SMTP_USERNAME:
                        client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    response = client.send_message(email_message)
        except (TimeoutError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as exc:
            return SendResult.transient_failure(self.provider_name, type(exc).__name__, str(exc))
        except smtplib.SMTPRecipientsRefused as exc:
            return SendResult.permanent_failure(self.provider_name, "recipient_refused", str(exc))
        except smtplib.SMTPAuthenticationError as exc:
            return SendResult.permanent_failure(self.provider_name, "auth_failed", str(exc))
        except smtplib.SMTPException as exc:
            return SendResult.transient_failure(self.provider_name, type(exc).__name__, str(exc))
        refused_recipients = sorted((response or {}).keys())
        return SendResult.success(self.provider_name, refused_recipients=refused_recipients)
