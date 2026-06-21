# Retries And Idempotency

Celery provides at-least-once task delivery. That means a task can run more than once.

This app aims for effectively-once application behavior by combining:

- Unique outbox idempotency keys.
- Atomic claim updates.
- Claim tokens.
- Protected state transitions.
- Send attempts and audit events.
- Retry and dead-letter states in the database.

Transient failures move to `retry_scheduled` with exponential backoff until `max_attempts` is reached. Exhausted retryable rows move to `dead_lettered`.

Permanent failures move to `failed` and are not retried automatically.

Dead-lettered rows are requeued only by explicit operator action.

**Celery revoke note:** when a campaign or outbox row is cancelled, the app calls
`celery.control.revoke(task_id, terminate=False)`. That prevents a queued task from starting
but does **not** interrupt a worker that is already executing `send_outbox_email`. Correctness
relies on claim tokens, state transitions, and the send-path re-check for cancelled campaigns
before contacting the provider.

