from __future__ import annotations

from django.contrib import admin

from emailauto.templates.models import EmailTemplate


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "body_format", "updated_at")
    search_fields = ("name", "subject_template", "body_template")
    list_filter = ("body_format",)

