from __future__ import annotations

from dataclasses import dataclass

from emailauto.recipients.models import Recipient, SuppressionEntry


@dataclass(frozen=True)
class SuppressionCheck:
    suppressed: bool
    reason: str = ""


def check_suppression(recipient: Recipient) -> SuppressionCheck:
    if not recipient.subscribed:
        return SuppressionCheck(True, "recipient is unsubscribed")
    entry = SuppressionEntry.objects.filter(email__iexact=recipient.email).first()
    if entry:
        return SuppressionCheck(True, entry.reason)
    return SuppressionCheck(False)


def suppress_email(email: str, *, reason: str, source: str = SuppressionEntry.Source.MANUAL) -> SuppressionEntry:
    entry, _ = SuppressionEntry.objects.update_or_create(
        email=email.strip().lower(),
        defaults={"reason": reason, "source": source},
    )
    return entry


def unsuppress_email(email: str) -> int:
    """Remove an email from the suppression list. Returns the number of rows deleted."""
    deleted, _ = SuppressionEntry.objects.filter(email=email.strip().lower()).delete()
    return deleted

