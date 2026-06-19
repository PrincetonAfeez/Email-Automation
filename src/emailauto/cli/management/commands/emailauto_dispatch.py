from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from emailauto.scheduling.dispatcher import dispatch_due_schedules


class Command(BaseCommand):
    help = "Dispatch due schedules and enqueue due outbox rows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--enqueue-celery", action="store_true", help="Publish Celery tasks after marking rows enqueued.")

    def handle(self, *args, **options):
        summary = dispatch_due_schedules(batch_size=options["batch_size"], enqueue_celery=options["enqueue_celery"])
        self.stdout.write(
            self.style.SUCCESS(
                f"schedules={summary.schedules_seen} runs={summary.runs_created} "
                f"outbox_created={summary.outbox_created} outbox_enqueued={summary.outbox_enqueued}"
            )
        )

