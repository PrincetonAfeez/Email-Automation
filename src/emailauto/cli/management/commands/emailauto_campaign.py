""" Create, list, inspect, and control campaigns """

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from emailauto.campaigns.models import Campaign
from emailauto.campaigns.services import CREATABLE_CAMPAIGN_STATUSES, cancel_campaign, pause_campaign, resume_campaign, set_campaign_status
from emailauto.core.states import CampaignStatus
from emailauto.observability.stats import outbox_counts
from emailauto.recipients.models import RecipientList
from emailauto.scheduling.models import CampaignSchedule
from emailauto.templates.models import EmailTemplate


class Command(BaseCommand):
    help = "Create, list, inspect, and control campaigns."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        create = sub.add_parser("create")
        create.add_argument("--name", required=True)
        create.add_argument("--template", required=True)
        create.add_argument("--list", dest="list_name", required=True)
        create.add_argument("--status", choices=sorted(CREATABLE_CAMPAIGN_STATUSES), default=CampaignStatus.SCHEDULED)
        status = sub.add_parser("status")
        status.add_argument("campaign_id", type=int)
        status.add_argument("status", choices=[choice[0] for choice in CampaignStatus.CHOICES])
        for name in ("pause", "resume", "cancel"):
            action_parser = sub.add_parser(name)
            action_parser.add_argument("campaign", help="Campaign id or name.")
        inspect = sub.add_parser("inspect")
        inspect.add_argument("campaign", help="Campaign id or name.")
        sub.add_parser("list")

    def _resolve(self, ref: str) -> Campaign:
        try:
            if ref.isdigit():
                return Campaign.objects.get(pk=int(ref))
            return Campaign.objects.get(name=ref)
        except Campaign.DoesNotExist as exc:
            raise CommandError(f"No campaign matching '{ref}'.") from exc

    def handle(self, *args, **options):
        action = options["action"]
        if action == "create":
            try:
                template = EmailTemplate.objects.get(name=options["template"])
            except EmailTemplate.DoesNotExist as exc:
                raise CommandError(f"No template named '{options['template']}'.") from exc
            try:
                recipient_list = RecipientList.objects.get(name=options["list_name"])
            except RecipientList.DoesNotExist as exc:
                raise CommandError(f"No recipient list named '{options['list_name']}'.") from exc
            if Campaign.objects.filter(name=options["name"]).exists():
                raise CommandError(f"Campaign '{options['name']}' already exists.")
            campaign = Campaign.objects.create(
                name=options["name"],
                template=template,
                recipient_list=recipient_list,
                status=options["status"],
            )
            self.stdout.write(self.style.SUCCESS(f"Campaign {campaign.id}: {campaign.name}"))
            if not recipient_list.recipients.exists():
                self.stdout.write(self.style.WARNING("Warning: recipient list is empty — dispatch will create no outbox rows."))
            return
        if action == "status":
            try:
                campaign = set_campaign_status(options["campaign_id"], options["status"])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"{campaign.name} -> {campaign.status}"))
            return
        if action in {"pause", "resume", "cancel"}:
            campaign = self._resolve(options["campaign"])
            handler = {"pause": pause_campaign, "resume": resume_campaign, "cancel": cancel_campaign}[action]
            try:
                campaign = handler(campaign.id)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"{campaign.name} -> {campaign.status}"))
            return
        if action == "inspect":
            self._inspect(self._resolve(options["campaign"]))
            return
        for campaign in Campaign.objects.select_related("template", "recipient_list").order_by("name"):
            self.stdout.write(f"{campaign.id}\t{campaign.name}\t{campaign.status}\t{campaign.recipient_list.name}")

    def _inspect(self, campaign: Campaign) -> None:
        counts = outbox_counts(campaign_id=campaign.id)
        self.stdout.write(f"id        {campaign.id}")
        self.stdout.write(f"name      {campaign.name}")
        self.stdout.write(f"status    {campaign.status}")
        self.stdout.write(f"template  {campaign.template.name}")
        self.stdout.write(f"list      {campaign.recipient_list.name}")
        self.stdout.write("schedules:")
        for schedule in CampaignSchedule.objects.filter(campaign=campaign).order_by("id"):
            self.stdout.write(f"  {schedule.id}\t{schedule.schedule_type}\tenabled={schedule.enabled}\tnext={schedule.next_run_at}")
        self.stdout.write("outbox:")
        for key, value in counts.items():
            if value:
                self.stdout.write(f"  {key}\t{value}")
