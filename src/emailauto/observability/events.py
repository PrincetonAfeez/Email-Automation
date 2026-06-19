from __future__ import annotations

from typing import Any

from emailauto.observability.logging import log_event
from emailauto.outbox.models import EmailEventLog, EmailOutbox


def record_event(
    event_type: str,
    *,
    outbox: EmailOutbox | None = None,
    campaign=None,
    campaign_run=None,
    recipient=None,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> EmailEventLog:
    if outbox is not None:
        campaign = campaign or outbox.campaign
        campaign_run = campaign_run or outbox.campaign_run
        recipient = recipient or outbox.recipient
    event = EmailEventLog.objects.create(
        event_type=event_type,
        campaign=campaign,
        campaign_run=campaign_run,
        outbox=outbox,
        recipient=recipient,
        message=message,
        metadata=metadata or {},
    )
    # The durable row above is the audit trail; this mirrors it to the structured log so
    # one outbox row can be traced through stdout/log aggregation as well as the DB.
    log_event(
        event_type,
        outbox_id=getattr(outbox, "id", None),
        campaign_id=getattr(campaign, "id", None),
        campaign_run_id=getattr(campaign_run, "id", None),
        recipient_id=getattr(recipient, "id", None),
        message=message or None,
    )
    return event

