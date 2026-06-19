# Scheduling

`CampaignSchedule` supports one-time and recurring schedules.

One-time schedules use `send_at` and are disabled after the dispatcher creates the campaign run.

Recurring schedules can use either:

- Fixed intervals: every N minutes, hours, or days.
- Five-field cron expressions: `minute hour day-of-month month day-of-week`.

Cron field notes:

- Supported syntax per field: `*`, single values, comma lists (`1,15`), ranges
  (`1-5`), and steps (`*/15`).
- Day-of-week uses the standard cron convention **Sunday = 0 .. Saturday = 6**, and `7`
  is also accepted as Sunday. Three-letter names work too: `MON`, `TUE`, ... `SUN`
  (e.g. `0 9 * * MON-FRI`). Month names `JAN`..`DEC` are also accepted.
- Times are evaluated in UTC (schedules store UTC internally; see UTC discipline below).
- `timezone_name` on a schedule is **display-only** for the operator UI; it does not shift
  when dispatch fires.
- Weekday ranges do not wrap across week boundaries (e.g. `FRI-MON` does not include Sat/Sun).

The dispatcher is safe to run repeatedly. Duplicate campaign occurrences are blocked by the unique `run_key`, and duplicate recipient work is blocked by the unique outbox `idempotency_key`.

Celery Beat calls `emailauto.scheduling.dispatch_due_schedules` every 60 seconds by default.

