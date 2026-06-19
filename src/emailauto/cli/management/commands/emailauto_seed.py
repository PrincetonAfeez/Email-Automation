from __future__ import annotations

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

    def handle(self, *args, **options):
        if options["reset"]:
            if not options["noinput"]:
                raise CommandError("Destructive reset requires --noinput to confirm.")
            self._reset()
        FakeEmailBackend.clear()

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

        # A second, paused campaign with an interval schedule — visible on the Schedules page.
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
        self.stdout.write("  Visit / (login required), /schedules/, and /dlq/ to explore.")

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
