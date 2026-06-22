""" Subscription for EmailAuto."""

from __future__ import annotations

from emailauto.recipients.models import Recipient


def set_recipient_subscribed(email: str, *, subscribed: bool) -> Recipient:
    """Mark a recipient subscribed or unsubscribed by email address."""
    normalized = email.strip().lower()
    try:
        recipient = Recipient.objects.get(email=normalized)
    except Recipient.DoesNotExist as exc:
        raise ValueError(f"No recipient found for '{normalized}'.") from exc
    if recipient.subscribed != subscribed:
        recipient.subscribed = subscribed
        recipient.save(update_fields=["subscribed", "updated_at"])
    return recipient
