# Architecture Decision Record
## App — Email Automation
**Email Workflow Group | Document 1 of 5**
**Status: Accepted**

## Context

Email Automation is a Django/Celery capstone for scheduled campaign email workflows. It includes templates, recipients, recipient lists, suppressions, campaigns, one-time and recurring schedules, campaign runs, an explicit database outbox, Celery execution, retries, dead-letter handling, Redis-backed dashboard/cache/throttling helpers, Django Admin, HTMX operator views, and management commands.

The central architectural requirement is reliability. Email sends should not depend on an in-memory queue, cache counter, or Celery message as the durable source of truth. The durable workflow state belongs in Django models.

## Decision Drivers

- Avoid accidental real email sending in demos.
- Make every intended send inspectable and recoverable.
- Prevent duplicate sends when Celery tasks are duplicated or republished.
- Preserve queued email content even if templates change later.
- Support retries, dead-letter handling, and operator intervention.
- Keep cache and broker data out of the correctness path.
- Provide CLI, admin, and web surfaces without duplicating business logic.

## Decisions

### Use a database outbox as the workflow core

Schedules generate `CampaignRun` rows and `EmailOutbox` rows. Celery tasks carry only the outbox ID. Workers must claim the row before sending. This makes the database the referee for all send behavior.

### Store immutable template snapshots on each outbox row

`EmailOutbox` stores subject, body, required variables, and body format snapshots. Workers render from the snapshot, not the live `EmailTemplate`, so editing a template after dispatch does not alter queued mail.

### Use deterministic idempotency keys

Outbox rows are keyed by campaign, campaign run, and recipient. Repeated dispatch ticks or concurrent dispatchers cannot create duplicate rows for the same intended email.

### Require claim tokens for protected transitions

Workers claim rows by moving them to `claimed` and assigning a token. Protected post-claim transitions require that token unless a recovery path explicitly forces reconciliation.

### Check suppression and throttling before provider send

Suppression, cancelled campaign, paused campaign, and rate-limit checks occur while the row is still `claimed`. The system only moves to `sending` after it knows the row is sendable.

### Treat Celery and Redis as helpers

Celery transports execution. Redis supports broker/cache/throttle behavior. Neither is the durable source of truth.

### Default to safe providers

The default backend is `console`; `fake` supports tests/demos. SMTP requires deliberate configuration.

## Consequences

Positive consequences:

- Every send intent has a durable row, state, attempts, and audit trail.
- Duplicate Celery tasks are safe because only one claim can win.
- Stale claims can be recovered.
- Operators can retry, cancel, or requeue through shared services.
- Suppression is checked at send time.
- Dashboard/cache data is clearly read-side convenience.

Trade-offs:

- More models and services than a direct SMTP script.
- Celery and Redis increase operational complexity.
- SQLite is only suitable for local demos; production should use PostgreSQL.
- Snapshot behavior means queued content intentionally does not follow later template edits.

## Alternatives Not Chosen

- Direct sends from the scheduler.
- Broker-only queue state.
- Cache-based correctness.
- SMTP as a default demo backend.
- Full ESP/webhook integration inside capstone scope.

*Constitution reference: Article 1, Article 3.3, Article 4, Article 5, Article 6, and Article 7.*

---

# Technical Design Document
## App — Email Automation
**Email Workflow Group | Document 2 of 5**

## Overview

Email Automation is a Django application with Celery workers and an HTMX operator dashboard. The product is a durable scheduled email workflow. Models and service functions own correctness; Celery and Redis are infrastructure helpers.

Package metadata:

- Distribution: `email-automation-capstone`
- Version: `0.2.0`
- Python: `>=3.11`
- Framework: Django 5.2
- Worker runtime: Celery
- Scheduler support: django-celery-beat
- Cache support: django-redis or local memory cache in development
- Default email backend: console

## Component Map

```text
Django Admin / HTMX dashboard / management commands
  -> shared service layer
     -> schedules and campaigns
     -> campaign runs
     -> outbox rows with snapshots
     -> Celery task publish
     -> worker claim/send/retry/DLQ
     -> events, attempts, dashboard stats
```

## Durable Models

### EmailTemplate

Stores a template name, subject template, body template, body format, required variables, and timestamps. `save()` calls `full_clean()`, and required variables must be a JSON list of strings.

### Recipient and RecipientList

Recipients store normalized email addresses, optional names, custom fields, and subscription state. Recipient lists group recipients for campaigns.

### SuppressionEntry

Stores a normalized email, reason, source, and timestamp. Suppression is checked at send time.

### Campaign

Connects an email template and recipient list with a campaign status. It includes an `operate_campaign` permission for dashboard operators.

### CampaignSchedule

Supports one-time and recurring schedules. One-time schedules require `send_at`; recurring schedules require cron or interval settings. `timezone_name` is display-only; dispatch evaluates UTC.

### CampaignRun

Represents one scheduled occurrence. A unique constraint prevents duplicate schedule occurrences.

### EmailOutbox

The core work row. It stores campaign, campaign run, recipient, template, immutable template snapshots, idempotency key, status, attempt timing, claim metadata, Celery task ID, timestamps, and last error.

### EmailSendAttempt

Records each render/provider attempt with worker ID, task ID, provider, timestamps, result, error fields, and provider metadata.

### EmailEventLog

Durable audit trail for scheduled, created, enqueued, claimed, attempted, sent, retry, failed, dead-letter, requeued, suppressed, cancelled, dispatched, completed, and operator events.

## State Machines

Campaign states:

- draft
- scheduled
- paused
- active
- completed
- cancelled

Campaign run states:

- pending
- generating_outbox
- outbox_generated
- dispatching
- dispatched
- completed
- failed
- cancelled

Outbox states:

- pending
- enqueued
- claimed
- sending
- sent
- retry_scheduled
- failed
- dead_lettered
- requeued
- skipped_suppressed
- cancelled

Illegal transitions raise domain exceptions. Protected target states require a valid claim token unless the caller uses a deliberate recovery path.

## Dispatch Flow

```text
find due schedules
  -> lock schedule
  -> create or resume CampaignRun
  -> promote campaign to active
  -> create outbox rows in batches
  -> store template snapshots
  -> record outbox_created events
  -> when all recipients materialized: mark run outbox_generated and advance schedule
  -> enqueue due rows
  -> optionally publish Celery tasks
  -> recover stale enqueued rows
  -> recover stale claimed/sending rows
  -> reconcile runs
```

The batch design prevents large recipient lists from creating unbounded transactions. A schedule is only advanced after every recipient for that occurrence has an outbox row.

## Worker Send Flow

```text
send_outbox_email(outbox_id)
  -> claim row
  -> check campaign cancelled/paused
  -> check suppression
  -> check throttle
  -> transition to sending
  -> render from TemplateSnapshot
  -> start attempt
  -> provider.send_email()
  -> complete attempt
  -> success: mark sent and record send quota
  -> transient failure: retry or dead-letter
  -> permanent failure: failed
```

Provider success may be reconciled to `sent` even if stale recovery released the claim mid-send. This avoids leaving an actually accepted delivery in a retryable state.

## Rendering

`TemplateSnapshot` is a frozen dataclass created from an outbox row. Rendering builds context from recipient custom fields plus reserved `recipient`, `campaign`, `run`, and `fields` keys. Reserved keys override custom fields. Required variables are resolved as dotted paths; missing, `None`, or empty values raise errors.

## Email Providers

The provider interface is `send_email(RenderedEmail) -> SendResult`. Implementations are selected by `EMAIL_BACKEND`:

- console
- fake
- smtp

SMTP configuration is environment-based and explicit.

## Throttling

`check_send()` reads campaign/global rate windows without consuming quota. `record_send()` increments counters only after successful provider delivery. Dashboard status is read-only and never decides correctness.

## Celery

`send_outbox_email_task` is a bound Celery task with late acknowledgements and `reject_on_worker_lost`. It calls the shared outbox service and releases stale claimed/sending rows on exceptions.

## Settings

Important settings include:

- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `REDIS_CACHE_URL`
- `EMAIL_BACKEND`
- `MAX_SEND_ATTEMPTS`
- `SEND_RATE_LIMIT`
- `CAMPAIGN_RATE_LIMIT`
- `ENQUEUED_STALE_SECONDS`
- `CLAIMED_STALE_SECONDS`

Production requires a real secret and Redis cache URL when debug is false.

## Known Limits

- SQLite is for local demos only.
- Cache and Redis are not correctness sources.
- Bounce and complaint webhooks are future work.
- SMTP is a basic provider path, not an ESP integration.
- Deep health hardening and provider dedupe are future work.

---

# Interface Design Specification
## App — Email Automation
**Email Workflow Group | Document 3 of 5**

## Public Interfaces

The system exposes:

- Django management commands
- Celery task workers
- Django Admin
- HTMX operator dashboard
- Python service functions
- Email provider interface
- Health endpoint

## Setup Commands

```powershell
python -m pip install -r requirements-dev.txt -e ".[dev]"
python manage.py migrate
python manage.py createsuperuser
```

## Demo Data

```powershell
python manage.py emailauto_seed --reset --noinput
python manage.py runserver
```

## Template Command

```powershell
python manage.py emailauto_template create --name Welcome --subject "Hi {{ recipient.name }}" --body "Hello {{ first_name }}" --required "[\"first_name\"]"
```

## Recipient Command

```powershell
python manage.py emailauto_recipients add --email ada@example.com --name Ada --fields "{\"first_name\":\"Ada\"}" --list Demo
```

## Campaign Command

```powershell
python manage.py emailauto_campaign create --name Launch --template Welcome --list Demo --status scheduled
```

## Schedule Command

```powershell
python manage.py emailauto_schedule one-time --campaign 1 --send-at 2026-07-01T09:00:00Z
```

## Dispatch Commands

```powershell
python manage.py emailauto_dispatch
python manage.py emailauto_dispatch --enqueue-celery
```

## Outbox Commands

```powershell
python manage.py emailauto_outbox list
python manage.py emailauto_outbox send 1 --backend fake
```

## Stats Command

```powershell
python manage.py emailauto_stats
```

## Demo Commands

Safe demos:

```powershell
python manage.py emailauto_demo basic
python manage.py emailauto_demo scheduler
python manage.py emailauto_demo retry
python manage.py emailauto_demo idempotency
python manage.py emailauto_demo suppression
python manage.py emailauto_demo rate-limit
python manage.py emailauto_demo all
```

Unsafe teaching demos:

```powershell
python manage.py emailauto_demo unsafe-direct-send
python manage.py emailauto_demo unsafe-no-idempotency
python manage.py emailauto_demo unsafe-duplicate-retry
python manage.py emailauto_demo unsafe-double-dispatch
python manage.py emailauto_demo unsafe-cache-truth
```

## Celery Commands

```powershell
python -m celery -A emailauto.config worker -l info -P solo
python manage.py emailauto_beat ensure-dispatcher
python -m celery -A emailauto.config beat -l info
```

## Python Services

```python
from emailauto.scheduling.dispatcher import dispatch_due_schedules
from emailauto.outbox.services import send_outbox_email, retry_outbox, requeue_outbox

summary = dispatch_due_schedules(enqueue_celery=True)
outcome = send_outbox_email(1, backend_name="fake")
retry_outbox(1)
requeue_outbox(1)
```

## Provider Interface

```python
class EmailBackend:
    provider_name = "base"
    def send_email(self, message: RenderedEmail) -> SendResult: ...
```

Supported provider names:

- console
- fake
- smtp

## Web Routes

- `/` — operator dashboard
- `/dlq/` — dead-letter view
- `/admin/` — Django Admin
- `/accounts/login/` — operator login
- `/health/` — health probe
- `/health/?deep=1` — database/cache/broker health

## Health Response

Healthy:

```json
{"status":"ok","database":true}
```

Degraded database:

```json
{"status":"degraded","database":false}
```

## Environment Contract

Production should set:

```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=...
DATABASE_URL=postgres://...
REDIS_CACHE_URL=redis://...
CELERY_BROKER_URL=redis://...
CELERY_RESULT_BACKEND=redis://...
DEFAULT_FROM_EMAIL=no-reply@example.com
```

SMTP requires:

```env
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

---

# Runbook
## App — Email Automation
**Email Workflow Group | Document 4 of 5**

## Local Start

```powershell
python -m pip install -r requirements-dev.txt -e ".[dev]"
python manage.py migrate
python manage.py createsuperuser
python manage.py emailauto_seed --reset --noinput
python manage.py runserver
```

Optional Redis:

```powershell
docker compose up -d redis
```

## Worker Start

Windows:

```powershell
python -m celery -A emailauto.config worker -l info -P solo
```

Beat:

```powershell
python manage.py emailauto_beat ensure-dispatcher
python -m celery -A emailauto.config beat -l info
```

## Quality Gates

```powershell
ruff check src tests
mypy src
python manage.py check
python manage.py makemigrations --check --dry-run
pytest --cov=emailauto --cov-report=term-missing --cov-fail-under=99
```

## Basic Operational Flow

1. Create a template.
2. Add recipients and recipient list.
3. Create a campaign.
4. Add a schedule.
5. Run dispatch.
6. Send manually with fake backend or enqueue Celery tasks.
7. Inspect outbox, stats, and events.

## Health Checks

```powershell
curl http://127.0.0.1:8000/health/
curl http://127.0.0.1:8000/health/?deep=1
```

## Common Failures

### Template render failure

Likely causes:

- missing required variable
- invalid template syntax
- empty rendered subject

Effect:

- attempt is recorded
- result becomes permanent failure

### Suppressed recipient

Effect:

- row becomes `skipped_suppressed`
- provider is not contacted

### Throttled send

Effect:

- row becomes `retry_scheduled`
- attempt count is not incremented
- provider is not contacted

### Celery publish failure

Effect:

- row rolls back to `retry_scheduled`
- future dispatch can publish again

### Stale enqueued row

Effect:

- dispatcher can republish safely because duplicate tasks must claim the row

### Stale claimed/sending row

Effect:

- recovery releases row back to retry-scheduled
- a successful provider acceptance can still be reconciled to `sent`

### Production configuration failure

Likely causes:

- `DJANGO_DEBUG=false` without `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false` without `REDIS_CACHE_URL`

Fix:

- set required environment variables

## Troubleshooting Tree

```text
Email did not send
  ├── no outbox row → run dispatch / verify schedule
  ├── pending/retry_scheduled → next_attempt_at not due or paused/throttled
  ├── enqueued → worker or broker issue; stale republish can recover
  ├── claimed/sending → worker issue; stale claim recovery can release
  ├── skipped_suppressed → inspect suppression entry
  ├── failed/dead_lettered → inspect attempt rows and requeue if appropriate
  └── sent → inspect provider output/logs
```

## Maintenance Notes

- Keep database state authoritative.
- Keep Celery payloads as outbox IDs.
- Keep cache and throttle counters out of correctness paths.
- Keep console/fake default safe.
- Add tests before changing state transitions, claims, retry/DLQ, or dispatcher batching.
- Keep unsafe demos isolated from production services.

---

# Lessons Learned
## App — Email Automation
**Email Workflow Group | Document 5 of 5**

## Why This Design Was Chosen

Email automation is a workflow problem, not just a sending problem. The difficult cases are duplicates, crashes, stale workers, retries, changed templates, suppressions, throttling, and operator recovery. A database outbox handles those cases better than direct send or broker-only state.

## What Was Intentionally Omitted

- Full ESP API integration.
- Bounce and complaint webhook ingestion.
- Provider-side dedupe.
- Multi-tenant operator governance.
- Full marketing analytics.
- Production hardening beyond the capstone baseline.

## Biggest Weakness

The biggest weakness is operational complexity. The reliability guarantees require many moving parts: Django models, state transitions, Celery, Redis, claim tokens, stale recovery, attempts, events, and operator actions. That complexity is justified by correctness, but it must be explained clearly.

The second weakness is that SMTP is not a full modern email platform. A production version should integrate with an ESP API and webhook feedback loops.

## Scaling Considerations

For larger campaigns:

- use PostgreSQL
- tune batch size
- run multiple Celery workers
- use Redis for cache/throttle accuracy
- monitor stale recovery windows
- add provider-level metrics

For production email operations:

- add ESP APIs
- store provider message IDs
- ingest bounces/complaints
- update suppressions automatically
- add authenticated deep health probes

## Next Refactor

1. Add provider API backend with provider message IDs.
2. Add bounce/complaint webhook processing.
3. Add Prometheus-style operational metrics.
4. Harden deep health probes.
5. Add schedule cleanup utilities.

## Key Lessons

- Brokers execute work; databases preserve truth.
- Idempotency keys prevent duplicate work.
- Claim tokens protect against stale workers.
- Template snapshots make queued email auditable.
- Suppression should be checked at send time.
- Throttle slots should be charged only on success.
- Unsafe demos make architectural choices easier to defend.

*Constitution v2.0 checklist: This document satisfies Article 5, Article 6, and Article 7 for Email Automation.*
