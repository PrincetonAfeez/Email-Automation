""" Test CLI commands for EmailAuto."""

from __future__ import annotations

import csv
import tempfile
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from emailauto.core.states import CampaignStatus, OutboxStatus


@pytest.mark.django_db
def test_campaign_list_pause_resume_cancel_status(campaign_fixture):
    out = StringIO()
    campaign = campaign_fixture["campaign"]
    call_command("emailauto_campaign", "list", stdout=out)
    assert campaign.name in out.getvalue()

    call_command("emailauto_campaign", "pause", str(campaign.id), stdout=out)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.PAUSED

    call_command("emailauto_campaign", "resume", campaign.name, stdout=out)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.SCHEDULED

    call_command("emailauto_campaign", "status", str(campaign.id), CampaignStatus.ACTIVE, stdout=out)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.ACTIVE

    call_command("emailauto_campaign", "cancel", str(campaign.id), stdout=out)
    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.CANCELLED


@pytest.mark.django_db
def test_campaign_resolve_errors():
    with pytest.raises(CommandError, match="No campaign matching"):
        call_command("emailauto_campaign", "inspect", "missing-name")


@pytest.mark.django_db
def test_campaign_create_duplicate_rejected(campaign_fixture):
    with pytest.raises(CommandError, match="already exists"):
        call_command(
            "emailauto_campaign",
            "create",
            "--name",
            campaign_fixture["campaign"].name,
            "--template",
            campaign_fixture["template"].name,
            "--list",
            campaign_fixture["recipient_list"].name,
        )


@pytest.mark.django_db
def test_outbox_list_filters_retry_cancel(dispatched_row):
    out = StringIO()
    call_command(
        "emailauto_outbox",
        "list",
        "--status",
        OutboxStatus.ENQUEUED,
        "--campaign",
        dispatched_row.campaign.name,
        "--limit",
        "10",
        stdout=out,
    )
    assert dispatched_row.recipient.email in out.getvalue()

    with patch("emailauto.scheduling.dispatcher.republish_enqueued_row", return_value=True):
        call_command("emailauto_outbox", "retry", "--id", str(dispatched_row.id), stdout=out)

    dispatched_row.status = OutboxStatus.PENDING
    dispatched_row.save(update_fields=["status"])
    call_command("emailauto_outbox", "cancel", "--id", str(dispatched_row.id), stdout=out)
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.CANCELLED


@pytest.mark.django_db
def test_outbox_inspect_missing_raises():
    with pytest.raises(CommandError, match="No outbox row"):
        call_command("emailauto_outbox", "inspect", "--id", "999999")


@pytest.mark.django_db
def test_recipients_import_suppress_unsuppress_list(campaign_fixture):
    out = StringIO()
    with tempfile.NamedTemporaryFile("w", newline="", suffix=".csv", delete=False, encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["email", "name", "first_name"])
        writer.writeheader()
        writer.writerow({"email": "csv@example.com", "name": "Csv", "first_name": "Csv"})
        path = handle.name

    call_command("emailauto_recipients", "import", path, "--list", "csv-list", stdout=out)
    call_command("emailauto_recipients", "suppress", "--email", "csv@example.com", "--reason", "test", stdout=out)
    call_command("emailauto_recipients", "unsuppress", "--email", "csv@example.com", stdout=out)
    call_command("emailauto_recipients", "list", "--limit", "5", stdout=out)
    assert "csv@example.com" in out.getvalue()


@pytest.mark.django_db
def test_recipients_unsuppress_missing_warns():
    out = StringIO()
    call_command("emailauto_recipients", "unsuppress", "--email", "nobody@example.com", stdout=out)
    assert "No suppression entry" in out.getvalue()


@pytest.mark.django_db
def test_recipients_import_missing_file():
    with pytest.raises(CommandError):
        call_command("emailauto_recipients", "import", "missing.csv")


@pytest.mark.django_db
def test_template_create_list_html_and_bad_json():
    out = StringIO()
    call_command(
        "emailauto_template",
        "create",
        "--name",
        "HtmlT",
        "--subject",
        "Hi",
        "--body",
        "<p>Hi</p>",
        "--format",
        "html",
        "--required",
        "[]",
        stdout=out,
    )
    call_command("emailauto_template", "list", stdout=out)
    assert "HtmlT" in out.getvalue()

    with pytest.raises(CommandError, match="valid JSON"):
        call_command("emailauto_template", "create", "--name", "x", "--subject", "s", "--body", "b", "--required", "bad")


@pytest.mark.django_db
def test_schedule_interval_cron_list(campaign_fixture):
    out = StringIO()
    cid = campaign_fixture["campaign"].id
    call_command("emailauto_schedule", "interval", "--campaign", str(cid), "--start-at", "2020-01-01T00:00:00Z", "--every", "1", "--period", "days", stdout=out)
    call_command("emailauto_schedule", "cron", "--campaign", str(cid), "--expression", "0 9 * * MON", stdout=out)
    call_command("emailauto_schedule", "list", stdout=out)
    assert "Launch" in out.getvalue()


@pytest.mark.django_db
def test_stats_campaign_and_dashboard(campaign_fixture):
    out = StringIO()
    call_command("emailauto_stats", "campaign", campaign_fixture["campaign"].name, stdout=out)
    assert "total" in out.getvalue()
    call_command("emailauto_stats", "dashboard", stdout=out)
    call_command("emailauto_stats", "--campaign-id", str(campaign_fixture["campaign"].id), stdout=out)


@pytest.mark.django_db
def test_stats_missing_campaign():
    with pytest.raises(CommandError, match="No campaign named"):
        call_command("emailauto_stats", "campaign", "missing")


@pytest.mark.django_db
def test_demo_all_and_unsafe(dispatched_row):
    out = StringIO()
    call_command("emailauto_demo", "all", stdout=out)
    assert out.getvalue()

    for name in ("unsafe-direct-send", "unsafe-no-idempotency", "unsafe-duplicate-retry", "unsafe-double-dispatch", "unsafe-cache-truth"):
        call_command("emailauto_demo", name, stdout=out)


@pytest.mark.django_db
def test_seed_reset_requires_noinput():
    with pytest.raises(CommandError, match="--noinput"):
        call_command("emailauto_seed", "--reset")


@pytest.mark.django_db
def test_seed_reset_and_operator_user():
    out = StringIO()
    call_command("emailauto_seed", "--reset", "--noinput", "--operator-password", "operator", stdout=out)
    from django.contrib.auth.models import User

    user = User.objects.get(username="operator")
    assert user.check_password("operator")
    assert user.has_perm("campaigns.operate_campaign")


@pytest.mark.django_db
def test_dlq_list_and_requeue(dispatched_row):
    from emailauto.core.results import SendResult
    from emailauto.email_providers.fake import FakeEmailBackend
    from emailauto.outbox.services import send_outbox_email

    dispatched_row.max_attempts = 1
    dispatched_row.save(update_fields=["max_attempts"])
    FakeEmailBackend.fail_next(dispatched_row.recipient.email, SendResult.transient_failure("fake", "timeout", "x"))
    send_outbox_email(dispatched_row.id, backend_name="fake")
    dispatched_row.refresh_from_db()
    assert dispatched_row.status == OutboxStatus.DEAD_LETTERED

    out = StringIO()
    call_command("emailauto_dlq", "list", stdout=out)
    assert dispatched_row.recipient.email in out.getvalue()
    call_command("emailauto_dlq", "requeue", str(dispatched_row.id), stdout=out)


@pytest.mark.django_db
def test_dlq_requeue_missing_raises():
    with pytest.raises(CommandError):
        call_command("emailauto_dlq", "requeue", "999999")
