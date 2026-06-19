from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError, CommandParser

from emailauto.recipients.importers import import_recipients_from_csv
from emailauto.recipients.models import Recipient, RecipientList
from emailauto.recipients.suppression import suppress_email, unsuppress_email


class Command(BaseCommand):
    help = "Create, import, list, and suppress recipients."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        add = sub.add_parser("add")
        add.add_argument("--email", required=True)
        add.add_argument("--name", default="")
        add.add_argument("--fields", default="{}", help="JSON object for custom fields.")
        add.add_argument("--list", dest="list_name")
        imp = sub.add_parser("import")
        imp.add_argument("path")
        imp.add_argument("--list", dest="list_name")
        suppress = sub.add_parser("suppress")
        suppress.add_argument("--email", required=True)
        suppress.add_argument("--reason", required=True)
        unsuppress = sub.add_parser("unsuppress")
        unsuppress.add_argument("--email", required=True)
        list_parser = sub.add_parser("list")
        list_parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        action = options["action"]
        if action == "add":
            try:
                custom_fields = json.loads(options["fields"])
            except json.JSONDecodeError as exc:
                raise CommandError(f"--fields must be valid JSON: {exc}") from exc
            # Normalise before the lookup so mixed-case input matches the stored
            # (lowercased) email instead of triggering a duplicate-key error.
            email = options["email"].strip().lower()
            recipient, _ = Recipient.objects.update_or_create(
                email=email,
                defaults={"name": options["name"], "custom_fields": custom_fields},
            )
            if options["list_name"]:
                recipient_list, _ = RecipientList.objects.get_or_create(name=options["list_name"])
                recipient_list.recipients.add(recipient)
            self.stdout.write(self.style.SUCCESS(f"Recipient {recipient.id}: {recipient.email}"))
            return
        if action == "import":
            try:
                imported = import_recipients_from_csv(options["path"], list_name=options["list_name"])
            except (FileNotFoundError, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"Imported {len(imported)} recipients."))
            return
        if action == "suppress":
            entry = suppress_email(options["email"], reason=options["reason"])
            self.stdout.write(self.style.SUCCESS(f"Suppressed {entry.email}: {entry.reason}"))
            return
        if action == "unsuppress":
            removed = unsuppress_email(options["email"])
            if removed:
                self.stdout.write(self.style.SUCCESS(f"Removed suppression for {options['email'].strip().lower()}"))
            else:
                self.stdout.write(self.style.WARNING(f"No suppression entry for {options['email'].strip().lower()}"))
            return
        for recipient in Recipient.objects.order_by("email")[: options["limit"]]:
            self.stdout.write(f"{recipient.id}\t{recipient.email}\t{recipient.name}\tsubscribed={recipient.subscribed}")

