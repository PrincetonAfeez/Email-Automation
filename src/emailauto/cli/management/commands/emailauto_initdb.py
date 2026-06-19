from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Initialise the database (apply migrations). Maps to the scope's `emailauto init-db`."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--noinput", action="store_true", help="Do not prompt for input.")

    def handle(self, *args, **options):
        call_command("migrate", interactive=not options["noinput"])
        self.stdout.write(self.style.SUCCESS("Database initialised."))
