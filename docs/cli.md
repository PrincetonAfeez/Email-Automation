# CLI Reference

All EmailAuto commands are Django management commands invoked as `python manage.py …`.
They follow Django's standard exit codes (see [CLI exit codes](../README.md#cli-exit-codes) in the README).

## Setup

Apply migrations (same as `python manage.py migrate`):

```powershell
python manage.py emailauto_initdb [--noinput]
```

Print the installed package version:

```powershell
python manage.py emailauto_version
```

## Templates

Create or list email templates.

```powershell
python manage.py emailauto_template create --name NAME --subject SUBJECT --body BODY [--format text|html] [--required JSON_LIST]
python manage.py emailauto_template list
```

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | yes | Unique template name. |
| `--subject` | yes | Subject line (Django template syntax). |
| `--body` | yes | Body template (Django template syntax). |
| `--format` | no | `text` (default) or `html`. |
| `--required` | no | JSON list of required template variables (default `[]`). |

`create` upserts by name. Invalid JSON in `--required` or template validation errors exit with code **1**.

## Recipients

Create, import, list, suppress, and unsuppress recipients.

```powershell
python manage.py emailauto_recipients add --email EMAIL [--name NAME] [--fields JSON_OBJECT] [--list LIST_NAME]
python manage.py emailauto_recipients import PATH [--list LIST_NAME]
python manage.py emailauto_recipients suppress --email EMAIL --reason REASON
python manage.py emailauto_recipients unsuppress --email EMAIL
python manage.py emailauto_recipients list [--limit N]
```

| Subcommand | Flags | Description |
|------------|-------|-------------|
| `add` | `--email`, `--name`, `--fields`, `--list` | Create or update a recipient. Email is normalized to lowercase. `--fields` defaults to `{}`. If `--list` is given, the recipient is added to that list (created if needed). |
| `import` | `PATH`, `--list` | Import recipients from a CSV file. The CSV must include an `email` column; optional `name` and other columns become custom fields. |
| `suppress` | `--email`, `--reason` | Add a suppression entry. |
| `unsuppress` | `--email` | Remove a suppression entry (warns if none exists). |
| `list` | `--limit` | List recipients (default limit **50**). |

## Campaigns

Create, list, inspect, and control campaigns.

```powershell
python manage.py emailauto_campaign create --name NAME --template TEMPLATE --list LIST_NAME [--status draft|scheduled]
python manage.py emailauto_campaign list
python manage.py emailauto_campaign inspect CAMPAIGN
python manage.py emailauto_campaign status CAMPAIGN_ID STATUS
python manage.py emailauto_campaign pause CAMPAIGN
python manage.py emailauto_campaign resume CAMPAIGN
python manage.py emailauto_campaign cancel CAMPAIGN
```

| Subcommand | Arguments / flags | Description |
|------------|-------------------|-------------|
| `create` | `--name`, `--template`, `--list`, `--status` | Create a campaign. `--template` and `--list` are resolved by name. `--status` may be `draft` or `scheduled` (default `scheduled`). |
| `list` | — | Tab-separated id, name, status, recipient list. |
| `inspect` | `CAMPAIGN` | Detailed view: schedules and outbox counts. `CAMPAIGN` is an id or name. |
| `status` | `CAMPAIGN_ID`, `STATUS` | Set status directly. `STATUS` may be `draft`, `scheduled`, `paused`, `active`, `completed`, or `cancelled`. |
| `pause` / `resume` / `cancel` | `CAMPAIGN` | Service-layer transitions. `CAMPAIGN` is an id or name. |

## Schedules

Create and list campaign schedules. Datetimes accept ISO-8601 strings; naive values use the Django configured timezone, then are stored in UTC.

```powershell
python manage.py emailauto_schedule one-time --campaign ID --send-at DATETIME
python manage.py emailauto_schedule interval --campaign ID --start-at DATETIME --every N --period minutes|hours|days
python manage.py emailauto_schedule cron --campaign ID --expression CRON [--start-at DATETIME]
python manage.py emailauto_schedule list
```

| Subcommand | Flags | Description |
|------------|-------|-------------|
| `one-time` | `--campaign`, `--send-at` | One-shot schedule at the given time. |
| `interval` | `--campaign`, `--start-at`, `--every`, `--period` | Recurring fixed interval. |
| `cron` | `--campaign`, `--expression`, `--start-at` | Recurring cron schedule. `--start-at` defaults to now if omitted. See [scheduling.md](scheduling.md) for cron syntax. |
| `list` | — | All schedules with next run time and display timezone. |

## Dispatch

Scan due schedules, create campaign runs and outbox rows, optionally enqueue Celery tasks.

```powershell
python manage.py emailauto_dispatch [--batch-size N] [--enqueue-celery]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--batch-size` | `500` | Maximum outbox rows created per dispatch tick. |
| `--enqueue-celery` | off | After marking rows `enqueued`, publish Celery send tasks. Without this flag, rows are created but not queued to the broker. |

Output includes counts: `schedules`, `runs`, `outbox_created`, `outbox_enqueued`.

## Outbox

Inspect, send, retry, and cancel outbox rows.

```powershell
python manage.py emailauto_outbox list [--status STATUS] [--campaign NAME] [--limit N]
python manage.py emailauto_outbox inspect --id OUTBOX_ID
python manage.py emailauto_outbox send OUTBOX_ID [--backend BACKEND]
python manage.py emailauto_outbox retry --id OUTBOX_ID
python manage.py emailauto_outbox cancel --id OUTBOX_ID
```

| Subcommand | Arguments / flags | Description |
|------------|-------------------|-------------|
| `list` | `--status`, `--campaign`, `--limit` | List recent rows (default limit **50**). Filter by outbox status string or campaign name. |
| `inspect` | `--id` | Row details, attempts, and errors. |
| `send` | `OUTBOX_ID`, `--backend` | Send synchronously in-process (CLI worker id). `--backend` overrides the configured backend (e.g. `fake`, `console`). |
| `retry` | `--id` | Requeue a failed or dead-lettered row for retry. |
| `cancel` | `--id` | Cancel a row. |

## DLQ

Inspect and requeue dead-lettered outbox rows.

```powershell
python manage.py emailauto_dlq list
python manage.py emailauto_dlq requeue OUTBOX_ID
```

`requeue` calls the same retry path as `emailauto_outbox retry` and only succeeds for rows in a retriable state.

## Stats

Print cached dashboard counters.

```powershell
python manage.py emailauto_stats [dashboard]
python manage.py emailauto_stats campaign NAME
python manage.py emailauto_stats [--campaign-id ID]
```

| Form | Description |
|------|-------------|
| (no subcommand) | Global dashboard stats. |
| `dashboard` | Same as no subcommand. |
| `campaign NAME` | Stats for one campaign (resolved by name). |
| `--campaign-id ID` | Filter global stats to one campaign (works with no subcommand or `dashboard`). |

Output is tab-separated `key\tvalue` lines.

## Seed data

Populate explorable sample data for the web UI. Uses the **fake** backend — never sends real email.

```powershell
python manage.py emailauto_seed [--reset --noinput] [--operator-password PASSWORD] [--no-create-operator]
```

| Flag | Description |
|------|-------------|
| `--reset` | Delete all existing EmailAuto data first. Requires `--noinput` to confirm. |
| `--noinput` | Non-interactive confirmation (required with `--reset`). |
| `--operator-password` | Password for the demo `operator` user. Defaults to `EMAILAUTO_SEED_OPERATOR_PASSWORD` or a random value printed once. |
| `--no-create-operator` | Skip creating the demo operator account (default is to create one with `campaigns.operate_campaign`). |

Without `--reset`, seed data is appended to whatever is already in the database.

## Celery Beat helper

Register or update the django-celery-beat periodic task that runs the dispatcher.

```powershell
python manage.py emailauto_beat ensure-dispatcher [--every-seconds N] [--disabled]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--every-seconds` | `60` | Beat interval for `dispatch_due_schedules`. |
| `--disabled` | off | Create/update the task but leave it disabled. |

## Demos

Safe pipeline demos build a tiny campaign, exercise the real pipeline, print results, and roll back. Unsafe demos illustrate failure modes the production architecture prevents. **None send real email.**

List available demos:

```powershell
python manage.py emailauto_demo list
```

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

Each demo prints tab-separated `key\tvalue` result lines.
