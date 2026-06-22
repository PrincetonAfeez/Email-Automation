# Schema State Values

## Campaign status

- `draft`
- `scheduled`
- `paused`
- `active`
- `completed`
- `cancelled`

Allowed campaign transitions:

- `draft` → `scheduled`, `cancelled`
- `scheduled` → `active`, `paused`, `cancelled`, `completed`
- `active` → `paused`, `completed`, `cancelled`
- `paused` resumes through service-layer logic using `status_before_pause`
- `completed` and `cancelled` are terminal

## Campaign run status

- `pending`
- `generating_outbox`
- `outbox_generated`
- `dispatching`
- `dispatched`
- `completed`
- `failed`
- `cancelled`

Terminal campaign run statuses:

- `completed`
- `failed`
- `cancelled`

## Outbox status

- `pending`
- `enqueued`
- `claimed`
- `sending`
- `sent`
- `retry_scheduled`
- `failed`
- `dead_lettered`
- `requeued`
- `skipped_suppressed`
- `cancelled`

Terminal or effectively terminal outbox statuses:

- `sent`
- `cancelled`
- `skipped_suppressed`

Operator requeue paths exist for `failed` and `dead_lettered` rows.

## Attempt result

- `success`
- `transient_failure`
- `permanent_failure`

## Schedule type

- `one_time`
- `recurring`

## Interval period

- `minutes`
- `hours`
- `days`

## Suppression source

- `manual`
- `unsubscribe`
- `import`
- `bounce`
- `test`

## Event type

- `scheduled`
- `outbox_created`
- `enqueued`
- `claimed`
- `send_attempt_started`
- `sent`
- `retry_scheduled`
- `failed`
- `dead_lettered`
- `requeued`
- `skipped_suppressed`
- `cancelled`
- `dispatched`
- `campaign_completed`
- `operator_action`
