from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from emailauto.scheduling.beat import ensure_dispatcher_periodic_task


class Command(BaseCommand):
    help = "Create or update django-celery-beat dispatcher periodic tasks."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=["ensure-dispatcher"])
        parser.add_argument("--every-seconds", type=int, default=60)
        parser.add_argument("--disabled", action="store_true")

    def handle(self, *args, **options):
        task = ensure_dispatcher_periodic_task(every_seconds=options["every_seconds"], enabled=not options["disabled"])
        self.stdout.write(self.style.SUCCESS(f"PeriodicTask {task.id}: {task.name} enabled={task.enabled}"))
