""" Test CLI smoke for EmailAuto."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_cli_version_prints_package_version():
    out = StringIO()
    call_command("emailauto_version", stdout=out)
    try:
        expected = version("email-automation-capstone")
    except PackageNotFoundError:
        expected = "unknown"
    assert out.getvalue().strip() == expected


@pytest.mark.django_db
def test_cli_demo_list_and_stats_smoke():
    out = StringIO()
    call_command("emailauto_demo", "list", stdout=out)
    assert "unsafe-direct-send" in out.getvalue()

    out = StringIO()
    call_command("emailauto_stats", stdout=out)
    assert "total" in out.getvalue()


@pytest.mark.django_db
def test_cli_end_to_end_flow(settings):
    settings.EMAILAUTO_EMAIL_BACKEND = "fake"
    out = StringIO()
    call_command("emailauto_template", "create", "--name", "cliT", "--subject", "Hi {{ recipient.name }}", "--body", "Body", stdout=out)
    call_command("emailauto_recipients", "add", "--email", "cli@example.com", "--name", "Cli", "--list", "cliL", stdout=out)
    call_command("emailauto_campaign", "create", "--name", "cliC", "--template", "cliT", "--list", "cliL", "--status", "scheduled", stdout=out)

    from emailauto.campaigns.models import Campaign
    from emailauto.outbox.models import EmailOutbox

    campaign_id = Campaign.objects.get(name="cliC").id
    call_command("emailauto_schedule", "one-time", "--campaign", str(campaign_id), "--send-at", "2020-01-01T00:00:00Z", stdout=out)
    call_command("emailauto_dispatch", stdout=out)

    row_id = EmailOutbox.objects.get().id
    call_command("emailauto_outbox", "send", str(row_id), "--backend", "fake", stdout=out)

    inspect = StringIO()
    call_command("emailauto_campaign", "inspect", "cliC", stdout=inspect)
    assert "cliC" in inspect.getvalue()

    stats = StringIO()
    call_command("emailauto_stats", "campaign", "cliC", stdout=stats)
    assert "sent\t1" in stats.getvalue()


@pytest.mark.django_db
def test_cli_seed_populates_mixed_states():
    out = StringIO()
    call_command("emailauto_seed", stdout=out)
    assert "Seeded sample data" in out.getvalue()

    from emailauto.core.states import OutboxStatus
    from emailauto.outbox.models import EmailOutbox

    assert EmailOutbox.objects.count() == 5
    assert EmailOutbox.objects.filter(status=OutboxStatus.DEAD_LETTERED).exists()
    assert EmailOutbox.objects.filter(status=OutboxStatus.SKIPPED_SUPPRESSED).exists()


# --- U4: bad input yields a clean CommandError, never a raw traceback ----------------


@pytest.mark.django_db
def test_cli_missing_template_reference_is_clean_error():
    with pytest.raises(CommandError):
        call_command("emailauto_campaign", "create", "--name", "x", "--template", "missing", "--list", "missing")


@pytest.mark.django_db
def test_cli_missing_campaign_reference_is_clean_error():
    with pytest.raises(CommandError):
        call_command("emailauto_schedule", "one-time", "--campaign", "999999", "--send-at", "2020-01-01T00:00:00Z")


@pytest.mark.django_db
def test_cli_malformed_cron_is_clean_error(campaign_fixture):
    with pytest.raises(CommandError):
        call_command("emailauto_schedule", "cron", "--campaign", str(campaign_fixture["campaign"].id), "--expression", "0 9 * * NOPE")


@pytest.mark.django_db
def test_cli_bad_datetime_is_clean_error(campaign_fixture):
    with pytest.raises(CommandError):
        call_command("emailauto_schedule", "one-time", "--campaign", str(campaign_fixture["campaign"].id), "--send-at", "not-a-date")


@pytest.mark.django_db
def test_cli_bad_json_fields_is_clean_error():
    with pytest.raises(CommandError):
        call_command("emailauto_recipients", "add", "--email", "x@example.com", "--fields", "{not json}")

