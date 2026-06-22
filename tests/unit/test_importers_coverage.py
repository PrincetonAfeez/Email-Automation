""" Test importers coverage for EmailAuto."""

from __future__ import annotations

import csv

import pytest

from emailauto.recipients.importers import add_recipients_to_list, import_recipients_from_csv
from emailauto.recipients.models import Recipient, RecipientList


@pytest.mark.django_db
def test_import_csv_creates_and_updates(tmp_path):
    path = tmp_path / "recipients.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["email", "name", "first_name"])
        writer.writeheader()
        writer.writerow({"email": "one@example.com", "name": "One", "first_name": "O"})
        writer.writerow({"email": "two@example.com", "name": "", "first_name": "T"})
        writer.writerow({"email": "", "name": "Skip", "first_name": ""})

    imported = import_recipients_from_csv(path, list_name="csv-list")
    assert len(imported) == 2
    assert RecipientList.objects.filter(name="csv-list").exists()

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["email", "name", "first_name"])
        writer.writeheader()
        writer.writerow({"email": "one@example.com", "name": "One Updated", "first_name": "O2"})

    import_recipients_from_csv(path, list_name="csv-list")
    assert Recipient.objects.get(email="one@example.com").name == "One Updated"


@pytest.mark.django_db
def test_import_csv_missing_email_column(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name\nAda\n", encoding="utf-8")
    with pytest.raises(ValueError, match="email column"):
        import_recipients_from_csv(path)


@pytest.mark.django_db
def test_add_recipients_to_list_helper(campaign_fixture):
    recipient = campaign_fixture["recipient"]
    add_recipients_to_list([recipient], campaign_fixture["recipient_list"])
    assert campaign_fixture["recipient_list"].recipients.filter(pk=recipient.pk).exists()
