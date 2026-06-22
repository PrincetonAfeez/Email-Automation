""" Tasks for EmailAuto."""

from __future__ import annotations

from celery import shared_task

from emailauto.scheduling.dispatcher import dispatch_due_schedules


@shared_task(name="emailauto.scheduling.dispatch_due_schedules")
def dispatch_due_schedules_task():
    summary = dispatch_due_schedules(enqueue_celery=True)
    return summary.__dict__

