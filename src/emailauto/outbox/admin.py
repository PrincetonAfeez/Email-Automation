from __future__ import annotations

from django.contrib import admin

from emailauto.core.states import OutboxStatus
from emailauto.outbox.models import EmailEventLog, EmailOutbox, EmailSendAttempt
from emailauto.outbox.services import requeue_dead_letter


class EmailSendAttemptInline(admin.TabularInline):
    model = EmailSendAttempt
    extra = 0
    readonly_fields = (
        "attempt_number",
        "worker_id",
        "celery_task_id",
        "provider_name",
        "started_at",
        "completed_at",
        "result",
        "error_code",
        "error_message",
    )
    can_delete = False


@admin.action(description="Requeue selected dead-lettered rows")
def requeue_dead_letters(modeladmin, request, queryset):
    count = 0
    for outbox in queryset.filter(status=OutboxStatus.DEAD_LETTERED):
        requeue_dead_letter(outbox.id)
        count += 1
    modeladmin.message_user(request, f"Requeued {count} rows.")


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "campaign", "recipient", "status", "attempt_count", "scheduled_for", "next_attempt_at")
    list_filter = ("status", "campaign")
    search_fields = ("recipient__email", "campaign__name", "idempotency_key", "last_error")
    readonly_fields = ("idempotency_key", "claim_token", "lock_version", "created_at", "updated_at")
    inlines = [EmailSendAttemptInline]
    actions = [requeue_dead_letters]


@admin.register(EmailSendAttempt)
class EmailSendAttemptAdmin(admin.ModelAdmin):
    list_display = ("outbox", "attempt_number", "provider_name", "result", "started_at", "completed_at")
    list_filter = ("result", "provider_name")
    search_fields = ("outbox__recipient__email", "error_code", "error_message")


@admin.register(EmailEventLog)
class EmailEventLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "campaign", "outbox", "created_at")
    list_filter = ("event_type",)
    search_fields = ("message", "outbox__recipient__email", "campaign__name")
    readonly_fields = ("created_at",)

