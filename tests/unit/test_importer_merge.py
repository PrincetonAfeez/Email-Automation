""" Test importer merge for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.recipients.importers import import_recipients_from_csv
from emailauto.recipients.models import Recipient


@pytest.mark.django_db
def test_reimport_preserves_name_and_merges_custom_fields(tmp_path):
    first = tmp_path / "first.csv"
    first.write_text("email,name,plan\nx@example.com,Xavier,pro\n", encoding="utf-8")
    import_recipients_from_csv(str(first))

    # Second import omits name and adds a new field.
    second = tmp_path / "second.csv"
    second.write_text("email,region\nx@example.com,EU\n", encoding="utf-8")
    import_recipients_from_csv(str(second))

    recipient = Recipient.objects.get(email="x@example.com")
    assert recipient.name == "Xavier"  # preserved, not blanked
    assert recipient.custom_fields.get("plan") == "pro"  # preserved
    assert recipient.custom_fields.get("region") == "EU"  # merged in


@pytest.mark.django_db
def test_import_lowercases_email(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text("email,name\nUPPER@Example.com,Up\n", encoding="utf-8")
    import_recipients_from_csv(str(path))
    assert Recipient.objects.filter(email="upper@example.com").exists()
