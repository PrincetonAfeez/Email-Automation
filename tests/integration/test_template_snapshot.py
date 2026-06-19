from __future__ import annotations

import pytest

from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.services import send_outbox_email


@pytest.mark.django_db
def test_send_renders_from_snapshot_not_live_template(dispatched_row):
    # Edit the live template AFTER the outbox row was created.
    template = dispatched_row.template
    template.subject_template = "CHANGED {{ recipient.name }}"
    template.body_template = "CHANGED BODY {{ first_name }}"
    template.save()

    send_outbox_email(dispatched_row.id, backend_name="fake")

    message = FakeEmailBackend.sent_messages[-1]
    # The queued row is immutable: it used the snapshot captured at creation, not the edit.
    assert "CHANGED" not in message.subject
    assert "CHANGED" not in message.body
    assert message.subject == "Hi Person"
    assert "Hello Ada from Launch" in message.body


@pytest.mark.django_db
def test_snapshot_required_variables_are_captured(dispatched_row):
    assert dispatched_row.required_variables_snapshot == ["first_name", "recipient.email"]
