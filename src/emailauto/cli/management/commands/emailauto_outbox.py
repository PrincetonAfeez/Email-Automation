""" Inspect, send, retry, and cancel outbox rows. Maps to the scope's `emailauto outbox`."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import cancel_outbox, retry_outbox, send_outbox_email


class Command(BaseCommand):
    help = "Inspect, send, retry, and cancel outbox rows."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        list_parser = sub.add_parser("list")
        list_parser.add_argument("--status")
        list_parser.add_argument("--campaign")
        list_parser.add_argument("--limit", type=int, default=50)
        inspect = sub.add_parser("inspect")
        inspect.add_argument("--id", dest="outbox_id", type=int, required=True)
        send = sub.add_parser("send")
        send.add_argument("outbox_id", type=int)
        send.add_argument("--backend")
        retry = sub.add_parser("retry")
        retry.add_argument("--id", dest="outbox_id", type=int, required=True)
        cancel = sub.add_parser("cancel")
        cancel.add_argument("--id", dest="outbox_id", type=int, required=True)

    def handle(self, *args, **options):
        action = options["action"]
        if action == "send":
            outcome = send_outbox_email(options["outbox_id"], worker_id="cli", celery_task_id="cli", backend_name=options["backend"])
            self.stdout.write(self.style.SUCCESS(f"{outcome.outbox_id}: {outcome.status} {outcome.detail}"))
            return
        if action == "inspect":
            self._inspect(options["outbox_id"])
            return
        if action == "retry":
            try:
                row = retry_outbox(options["outbox_id"])
            except (EmailOutbox.DoesNotExist, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"Retry queued for {row.id}: {row.status}"))
            return
        if action == "cancel":
            try:
                row = cancel_outbox(options["outbox_id"])
            except (EmailOutbox.DoesNotExist, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"Cancelled {row.id}: {row.status}"))
            return

        rows = EmailOutbox.objects.select_related("campaign", "recipient").order_by("-updated_at")
        if options["status"]:
            rows = rows.filter(status=options["status"])
        if options["campaign"]:
            rows = rows.filter(campaign__name=options["campaign"])
        for row in rows[: options["limit"]]:
            self.stdout.write(f"{row.id}\t{row.campaign.name}\t{row.recipient.email}\t{row.status}\tattempts={row.attempt_count}")

    def _inspect(self, outbox_id: int) -> None:
        try:
            row = EmailOutbox.objects.select_related("campaign", "campaign_run", "recipient").get(pk=outbox_id)
        except EmailOutbox.DoesNotExist as exc:
            raise CommandError(f"No outbox row with id {outbox_id}.") from exc
        self.stdout.write(f"id            {row.id}")
        self.stdout.write(f"campaign      {row.campaign.name}")
        self.stdout.write(f"recipient     {row.recipient.email}")
        self.stdout.write(f"status        {row.status}")
        self.stdout.write(f"attempts      {row.attempt_count}/{row.max_attempts}")
        self.stdout.write(f"idempotency   {row.idempotency_key}")
        self.stdout.write(f"scheduled_for {row.scheduled_for}")
        self.stdout.write(f"next_attempt  {row.next_attempt_at}")
        self.stdout.write(f"last_error    {row.last_error}")
        for attempt in row.attempts.all():
            self.stdout.write(
                f"  attempt {attempt.attempt_number}: {attempt.provider_name} -> {attempt.result or 'started'} {attempt.error_code}"
            )
