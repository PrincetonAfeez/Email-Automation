""" Campaign model """

from __future__ import annotations

from django.db import models

from emailauto.core.states import CampaignStatus


class Campaign(models.Model):
    name = models.CharField(max_length=150, unique=True)
    template = models.ForeignKey("email_templates.EmailTemplate", on_delete=models.PROTECT, related_name="campaigns")
    recipient_list = models.ForeignKey("recipients.RecipientList", on_delete=models.PROTECT, related_name="campaigns")
    status = models.CharField(max_length=30, choices=CampaignStatus.CHOICES, default=CampaignStatus.DRAFT)
    status_before_pause = models.CharField(max_length=30, choices=CampaignStatus.CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        permissions = [("operate_campaign", "Can operate campaigns from the dashboard")]

    def __str__(self) -> str:
        return self.name

