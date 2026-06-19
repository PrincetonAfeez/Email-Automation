# Demo Script

All demos use the fake/console backend and never send real email.

## Fastest path: built-in demos

Each safe demo builds a tiny campaign, runs the real pipeline, prints what happened, and
rolls back (nothing is persisted):

```powershell
python manage.py emailauto_demo list
python manage.py emailauto_demo basic         # 1: create -> schedule -> dispatch -> send -> stats
python manage.py emailauto_demo scheduler     # 2: recurring schedule advances its next run
python manage.py emailauto_demo idempotency   # 5: duplicate dispatch + duplicate task -> one send
python manage.py emailauto_demo suppression   # 6: suppressed recipient -> skipped_suppressed, no send
python manage.py emailauto_demo retry         # 4: transient failure -> retry_scheduled
python manage.py emailauto_demo rate-limit     # throttled sends -> retry_scheduled, not lost
python manage.py emailauto_demo all
```

Unsafe teaching demos (intentionally reproduce the failure the architecture prevents):

```powershell
python manage.py emailauto_demo unsafe-direct-send
python manage.py emailauto_demo unsafe-no-idempotency
python manage.py emailauto_demo unsafe-duplicate-retry
python manage.py emailauto_demo unsafe-double-dispatch
python manage.py emailauto_demo unsafe-cache-truth
```

## Explore the web UI with sample data

Populate mixed-state data (sent / retry_scheduled / dead_lettered / skipped_suppressed),
then browse it:

```powershell
python manage.py emailauto_seed --reset
python manage.py createsuperuser   # if you have not already
python manage.py runserver
```

Then visit (login required): `/` (dashboard + live stats, throughput, rate-limit status),
`/schedules/` (upcoming & recurring sends), a campaign page (its runs), a run page
(per-run stats), and `/dlq/` (requeue dead letters).

## Manual walk-through (matches the scope's 8 demos)

### 1. Basic campaign
```powershell
python manage.py emailauto_template create --name welcome --subject "Hi {{ recipient.name }}" --body "Hello {{ first_name }}" --required "[\"first_name\"]"
python manage.py emailauto_recipients add --email ada@example.com --name Ada --fields "{\"first_name\":\"Ada\"}" --list customers
python manage.py emailauto_campaign create --name spring-sale --template welcome --list customers --status scheduled
python manage.py emailauto_schedule one-time --campaign 1 --send-at 2020-01-01T00:00:00Z
python manage.py emailauto_dispatch
python manage.py emailauto_outbox send 1 --backend fake
python manage.py emailauto_stats campaign spring-sale
```

### 2. Scheduler & dispatcher
Create a recurring schedule, then let Beat run the dispatcher:
```powershell
python manage.py emailauto_schedule cron --campaign 1 --expression "0 9 * * MON"
python manage.py emailauto_beat ensure-dispatcher
python -m celery -A emailauto.config beat -l info
```

### 3. Concurrent workers
Start Redis and two workers, dispatch with `--enqueue-celery`, and confirm each row is
claimed once and sent once:
```powershell
python -m celery -A emailauto.config worker -l info -P solo
python manage.py emailauto_dispatch --enqueue-celery
```

### 4. Retry & DLQ
Force a transient failure (or `max_attempts=1`), watch `retry_scheduled` then
`dead_lettered`, then requeue:
```powershell
python manage.py emailauto_dlq list
python manage.py emailauto_dlq requeue <id>
```

### 5. Idempotency
Dispatch the same occurrence twice and run the same task twice — one `CampaignRun`, one
outbox row per recipient, one provider send. (`emailauto_demo idempotency` proves it.)

### 6. Suppression
```powershell
python manage.py emailauto_recipients suppress --email ada@example.com --reason manual
python manage.py emailauto_outbox send <id> --backend fake   # -> skipped_suppressed, no send
```

### 7. Dashboard & cache
Run the server, open `/`, watch the HTMX panels (stats, throughput, rate-limit) poll
without full reloads. Cached stats may lag the DB; the DB always wins for correctness.

### 8. Unsafe demos
Run the unsafe demos above and compare their duplicate/incorrect outcomes to the
protected outbox flow.
