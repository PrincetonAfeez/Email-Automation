""" Celery configuration for EmailAuto."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emailauto.config.settings")

app = Celery("emailauto")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# The periodic dispatcher schedule lives in the database (django-celery-beat), created
# via `python manage.py emailauto_beat ensure-dispatcher`. We deliberately do NOT also
# declare it in app.conf.beat_schedule: the DatabaseScheduler would sync that static
# entry into a second PeriodicTask and run the dispatcher twice per interval.

