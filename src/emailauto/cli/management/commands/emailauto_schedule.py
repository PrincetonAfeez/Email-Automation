from __future__ import annotations

from datetime import UTC

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from emailauto.campaigns.models import Campaign
from emailauto.core.states import ScheduleType
from emailauto.scheduling.models import CampaignSchedule


def parse_dt(value: str):
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid datetime: {value}")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed.astimezone(UTC)


def _get_campaign(campaign_id: int) -> Campaign:
    try:
        return Campaign.objects.get(pk=campaign_id)
    except Campaign.DoesNotExist as exc:
        raise CommandError(f"No campaign with id {campaign_id}.") from exc


def _parse_dt_or_error(value: str):
    try:
        return parse_dt(value)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc


class Command(BaseCommand):
    help = "Create and list campaign schedules."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        one = sub.add_parser("one-time")
        one.add_argument("--campaign", type=int, required=True)
        one.add_argument("--send-at", required=True)
        interval = sub.add_parser("interval")
        interval.add_argument("--campaign", type=int, required=True)
        interval.add_argument("--start-at", required=True)
        interval.add_argument("--every", type=int, required=True)
        interval.add_argument("--period", choices=["minutes", "hours", "days"], required=True)
        cron = sub.add_parser("cron")
        cron.add_argument("--campaign", type=int, required=True)
        cron.add_argument("--start-at")
        cron.add_argument("--expression", required=True)
        sub.add_parser("list")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "one-time":
            campaign = _get_campaign(options["campaign"])
            schedule = CampaignSchedule.objects.create(campaign=campaign, schedule_type=ScheduleType.ONE_TIME, send_at=_parse_dt_or_error(options["send_at"]))
            self.stdout.write(self.style.SUCCESS(f"Schedule {schedule.id}: one-time {schedule.send_at}"))
            return
        if action == "interval":
            campaign = _get_campaign(options["campaign"])
            schedule = CampaignSchedule.objects.create(
                campaign=campaign,
                schedule_type=ScheduleType.RECURRING,
                send_at=_parse_dt_or_error(options["start_at"]),
                interval_every=options["every"],
                interval_period=options["period"],
            )
            self.stdout.write(self.style.SUCCESS(f"Schedule {schedule.id}: every {schedule.interval_every} {schedule.interval_period}"))
            return
        if action == "cron":
            campaign = _get_campaign(options["campaign"])
            start = _parse_dt_or_error(options["start_at"]) if options["start_at"] else timezone.now()
            try:
                schedule = CampaignSchedule.objects.create(
                    campaign=campaign,
                    schedule_type=ScheduleType.RECURRING,
                    send_at=start,
                    cron_expression=options["expression"],
                )
            except ValidationError as exc:
                raise CommandError(f"Invalid cron expression: {'; '.join(exc.messages)}") from exc
            self.stdout.write(self.style.SUCCESS(f"Schedule {schedule.id}: cron {schedule.cron_expression}"))
            return
        for schedule in CampaignSchedule.objects.select_related("campaign").order_by("id"):
            next_local = schedule.next_run_at_local
            self.stdout.write(
                f"{schedule.id}\t{schedule.campaign.name}\t{schedule.schedule_type}\tenabled={schedule.enabled}\t"
                f"next={next_local.isoformat() if next_local else None} ({schedule.timezone_name})"
            )
