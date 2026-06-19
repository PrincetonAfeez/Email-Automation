# ADR 0001 — Concurrency, locking, and starvation/deadlock posture

Status: accepted

## Context

Multiple Celery workers process the broker concurrently, and Celery Beat can fire the
dispatcher (`dispatch_due_schedules`) on overlapping ticks. Two correctness hazards follow:

1. **Two workers racing one outbox row** — both could try to send the same email.
2. **Two dispatchers racing one schedule occurrence** — both could create duplicate
   `CampaignRun` / `EmailOutbox` rows, or block each other.

We must also avoid the classic concurrency failure modes — **deadlock** (two transactions
each holding a lock the other needs) and **starvation** (a transaction repeatedly losing a
contended lock and never making progress).

## Decision

- **The database is the arbiter, and the real guards are unique constraints, not locks.**
  `EmailOutbox.idempotency_key` and `CampaignRun.run_key` are `UNIQUE`. Even with zero
  locking, a duplicate dispatcher run cannot create duplicate rows — `get_or_create` plus
  the unique constraint collapse the race. Locking is an optimization, not the correctness
  mechanism.
- **Worker claims are a single-statement compare-and-swap**, not a held lock. `claim_outbox`
  issues one `UPDATE ... WHERE status IN (claimable) AND pk = ?` and checks the affected-row
  count. Exactly one worker updates one row; the loser updates zero rows and backs off. A
  single atomic statement cannot deadlock with itself and holds no lock across user code.
- **Dispatcher schedule locking uses `SELECT ... FOR UPDATE SKIP LOCKED` where the backend
  supports it** (PostgreSQL). A second dispatcher that finds a schedule already locked
  *skips it this tick* rather than blocking — this is the explicit anti-starvation /
  anti-blocking choice. On SQLite the option is unsupported and is a no-op; SQLite serializes
  writers globally, so concurrent dispatchers are not a practical concern in dev.
- **Lock ordering is uniform** (lock the schedule row, then create children) and every locked
  section is short and never spans a network/provider call, which keeps deadlock risk low.

## Consequences

- **Deadlock:** very low risk — claims are single statements, and the only `FOR UPDATE` is a
  single-row lock acquired in a consistent order and released at transaction end without any
  intervening external I/O.
- **Starvation:** a contended dispatcher does not spin on a blocked lock; `SKIP LOCKED` lets
  it move on and the next tick (or another worker) picks the row up. Worker-claim losers
  simply re-poll on the next dispatch tick.
- **SQLite limitation (accepted):** `select_for_update`/`SKIP LOCKED` are no-ops on SQLite;
  true row-level concurrency requires PostgreSQL. This is documented and acceptable for the
  local/dev/test target. See `docs/architecture.md`.
- **Tested:** `tests/concurrency/test_concurrent_claim.py` runs a genuine two-thread race and
  asserts exactly one winner; `tests/concurrency/test_duplicate_dispatch.py` asserts duplicate
  dispatch creates one row per recipient.
