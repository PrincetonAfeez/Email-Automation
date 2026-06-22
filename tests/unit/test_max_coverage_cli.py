""" Test max coverage CLI for EmailAuto."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from emailauto.core.states import OutboxStatus


@pytest.mark.django_db
def test_outbox_retry_and_cancel_command_errors(dispatched_row):
    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])
    with pytest.raises(CommandError):
        call_command("emailauto_outbox", "retry", "--id", str(dispatched_row.id))
    with pytest.raises(CommandError):
        call_command("emailauto_outbox", "cancel", "--id", str(dispatched_row.id))


@pytest.mark.django_db
def test_outbox_inspect_with_attempts(dispatched_row):
    from emailauto.outbox.models import EmailSendAttempt

    EmailSendAttempt.objects.create(
        outbox=dispatched_row,
        attempt_number=1,
        provider_name="fake",
        started_at=dispatched_row.updated_at,
        result="success",
    )
    out = StringIO()
    call_command("emailauto_outbox", "inspect", "--id", str(dispatched_row.id), stdout=out)
    assert "attempt 1" in out.getvalue()


@pytest.mark.django_db
def test_template_create_validation_error():
    from django.core.exceptions import ValidationError

    with patch(
        "emailauto.cli.management.commands.emailauto_template.EmailTemplate.objects.update_or_create",
        side_effect=ValidationError("bad template"),
    ):
        with pytest.raises(CommandError):
            call_command(
                "emailauto_template",
                "create",
                "--name",
                "BadT",
                "--subject",
                "Hi",
                "--body",
                "Body",
            )


@pytest.mark.django_db
def test_campaign_inspect_with_schedules_and_counts(campaign_fixture):
    out = StringIO()
    call_command("emailauto_campaign", "inspect", str(campaign_fixture["campaign"].id), stdout=out)
    text = out.getvalue()
    assert "schedules:" in text
    assert "outbox:" in text


@pytest.mark.django_db
def test_campaign_create_empty_list_warning(campaign_fixture):
    campaign_fixture["recipient_list"].recipients.clear()
    out = StringIO()
    call_command(
        "emailauto_campaign",
        "create",
        "--name",
        "empty-list-campaign",
        "--template",
        campaign_fixture["template"].name,
        "--list",
        campaign_fixture["recipient_list"].name,
        stdout=out,
    )
    assert "Warning: recipient list is empty" in out.getvalue()
