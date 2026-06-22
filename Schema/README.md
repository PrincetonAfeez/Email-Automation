# Email Automation Schema

This folder contains a simple, reviewer-friendly schema package for the Email Automation Django/Celery project.

## Files

- `schema.sql` — PostgreSQL-style reference schema for the project-owned Django models.
- `entities.json` — machine-readable entity, field, relationship, and index metadata.
- `relationships.md` — plain-English explanation of the data model relationships.
- `states.md` — campaign, run, outbox, attempt, schedule, suppression, and event state values.
- `erd.mmd` — Mermaid ER diagram you can paste into a Mermaid renderer or Markdown viewer that supports Mermaid.

## Scope

The schema focuses on the project-owned email automation tables:

- Email templates
- Recipients and recipient lists
- Suppression entries
- Campaigns
- Campaign schedules and campaign runs
- Email outbox rows
- Send attempts
- Email event logs

Django built-in tables such as auth, sessions, admin logs, and `django_celery_beat` tables are intentionally omitted so this folder stays simple and focused.
