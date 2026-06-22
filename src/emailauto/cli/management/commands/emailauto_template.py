""" Create and list email templates. Maps to the scope's `emailauto template`."""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from emailauto.templates.models import EmailTemplate


class Command(BaseCommand):
    help = "Create and list email templates."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        create = sub.add_parser("create")
        create.add_argument("--name", required=True)
        create.add_argument("--subject", required=True)
        create.add_argument("--body", required=True)
        create.add_argument("--format", choices=["text", "html"], default="text")
        create.add_argument("--required", default="[]", help="JSON list of required variables.")
        sub.add_parser("list")

    def handle(self, *args, **options):
        if options["action"] == "create":
            try:
                required = json.loads(options["required"])
            except json.JSONDecodeError as exc:
                raise CommandError(f"--required must be valid JSON: {exc}") from exc
            try:
                template, _ = EmailTemplate.objects.update_or_create(
                    name=options["name"],
                    defaults={
                        "subject_template": options["subject"],
                        "body_template": options["body"],
                        "body_format": options["format"],
                        "required_variables": required,
                    },
                )
            except ValidationError as exc:
                raise CommandError("; ".join(exc.messages)) from exc
            self.stdout.write(self.style.SUCCESS(f"Template {template.id}: {template.name}"))
            return
        for template in EmailTemplate.objects.order_by("name"):
            self.stdout.write(f"{template.id}\t{template.name}\t{template.body_format}")

