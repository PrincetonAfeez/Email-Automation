# Portfolio Demo Walkthrough

Use this script when presenting the project to reviewers. Total time: **~15 minutes**.

## Before you start

```powershell
python -m pip install -e ".[dev]"
python manage.py migrate
python manage.py emailauto_seed --reset --noinput --operator-password demo
python manage.py runserver
```

Log in at `/accounts/login/` as `operator` / `demo` (password printed by seed if omitted).

## 1. Architecture pitch (2 min)

Explain the core invariant: **the database owns correctness**. Celery carries messages; workers claim rows atomically; every send is idempotent.

Point reviewers to:
- [docs/architecture.md](architecture.md) — diagram
- [docs/state_transitions.md](state_transitions.md) — outbox lifecycle
- [docs/retries_and_idempotency.md](retries_and_idempotency.md) — at-least-once → effectively-once

## 2. Web dashboard (4 min)

1. Open `/` — live stats, throughput, rate-limit status (HTMX polls every 5–8s).
2. Show a **Send now** on a scheduled campaign → outbox rows appear.
3. Open campaign detail — note recipient count warning if list is empty.
4. Visit `/schedules/` — campaign status column shows which schedules are runnable.
5. Open `/dlq/` — requeue a dead-lettered row (seed data includes examples).

## 3. Safe CLI demos (4 min)

```powershell
python manage.py emailauto_demo idempotency   # duplicate dispatch → one send
python manage.py emailauto_demo suppression   # skipped_suppressed, no provider call
python manage.py emailauto_demo retry         # transient → retry_scheduled
```

Compare to one unsafe demo:

```powershell
python manage.py emailauto_demo unsafe-no-idempotency
```

## 4. Tests & quality gates (2 min)

```powershell
pytest --cov=emailauto --cov-fail-under=90 -q
ruff check src tests
mypy src
```

Highlight: concurrency tests, stale-claim recovery, operator action tests.

## 5. Future work (1 min)

Close with [docs/out_of_scope.md](out_of_scope.md) and README **Future work** — bounces, production hardening, webhook extension. Emphasize what the capstone proves vs what would come next in production.

## Talking points checklist

- [ ] Outbox idempotency key per (run × recipient)
- [ ] Claim token + stale recovery
- [ ] Throttle does not consume quota until success
- [ ] Template snapshot immutability
- [ ] Operator audit trail (`operator_action` events)
- [ ] Teaching demos show both safe and intentionally unsafe paths
