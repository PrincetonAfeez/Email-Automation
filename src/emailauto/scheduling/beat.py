from __future__ import annotations

from django_celery_beat.models import IntervalSchedule, PeriodicTask


def ensure_dispatcher_periodic_task(*, every_seconds: int = 60, enabled: bool = True) -> PeriodicTask:
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=every_seconds,
        period=IntervalSchedule.SECONDS,
    )
    task, _ = PeriodicTask.objects.update_or_create(
        name="emailauto dispatch due schedules",
        defaults={
            "interval": interval,
            "task": "emailauto.scheduling.dispatch_due_schedules",
            "enabled": enabled,
        },
    )
    return task

