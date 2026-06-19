from __future__ import annotations

from django.contrib import admin

from emailauto.scheduling.dispatcher import create_run_and_outbox
from emailauto.scheduling.models import CampaignRun, CampaignSchedule


@admin.action(description="Generate outbox for selected due schedules")
def generate_outbox(modeladmin, request, queryset):
    total = 0
    for schedule in queryset:
        _run, created, _run_created = create_run_and_outbox(schedule)
        total += created
    modeladmin.message_user(request, f"Created {total} outbox rows.")


@admin.register(CampaignSchedule)
class CampaignScheduleAdmin(admin.ModelAdmin):
    list_display = ("campaign", "schedule_type", "send_at", "next_run_at", "next_run_local", "timezone_name", "enabled")
    list_filter = ("schedule_type", "enabled")
    search_fields = ("campaign__name", "cron_expression")
    actions = [generate_outbox]

    @admin.display(description="Next run (local)")
    def next_run_local(self, obj: CampaignSchedule):
        return obj.next_run_at_local


@admin.register(CampaignRun)
class CampaignRunAdmin(admin.ModelAdmin):
    list_display = ("campaign", "schedule", "scheduled_for", "status", "generated_at")
    list_filter = ("status",)
    search_fields = ("campaign__name", "run_key")

