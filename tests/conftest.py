""" Conftest for EmailAuto."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.utils import timezone

from emailauto.campaigns.models import Campaign
from emailauto.core.states import CampaignStatus, ScheduleType
from emailauto.email_providers.fake import FakeEmailBackend
from emailauto.outbox.models import EmailOutbox
from emailauto.recipients.models import Recipient, RecipientList
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.scheduling.models import CampaignSchedule
from emailauto.templates.models import EmailTemplate


@pytest.fixture(autouse=True)
def safe_settings(settings):
    settings.EMAILAUTO_EMAIL_BACKEND = "fake"
    settings.EMAILAUTO_SEND_RATE_LIMIT = 1000
    settings.EMAILAUTO_CAMPAIGN_RATE_LIMIT = 1000
    settings.EMAILAUTO_MAX_SEND_ATTEMPTS = 3
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}
    # LocMemCache keyed by LOCATION is process-global; clear it so throttle counters and
    # cached stats never leak between tests.
    cache.clear()
    FakeEmailBackend.clear()


@pytest.fixture
def campaign_fixture(db):
    template = EmailTemplate.objects.create(
        name="Welcome",
        subject_template="Hi {{ recipient.name }}",
        body_template="Hello {{ first_name }} from {{ campaign.name }}",
        required_variables=["first_name", "recipient.email"],
    )
    recipient = Recipient.objects.create(email="person@example.com", name="Person", custom_fields={"first_name": "Ada"})
    recipient_list = RecipientList.objects.create(name="List")
    recipient_list.recipients.add(recipient)
    campaign = Campaign.objects.create(
        name="Launch",
        template=template,
        recipient_list=recipient_list,
        status=CampaignStatus.SCHEDULED,
    )
    return {
        "template": template,
        "recipient": recipient,
        "recipient_list": recipient_list,
        "campaign": campaign,
        "now": timezone.now(),
    }


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(username="admin", password="admin-pw", email="admin@example.com")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def admin_request(admin_user):
    """RequestFactory POST with messages middleware storage for admin action tests."""
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    request = RequestFactory().post("/admin/")
    request.user = admin_user
    request.session = "session"
    request._messages = FallbackStorage(request)  # noqa: SLF001
    return request


@pytest.fixture
def auth_client(client, django_user_model):
    """A test client logged in as an operator (web views require authentication + permission)."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    user = django_user_model.objects.create_user(username="operator", password="operator-pw")
    content_type = ContentType.objects.get_for_model(Campaign)
    permission = Permission.objects.get(content_type=content_type, codename="operate_campaign")
    user.user_permissions.add(permission)
    client.force_login(user)
    return client


@pytest.fixture
def dispatched_row(campaign_fixture):
    """A single EmailOutbox row for the fixture campaign, produced via the dispatcher."""
    CampaignSchedule.objects.create(
        campaign=campaign_fixture["campaign"],
        schedule_type=ScheduleType.ONE_TIME,
        send_at=timezone.now(),
    )
    dispatch_due_schedules()
    return EmailOutbox.objects.get()

