from __future__ import annotations

from django.contrib import admin, messages

from emailauto.campaigns.models import Campaign
from emailauto.campaigns.services import cancel_campaign, pause_campaign, resume_campaign


@admin.action(description="Pause selected campaigns")
def pause_campaigns(modeladmin, request, queryset):
    count = 0
    for campaign in queryset:
        try:
            pause_campaign(campaign.id)
            count += 1
        except ValueError as exc:
            modeladmin.message_user(request, f"{campaign.name}: {exc}", level=messages.ERROR)
    if count:
        modeladmin.message_user(request, f"Paused {count} campaign(s).")


@admin.action(description="Resume selected campaigns")
def resume_campaigns(modeladmin, request, queryset):
    count = 0
    for campaign in queryset:
        try:
            resume_campaign(campaign.id)
            count += 1
        except ValueError as exc:
            modeladmin.message_user(request, f"{campaign.name}: {exc}", level=messages.ERROR)
    if count:
        modeladmin.message_user(request, f"Resumed {count} campaign(s).")


@admin.action(description="Cancel selected campaigns")
def cancel_campaigns(modeladmin, request, queryset):
    count = 0
    for campaign in queryset:
        try:
            cancel_campaign(campaign.id)
            count += 1
        except ValueError as exc:
            modeladmin.message_user(request, f"{campaign.name}: {exc}", level=messages.ERROR)
    if count:
        modeladmin.message_user(request, f"Cancelled {count} campaign(s).")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "template", "recipient_list", "status", "status_before_pause", "updated_at")
    list_filter = ("status",)
    search_fields = ("name",)
    readonly_fields = ("status", "status_before_pause", "created_at", "updated_at")
    actions = [pause_campaigns, resume_campaigns, cancel_campaigns]
