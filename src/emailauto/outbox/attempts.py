""" Attempts for EmailAuto."""

from __future__ import annotations

from django.utils import timezone

from emailauto.core.results import SendResult
from emailauto.core.states import EventType
from emailauto.observability.events import record_event
from emailauto.outbox.models import EmailOutbox, EmailSendAttempt


def start_attempt(*, outbox: EmailOutbox, worker_id: str, celery_task_id: str, provider_name: str) -> EmailSendAttempt:
    max_existing = (
        EmailSendAttempt.objects.filter(outbox=outbox).order_by("-attempt_number").values_list("attempt_number", flat=True).first()
    ) or 0
    attempt = EmailSendAttempt.objects.create(
        outbox=outbox,
        attempt_number=max_existing + 1,
        worker_id=worker_id,
        celery_task_id=celery_task_id,
        provider_name=provider_name,
        started_at=timezone.now(),
    )
    record_event(
        EventType.SEND_ATTEMPT_STARTED,
        outbox=outbox,
        metadata={"attempt_number": attempt.attempt_number, "provider": provider_name},
    )
    return attempt


def complete_attempt(attempt: EmailSendAttempt, result: SendResult) -> EmailSendAttempt:
    attempt.completed_at = timezone.now()
    attempt.result = result.result
    attempt.error_code = result.error_code
    attempt.error_message = result.error_message
    attempt.provider_response_metadata = result.response_metadata
    attempt.save(update_fields=["completed_at", "result", "error_code", "error_message", "provider_response_metadata"])
    return attempt

