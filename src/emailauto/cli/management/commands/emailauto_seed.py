""" Populate the database with sample data (campaigns, runs, outbox rows in mixed states, schedules) so the web UI is explorable. Uses the fake backend — never sends real email. Maps to the scope's `emailauto seed`."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from emailauto.campaigns.models import Campaign
from emailauto.core.results import SendResult
from emailauto.core.states import CampaignStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailEventLog, EmailOutbox, EmailSendAttempt
from emailauto.outbox.services import send_outbox_email
from emailauto.recipients.models import Recipient, RecipientList, SuppressionEntry
from emailauto.recipients.suppression import suppress_email
from emailauto.scheduling.dispatcher import dispatch_due_schedules, reconcile_campaign_runs
from emailauto.scheduling.models import CampaignRun, CampaignSchedule
from emailauto.templates.models import EmailTemplate


class Command(BaseCommand):
    help = (
        "Populate the database with sample data (campaigns, runs, outbox rows in mixed "
        "states, schedules) so the web UI is explorable. Uses the fake backend — never "
        "sends real email."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reset", action="store_true", help="Delete all existing emailauto data first.")
        parser.add_argument("--noinput", action="store_true", help="Required with --reset to confirm destructive reset.")
        parser.add_argument(
            "--create-operator",
            action="store_true",
            default=True,
            help="Create or update the demo operator account (default: on).",
        )
        parser.add_argument(
            "--no-create-operator",
            dest="create_operator",
            action="store_false",
            help="Skip creating the demo operator account.",
        )
        parser.add_argument(
            "--operator-password",
            default="",
            help="Password for the demo operator (default: EMAILAUTO_SEED_OPERATOR_PASSWORD env or a random value).",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            if not options["noinput"]:
                raise CommandError("Destructive reset requires --noinput to confirm.")
            self._reset()
        FakeEmailBackend.clear()
        operator_password = ""
        if options["create_operator"]:
            operator_password = self._ensure_operator_user(options["operator_password"])

        template = EmailTemplate.objects.create(
            name="seed-welcome",
            subject_template="Welcome {{ recipient.name }}",
            body_template="Hello {{ first_name }}, welcome to {{ campaign.name }}.",
            required_variables=["first_name"],
        )

        recipient_list = RecipientList.objects.create(name="seed-customers")
        names = ["Ada", "Linus", "Grace", "Alan", "Edsger"]
        recipients = []
        for index, name in enumerate(names):
            recipient = Recipient.objects.create(email=f"seed{index}@example.com", name=name, custom_fields={"first_name": name})
            recipient_list.recipients.add(recipient)
            recipients.append(recipient)
        suppress_email(recipients[-1].email, reason="seed unsubscribe")  # Edsger -> skipped_suppressed

        campaign = Campaign.objects.create(
            name="seed-spring-sale",
            template=template,
            recipient_list=recipient_list,
            status=CampaignStatus.SCHEDULED,
        )
        # A due one-time schedule (will dispatch now) and an upcoming recurring one.
        CampaignSchedule.objects.create(campaign=campaign, schedule_type=ScheduleType.ONE_TIME, send_at=timezone.now() - timedelta(minutes=1))
        CampaignSchedule.objects.create(
            campaign=campaign,
            schedule_type=ScheduleType.RECURRING,
            cron_expression="0 9 * * MON",
            send_at=timezone.now() + timedelta(days=1),
        )

        # A second, paused campaign with a disabled interval schedule (cannot be enabled while paused).
        paused = Campaign.objects.create(
            name="seed-weekly-digest",
            template=template,
            recipient_list=recipient_list,
            status=CampaignStatus.PAUSED,
        )
        CampaignSchedule.objects.create(
            campaign=paused,
            schedule_type=ScheduleType.RECURRING,
            interval_every=1,
            interval_period=CampaignSchedule.IntervalPeriod.DAYS,
            send_at=timezone.now() + timedelta(hours=6),
            enabled=False,
        )

        dispatch_due_schedules()
        rows = list(EmailOutbox.objects.filter(campaign=campaign).select_related("recipient").order_by("id"))

        retry_email = recipients[2].email  # Grace -> retry_scheduled
        deadletter_email = recipients[3].email  # Alan -> dead_lettered
        for row in rows:
            email = row.recipient.email
            if email == retry_email:
                FakeEmailBackend.fail_next(email, SendResult.transient_failure("fake", "timeout", "seed transient"))
            elif email == deadletter_email:
                row.max_attempts = 1
                row.save(update_fields=["max_attempts"])
                FakeEmailBackend.fail_next(email, SendResult.transient_failure("fake", "timeout", "seed exhausted"))
            send_outbox_email(row.id, backend_name="fake")

        reconcile_campaign_runs()

        self.stdout.write(self.style.SUCCESS("Seeded sample data:"))
        self.stdout.write(f"  campaigns={Campaign.objects.count()} schedules={CampaignSchedule.objects.count()} runs={CampaignRun.objects.count()}")
        self.stdout.write(f"  outbox rows={EmailOutbox.objects.count()} attempts={EmailSendAttempt.objects.count()} events={EmailEventLog.objects.count()}")
        if options["create_operator"]:
            self.stdout.write("  Operator login: username=operator (has campaigns.operate_campaign)")
            self.stdout.write(f"  Operator password: {operator_password}")
        self.stdout.write("  Visit / (login required), /schedules/, and /dlq/ to explore.")

    def _ensure_operator_user(self, password: str = "") -> str:
        from django.contrib.auth.models import Permission, User
        from django.contrib.contenttypes.models import ContentType

        resolved = password or os.getenv("EMAILAUTO_SEED_OPERATOR_PASSWORD") or secrets.token_urlsafe(12)
        user, created = User.objects.get_or_create(username="operator", defaults={"email": "operator@example.com"})
        if created or not user.check_password(resolved):
            user.set_password(resolved)
            user.save(update_fields=["password"])
        content_type = ContentType.objects.get_for_model(Campaign)
        permission = Permission.objects.get(content_type=content_type, codename="operate_campaign")
        user.user_permissions.add(permission)
        return resolved

    def _reset(self) -> None:
        EmailSendAttempt.objects.all().delete()
        EmailEventLog.objects.all().delete()
        EmailOutbox.objects.all().delete()
        CampaignRun.objects.all().delete()
        CampaignSchedule.objects.all().delete()
        Campaign.objects.all().delete()
        RecipientList.objects.all().delete()
        SuppressionEntry.objects.all().delete()
        Recipient.objects.all().delete()
        EmailTemplate.objects.all().delete()
