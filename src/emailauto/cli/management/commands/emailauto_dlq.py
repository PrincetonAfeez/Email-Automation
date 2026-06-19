from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from emailauto.core.states import OutboxStatus
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import requeue_dead_letter


class Command(BaseCommand):
    help = "Inspect and requeue dead-lettered outbox rows."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("list")
        requeue = sub.add_parser("requeue")
        requeue.add_argument("outbox_id", type=int)

    def handle(self, *args, **options):
        if options["action"] == "requeue":
            try:
                row = requeue_dead_letter(options["outbox_id"])
            except (EmailOutbox.DoesNotExist, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"Requeued {row.id}: {row.status}"))
            return
        for row in EmailOutbox.objects.select_related("campaign", "recipient").filter(status=OutboxStatus.DEAD_LETTERED):
            self.stdout.write(f"{row.id}\t{row.campaign.name}\t{row.recipient.email}\t{row.last_error}")
