""" Admin for EmailAuto."""

from __future__ import annotations

from django.contrib import admin

from emailauto.recipients.models import Recipient, RecipientList, SuppressionEntry


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "subscribed", "updated_at")
    list_filter = ("subscribed",)
    search_fields = ("email", "name")


@admin.register(RecipientList)
class RecipientListAdmin(admin.ModelAdmin):
    list_display = ("name", "recipient_count", "updated_at")
    search_fields = ("name", "description")
    filter_horizontal = ("recipients",)

    @admin.display(description="Recipients")
    def recipient_count(self, obj: RecipientList) -> int:
        return obj.recipients.count()


@admin.register(SuppressionEntry)
class SuppressionEntryAdmin(admin.ModelAdmin):
    list_display = ("email", "reason", "source", "created_at")
    list_filter = ("source",)
    search_fields = ("email", "reason")

