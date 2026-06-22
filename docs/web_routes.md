# Web Routes

EmailAuto serves an HTMX operator dashboard at the site root. Routes are defined in
`src/emailauto/web/urls.py`.

**Authentication:** All operator pages except `/health/` require login. Anonymous requests
receive **302** to `/accounts/login/?next=…`.

**Mutations:** POST actions that change state require `campaigns.operate_campaign` or Django
staff status. Logged-in users without that permission receive **403** with body
`Operator permission required.`

**Rate limiting:** Operator POST endpoints share a per-user limit (`EMAILAUTO_OPERATOR_RATE_LIMIT`,
default **30** per 60 seconds). When exceeded, the request is redirected to the dashboard with
an error message; no mutation runs.

**Redirects after POST:** Most mutating forms accept an optional `next` POST field. Only same-host
relative URLs are honored; external URLs are ignored and the view falls back to its default redirect.

---

## Authentication

| Route | Method | Permission | Purpose | Success | Bad input |
|-------|--------|------------|---------|---------|-----------|
| `/accounts/login/` | GET, POST | Public | Operator login form. Any active Django user may log in (staff not required). | **200** HTML form (GET). **302** to `next` or `/` after valid credentials (POST). | Invalid credentials re-render the form with errors (**200**). |
| `/accounts/logout/` | POST | Authenticated | End session. | **302** to `/accounts/login/`. | GET returns **405** (POST only). |

---

## Public / readiness

| Route | Method | Permission | Purpose | Success | Bad input |
|-------|--------|------------|---------|---------|-----------|
| `/health/` | GET | None | Liveness/readiness probe for load balancers and Docker. | **200** JSON: `{"status":"ok","database":true}` when the database answers `SELECT 1`. | N/A |
| `/health/?deep=1` | GET | None | Extended probe: database, Django cache write/read, and Celery broker ping. | **200** when database, cache, and broker are healthy. Adds `"cache": true/false` and `"broker": true/false`. | **503** JSON with `"status":"degraded"` when any dependency fails (including database-only failure on the shallow probe). |

---

## Operator dashboard (read-only pages)

All routes below require **login** only. Action buttons on these pages are hidden or disabled
unless the user has operator permission (`can_operate` in templates).

| Route | Method | Purpose | Success | Bad input |
|-------|--------|---------|---------|-----------|
| `/` | GET | Main dashboard: global stats, paginated campaigns (25/page), recent outbox (50/page), failures, throughput, throttle status. Query: `campaign_page`, `outbox_page`. | **200** HTML. | Invalid page numbers are clamped by Django's paginator (empty page → last page). |
| `/schedules/` | GET | Enabled schedules ordered by next run. Query: `page` (50/page). Includes UTC scheduling note. | **200** HTML. | Invalid `page` clamped by paginator. |
| `/runs/<run_id>/` | GET | Campaign run detail: per-run stats and paginated outbox rows. Query: `outbox_page`. | **200** HTML. | Unknown `run_id` → **404**. |
| `/campaigns/<campaign_id>/` | GET | Campaign detail: stats, runs, outbox rows, action flags. Query: `outbox_page`, `runs_page`. | **200** HTML. | Unknown `campaign_id` → **404**. |
| `/outbox/<outbox_id>/` | GET | Outbox row detail: attempts, event log, retry/cancel/force-requeue flags. | **200** HTML. | Unknown `outbox_id` → **404**. |
| `/dlq/` | GET | Dead-letter queue listing (50/page). Query: `page`. | **200** HTML. | Invalid `page` clamped by paginator. |

---

## Campaign actions

| Route | Method | Permission | Purpose | Success | Bad input |
|-------|--------|------------|---------|---------|-----------|
| `/campaigns/<id>/trigger/` | POST | Operator | Immediately dispatch one campaign occurrence (creates outbox rows). | **302** redirect to dashboard (or safe `next`). Success flash with queued/enqueued counts. Audit event recorded. | Unknown campaign → error flash, **302**. Invalid state (`ValueError`/`RuntimeError`) → error flash, **302**. GET → **405**. Unauthenticated → **302** login. No permission → **403**. |
| `/campaigns/<id>/pause/` | POST | Operator | Pause an active or scheduled campaign. | **302**; success flash `Campaign <name> -> paused`. | Same error/permission/method rules as trigger. Service-layer rejection → error flash. |
| `/campaigns/<id>/resume/` | POST | Operator | Resume a paused campaign. | **302**; success flash with new status. | Same as pause. |
| `/campaigns/<id>/cancel/` | POST | Operator | Cancel a campaign. | **302**; success flash with new status. | Same as pause. |
| `/campaigns/<id>/<action>/` | POST | Operator | Any other `<action>` string. | **302**; error flash `Unknown campaign action`. | No state change. |

Valid actions: `trigger`, `pause`, `resume`, `cancel`.

---

## Outbox actions

Outbox POST actions always redirect to `/outbox/<outbox_id>/` (no `next` support).

| Route | Method | Permission | Purpose | Success | Bad input |
|-------|--------|------------|---------|---------|-----------|
| `/outbox/<id>/retry/` | POST | Operator | Requeue a failed, dead-lettered, or pending row for send. | **302** to outbox detail; success flash. | Missing row or invalid transition (`ValueError`) → error flash, **302**. GET → **405**. |
| `/outbox/<id>/cancel/` | POST | Operator | Cancel a cancellable row (`pending`, `enqueued`, `retry_scheduled`, `requeued`). | **302**; success flash. | Same error rules as retry. |
| `/outbox/<id>/force_requeue/` | POST | Operator | Recover a stuck `claimed` or `sending` row. | **302**; success flash. | Same error rules as retry. |
| `/outbox/<id>/<action>/` | POST | Operator | Unknown action string. | **302**; error flash `Unknown outbox action`. | No state change. |

---

## DLQ

| Route | Method | Permission | Purpose | Success | Bad input |
|-------|--------|------------|---------|---------|-----------|
| `/dlq/<outbox_id>/requeue/` | POST | Operator | Retry a dead-lettered outbox row (same service path as outbox retry). | **302** to `/dlq/` (or safe `next`); success flash. Audit event `dlq_requeue`. | Missing row or `ValueError` → error flash, **302**. GET → **405**. |

---

## Suppression and subscription

All accept optional `next` POST field (same-host only). Default redirect: dashboard.

| Route | Method | Permission | POST fields | Success | Bad input |
|-------|--------|------------|-------------|---------|-----------|
| `/suppress/` | POST | Operator | `email` (required), `reason` (optional, default `operator`) | **302**; success flash. Email normalized to lowercase. Audit event recorded. | Empty `email` → error flash, **302**. |
| `/unsuppress/` | POST | Operator | `email` (required) | **302**; success flash if entry removed. | Empty `email` → error flash. Unknown email → warning flash (no error), **302**. |
| `/subscription/` | POST | Operator | `email` (required), `action` (`subscribe` or `unsubscribe`) | **302**; success flash with new subscription state. | Empty `email` → error flash. Invalid `action` → error flash. Unknown recipient (`ValueError`) → error flash. |

---

## HTMX partials

Fragment endpoints polled or swapped by the dashboard. Require **login** only.

| Route | Method | Purpose | Success | Bad input |
|-------|--------|---------|---------|-----------|
| `/partials/stats/` | GET | Dashboard stat counters. Optional query: `campaign_id` (integer). | **200** HTML fragment. | Non-integer `campaign_id` is ignored; returns global stats (**200**, not **500**). |
| `/partials/outbox/` | GET | Recent outbox table panel. Query: `outbox_page`. | **200** HTML fragment. | Invalid page clamped by paginator. |
| `/partials/system/` | GET | Throughput and rate-limit status panel. | **200** HTML fragment. | N/A |

---

## Related documentation

- Operator permission is granted via Django admin (`campaigns.operate_campaign`) or the seeded
  `operator` user from `emailauto_seed`.
- Deep health probe behavior is also summarized in the [README production notes](../README.md#production-notes).
- Django Admin lives at `/admin/` (separate from these routes; staff/superuser required).
- Route-by-route test coverage: [test_matrix.md](test_matrix.md).
