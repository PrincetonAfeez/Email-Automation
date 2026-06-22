""" Test suppression for EmailAuto."""

from __future__ import annotations

import pytest

from emailauto.recipients.suppression import check_suppression, suppress_email


@pytest.mark.django_db
def test_unsubscribed_recipient_is_suppressed(campaign_fixture):
    recipient = campaign_fixture["recipient"]
    recipient.subscribed = False
    recipient.save()

    result = check_suppression(recipient)

    assert result.suppressed is True
    assert "unsubscribed" in result.reason


@pytest.mark.django_db
def test_suppression_entry_is_checked_case_insensitively(campaign_fixture):
    suppress_email("PERSON@example.com", reason="manual test")

    result = check_suppression(campaign_fixture["recipient"])

    assert result.suppressed is True
    assert result.reason == "manual test"

