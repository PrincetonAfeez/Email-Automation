from __future__ import annotations

import socket

from celery import shared_task

from emailauto.core.states import OutboxStatus
from emailauto.observability.logging import WORKER_LOGGER, get_logger
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import release_stale_outbox, send_outbox_email


@shared_task(bind=True, name="emailauto.send_outbox_email", acks_late=True, reject_on_worker_lost=True)
def send_outbox_email_task(self, outbox_id: int):
    worker_id = socket.gethostname() or "celery-worker"
    celery_task_id = self.request.id or ""
    try:
        outcome = send_outbox_email(outbox_id, worker_id=worker_id, celery_task_id=celery_task_id)
    except Exception as exc:
        current = EmailOutbox.objects.filter(pk=outbox_id).only("status").first()
        if current and current.status in {OutboxStatus.CLAIMED, OutboxStatus.SENDING}:
            release_stale_outbox(outbox_id, reason=f"worker error: {exc}")
        raise
    row = EmailOutbox.objects.filter(pk=outbox_id).only("campaign_id", "recipient_id", "attempt_count").first()
    get_logger(WORKER_LOGGER).info(
        "event=worker_send worker_id=%s celery_task_id=%s outbox_id=%s campaign_id=%s recipient_id=%s attempt_count=%s result=%s",
        worker_id,
        celery_task_id,
        outbox_id,
        getattr(row, "campaign_id", None),
        getattr(row, "recipient_id", None),
        getattr(row, "attempt_count", None),
        outcome.status,
    )
    return outcome.__dict__
