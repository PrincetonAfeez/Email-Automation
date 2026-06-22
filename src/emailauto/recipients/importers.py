""" Importers for EmailAuto."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from django.db import transaction

from emailauto.recipients.models import Recipient, RecipientList


def import_recipients_from_csv(path: str | Path, *, list_name: str | None = None) -> list[Recipient]:
    imported: list[Recipient] = []
    recipient_list = None
    if list_name:
        recipient_list, _ = RecipientList.objects.get_or_create(name=list_name)
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "email" not in (reader.fieldnames or []):
            raise ValueError("CSV must include an email column.")
        with transaction.atomic():
            for row in reader:
                email = (row.pop("email") or "").strip().lower()
                if not email:
                    continue
                name = (row.pop("name", "") or "").strip()
                custom_fields = {key: value for key, value in row.items() if key and value not in (None, "")}
                recipient, created = Recipient.objects.get_or_create(
                    email=email,
                    defaults={"name": name, "custom_fields": custom_fields},
                )
                if not created:
                    # Re-import updates rather than clobbers: keep an existing name when the
                    # new row omits it, and merge custom fields instead of replacing them.
                    update_fields: list[str] = []
                    if name and name != recipient.name:
                        recipient.name = name
                        update_fields.append("name")
                    if custom_fields:
                        merged = {**(recipient.custom_fields or {}), **custom_fields}
                        if merged != recipient.custom_fields:
                            recipient.custom_fields = merged
                            update_fields.append("custom_fields")
                    if update_fields:
                        recipient.save(update_fields=[*update_fields, "updated_at"])
                imported.append(recipient)
            if recipient_list:
                recipient_list.recipients.add(*imported)
    return imported


def add_recipients_to_list(recipients: Iterable[Recipient], recipient_list: RecipientList) -> None:
    recipient_list.recipients.add(*list(recipients))

