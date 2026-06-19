# State Transitions

The authoritative transition table lives in `emailauto/core/states.py`
(`OUTBOX_TRANSITIONS`) and is enforced by `assert_outbox_transition`.

Normal outbox path:

```text
pending -> enqueued -> claimed -> sending -> sent
```

Pre-send checks (suppression, cancelled/paused campaign) are resolved while the row is
still `claimed`, before it ever reaches `sending`:

```text
claimed -> skipped_suppressed     # recipient unsubscribed/suppressed
claimed -> cancelled              # campaign cancelled
claimed -> retry_scheduled        # campaign paused / throttled before send (no attempt consumed)
```

Retry path:

```text
sending -> retry_scheduled -> enqueued -> claimed -> sending -> sent
retry_scheduled -> claimed         # a due retry may also be claimed directly
```

Failure paths:

```text
sending -> dead_lettered           # transient failure with attempts exhausted
sending -> failed                  # permanent failure (bad address, render error, ...)
retry_scheduled -> dead_lettered   # a scheduled retry abandoned once exhausted
```

Suppression path:

```text
pending -> skipped_suppressed
claimed -> skipped_suppressed
```

Cancellation path:

```text
pending -> cancelled
enqueued -> cancelled
retry_scheduled -> cancelled
requeued -> cancelled
claimed -> cancelled
```

Requeue paths (operator-initiated):

```text
dead_lettered -> requeued -> pending/enqueued/claimed
failed -> requeued -> pending/enqueued/claimed
```

Invalid examples are rejected in code and tested:

- `sent -> sending`
- `sent -> retry_scheduled`
- `sending -> skipped_suppressed` (suppression must be decided while `claimed`)
- `dead_lettered -> sending` without requeue
- stale claim token -> `sent`
- stale claim token -> `retry_scheduled`
- stale claim token -> `dead_lettered`

## Stale worker recovery

Rows stuck in `enqueued` longer than `ENQUEUED_STALE_SECONDS` are re-published to Celery.
Rows stuck in `claimed` or `sending` longer than `CLAIMED_STALE_SECONDS` are force-released
to `retry_scheduled` by the dispatcher (claim token bypass with audit metadata). Recovery
includes campaigns in `paused` state (rows are not sent until the campaign is resumed).
Operators can also force-requeue a stuck row from the outbox detail page.

## Why suppression/cancel happen before `sending`

`skipped_suppressed` and `cancelled` are only reachable from `pending`/`claimed`, never
from `sending`. The worker therefore evaluates every reason-not-to-send while the row is
still `claimed` and only transitions to `sending` once the row is known to be sendable.
A throttle rejection or a paused campaign releases the row back to `retry_scheduled`
**without** incrementing `attempt_count`, so a delayed send is never lost to the DLQ.
