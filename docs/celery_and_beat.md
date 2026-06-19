# Celery And Beat

Celery tasks are execution messages. They do not contain full email payloads.

The worker task receives:

```text
outbox_id
```

The worker then reads the durable row, claims it, checks suppression, renders the template, applies throttling, sends through the configured provider, and records the result.

Celery Beat runs the dispatcher task periodically:

```text
emailauto.scheduling.dispatch_due_schedules
```

`django-celery-beat` is installed and configured as the Beat scheduler so periodic tasks can be stored and inspected in the Django database/admin.

Create the DB-backed dispatcher schedule with:

```powershell
python manage.py emailauto_beat ensure-dispatcher
```

Recommended local Windows worker:

```powershell
python -m celery -A emailauto.config worker -l info -P solo
```
