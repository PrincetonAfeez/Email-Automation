# Changelog

All notable changes to this capstone project are documented here.

## [0.2.0] — 2026-06-20

### Test & quality

- Expanded pytest suite to **353 tests** with **~99.9% line coverage** on `src/emailauto`
- Added targeted coverage modules for dispatcher reconcile, outbox recovery, web views, CLI, settings, and recurrence edge cases
- CI coverage gate raised to **99%**; quality gates: ruff, mypy, Django check, migration check

### Portfolio polish

- HTMX outbox panel preserves pagination across polls
- Schedule page shows campaign status; runs paginated on campaign detail
- Recipient subscribe/unsubscribe from operator dashboard
- Empty recipient list warnings on trigger, campaign detail, and CLI create
- Post-attempt reconcile for failure/dead-letter/retry paths after mid-flight claim release
- `docs/portfolio_walkthrough.md` — structured reviewer demo script

### Round 2 — reliability

- Post-send reconcile prevents duplicate delivery after force-requeue during `sending`
- Cron OR semantics when both day-of-month and day-of-week are restricted
- Celery task revoke on force-requeue and stale-claim recovery
- Campaign completion disables orphaned schedules; auto-promote `scheduled → active` on dispatch
- Paused campaigns cannot enable schedules; cancel campaign in single transaction
- Operator audit events, deep health probe, pagination across dashboard/schedules/runs
- Global operator rate limit; seed credential hardening

### Round 1 — correctness

- Suppression/throttle/pause resolved in `claimed` before `sending`
- Campaign cancel bulk-cancels inflight outbox; trigger creates fresh run per send
- CampaignRun transition enforcement; migration for `operator_action` events
- HTMX vendored static assets; production requires `REDIS_CACHE_URL`

## [0.1.0] — initial capstone

- Django + Celery scheduled email automation with DB-owned outbox
- Idempotent worker claims, retries, DLQ, CLI, admin, HTMX operator dashboard
- Safe and unsafe teaching demos
