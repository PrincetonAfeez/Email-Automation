# Email Automation Capstone

Scheduled email automation built around Django, Celery, an explicit database outbox, idempotent worker claims, retries, dead-letter handling, Redis-backed cache/throttling support, CLI commands, Django Admin, and a small HTMX operator dashboard.

The important design choice is that the database owns correctness. Celery carries execution messages, Redis can carry broker/cache/rate-limit data, and workers perform sends, but the durable state lives in Django models.

```text
Beat ──60s──> dispatch_due_schedules ──> CampaignRun + EmailOutbox (DB, unique idempotency key)
                                              │ enqueue id
                                              ▼
                                        Redis broker ──> Celery worker
                                              │ atomic claim, render snapshot,
                                              │ suppression + throttle checks
                                              ▼
                              console / fake / smtp backend ──> attempt + event + state (DB)
```

See [docs/architecture.md](docs/architecture.md) for the full diagram and component breakdown.

## What Is Included

- Email templates with required-variable validation.
- Recipients, recipient lists, and suppression entries.
- Campaigns, one-time schedules, interval schedules, and cron-style recurrence helpers.
- Campaign runs (reconciled to dispatched/completed/failed) and unique outbox rows per
  campaign run and recipient.
- Immutable per-row template snapshots: a queued email renders from the snapshot captured
  at creation, so editing the template later cannot change what is sent.
- Worker claim tokens, stale-claim protection, and automatic recovery for orphaned
  `claimed`/`sending` rows (see `CLAIMED_STALE_SECONDS`).
- Structured lifecycle logging (`event=… outbox_id=… campaign_id=…`) alongside the durable
  audit events, so one row can be traced through the logs end-to-end.
- Safe console and fake email providers by default, with optional SMTP.
- Send attempts, audit events, retry scheduling, and dead-letter requeue.
- Redis/Django-cache dashboard stats and send throttling helpers.
- Django Admin registrations and actions.
- HTMX dashboard at `/`, DLQ view at `/dlq/`, Django Admin at `/admin/`.
- Operator actions from the dashboard: trigger/pause/resume/cancel a campaign, retry or
  cancel an outbox row, requeue dead letters, and add suppressions — all through the
  shared service layer.
- CLI commands for init-db, template, recipient, campaign, schedule, dispatch, outbox,
  DLQ, stats, sample-data seeding, and both safe and unsafe demos.
- Operator web views: dashboard (live stats, throughput, rate-limit status), schedule
  visibility, per-campaign and per-run pages, and the DLQ.
- Pytest suite (353 tests, ~99% coverage) for reliability paths (idempotency, claims,
  retries, DLQ, suppression-at-send, batching, cron, throttling, operator actions),
  full CLI/admin/web coverage, and teaching demos.

## Setup

```powershell
python -m pip install -r requirements-dev.txt -e ".[dev]"
python manage.py migrate
python manage.py createsuperuser
```

`pyproject.toml` (v0.2.0) declares compatible version ranges; `requirements.txt`,
`requirements-dev.txt`, and `requirements-prod.txt` pin a known-good resolved set for
reproducible installs (`pip install -r requirements-dev.txt -e ".[dev]"` for local work,
`pip install -r requirements-prod.txt -e ".[prod]"` for production/Docker).

For Redis:

```powershell
docker compose up -d redis
```

Load explorable sample data (mixed sent / retry / dead-lettered / suppressed states) and
run the web process:

```powershell
python manage.py emailauto_seed --reset --noinput
python manage.py runserver
```

The seed command creates an `operator` user with `campaigns.operate_campaign`. By default
the password is random (printed once) or set via `EMAILAUTO_SEED_OPERATOR_PASSWORD` /
`--operator-password`. Pass `--no-create-operator` to skip demo credentials entirely.
The dashboard and operator actions require a logged-in user with that permission (grant via
Django admin or assign to staff). Anonymous requests are redirected to the operator login
at `/accounts/login/`; create an account with `createsuperuser` (above) or use the seeded
operator account.
HTMX is vendored under `src/emailauto/web/static/emailauto/vendor/` (no CDN dependency);
run `collectstatic` for production.

`DEBUG` defaults to `true` for a zero-config local run. In production set
`DJANGO_DEBUG=false` and a real `DJANGO_SECRET_KEY` (the app refuses to start without one
when `DEBUG` is off) — secure cookies and content-type-nosniff turn on automatically.

Run a Celery worker on Windows:

```powershell
python -m celery -A emailauto.config worker -l info -P solo
```

Run Celery Beat:

```powershell
python manage.py emailauto_beat ensure-dispatcher
python -m celery -A emailauto.config beat -l info
```

## Environment

Copy `.env.example` to `.env` and adjust values. The default email backend is `console`, so demos do not send real email.

Real SMTP requires all of this to be deliberate:

```env
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
DEFAULT_FROM_EMAIL=no-reply@example.com
```

Tests and demos should use `fake` or `console`.

## CLI Demo

```powershell
python manage.py emailauto_template create --name Welcome --subject "Hi {{ recipient.name }}" --body "Hello {{ first_name }}" --required "[\"first_name\"]"
python manage.py emailauto_recipients add --email ada@example.com --name Ada --fields "{\"first_name\":\"Ada\"}" --list Demo
python manage.py emailauto_campaign create --name Launch --template Welcome --list Demo --status scheduled
python manage.py emailauto_schedule one-time --campaign 1 --send-at 2026-07-01T09:00:00Z
python manage.py emailauto_dispatch
python manage.py emailauto_outbox list
python manage.py emailauto_outbox send 1 --backend fake
python manage.py emailauto_stats
```

To enqueue Celery tasks instead of sending manually:

```powershell
python manage.py emailauto_dispatch --enqueue-celery
```

## Demos

All demos use the fake/console backend and never send real email. The safe demos build a
tiny campaign, exercise the real pipeline, print what happened, and roll back so nothing
is persisted.

```powershell
python manage.py emailauto_demo list
python manage.py emailauto_demo basic
python manage.py emailauto_demo scheduler
python manage.py emailauto_demo retry
python manage.py emailauto_demo idempotency
python manage.py emailauto_demo suppression
python manage.py emailauto_demo rate-limit
python manage.py emailauto_demo all
```

Unsafe teaching demos intentionally reproduce failure modes the architecture prevents:

```powershell
python manage.py emailauto_demo unsafe-direct-send
python manage.py emailauto_demo unsafe-no-idempotency
python manage.py emailauto_demo unsafe-duplicate-retry
python manage.py emailauto_demo unsafe-double-dispatch
python manage.py emailauto_demo unsafe-cache-truth
```

The production path avoids these with durable outbox rows, unique idempotency keys, claim
tokens, enforced state transitions, and audit records.

## Tests & quality gates

The same checks run in CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)):

```powershell
ruff check src tests          # lint + import order
mypy src                      # type check (django-stubs)
python manage.py check
python manage.py makemigrations --check --dry-run
pytest --cov=emailauto --cov-report=term-missing --cov-fail-under=99   # 353 tests, ~99% coverage
```

For a structured reviewer walkthrough, see [docs/portfolio_walkthrough.md](docs/portfolio_walkthrough.md).

## Production notes

- Set `DJANGO_DEBUG=false`, a strong `DJANGO_SECRET_KEY`, and **`REDIS_CACHE_URL`** (required when debug is off).
- Use PostgreSQL and Redis in production; SQLite is for local demos only.
- For Docker, use `docker compose -f docker-compose.yml -f docker-compose.prod.yml up`
  (prod override sets `DEBUG=false`, runs `collectstatic`, serves via Gunicorn, and expects a real secret).
- SMTP: set `SMTP_USE_TLS=true` for port 587 (STARTTLS) or `SMTP_USE_SSL=true` for port 465.
- Schedule `timezone_name` is **display-only**; dispatch always evaluates UTC.
- Grant `campaigns.operate_campaign` to non-staff operator accounts via Django admin (superusers have it automatically).
- Throttling and dashboard stats are accurate across multiple workers only when `REDIS_CACHE_URL` is set.
- Send-rate slots are consumed only after a **successful** delivery; throttled or failed sends do not consume quota.
- Supported Python versions: 3.11–3.14 (see CI matrix).
- Health/readiness probe: `GET /health/` returns `{"status":"ok","database":true}` when healthy, or HTTP **503** with `{"status":"degraded","database":false}` when the database is unreachable. Append `?deep=1` to also check shared cache and the Celery broker (`cache`, `broker` boolean fields).

## Data Ownership

- Durable DB data: templates, recipients, campaigns, schedules, runs, outbox rows, attempts, events, suppression.
- Broker data: Celery delivery messages that point to durable outbox IDs.
- Cache data: dashboard counts and rate-limit counters. Cache is never used for send correctness.

## Future work

Production and extension items deliberately out of scope for the capstone demo but documented for reviewers:

- **Production hardening:** authenticated deep health probes, Docker service healthchecks, HSTS defaults, CI job with Redis/Celery integration (see [docs/out_of_scope.md](docs/out_of_scope.md) and production notes above).
- **Inbound webhooks:** bounce/complaint handling to auto-populate suppressions.
- **Schedule hygiene:** optional cleanup of orphan one-time schedules created by repeated manual triggers.
- **Provider deduplication:** SMTP sends an `X-Idempotency-Key` header; a provider-side dedupe layer would complement app-level correctness.

See [CHANGELOG.md](CHANGELOG.md) for release history and reliability fixes applied during development.

## License

Released under the [MIT License](LICENSE).
