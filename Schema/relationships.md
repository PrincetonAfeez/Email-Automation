# Schema Relationships

## Core flow

1. An `EmailTemplate` stores reusable subject and body templates.
2. A `Recipient` stores an email address, display name, subscription flag, and JSON personalization fields.
3. A `RecipientList` groups recipients through the `recipients_recipientlist_recipients` join table.
4. A `Campaign` links one template to one recipient list.
5. A `CampaignSchedule` defines when the campaign should run.
6. A `CampaignRun` represents one schedule occurrence.
7. An `EmailOutbox` row is created per campaign run and recipient. It stores immutable template snapshots and an idempotency key.
8. `EmailSendAttempt` rows record provider-level send attempts for each outbox row.
9. `EmailEventLog` rows provide a durable audit trail across campaign, run, recipient, and outbox activity.
10. `SuppressionEntry` stores email addresses that should be skipped before sending.

## Relationship map

| Parent | Child | Relationship | Delete behavior |
|---|---|---:|---|
| EmailTemplate | Campaign | 1 to many | Restrict template deletion while campaigns reference it |
| RecipientList | Campaign | 1 to many | Restrict list deletion while campaigns reference it |
| RecipientList | Recipient | many to many | Join rows cascade |
| Campaign | CampaignSchedule | 1 to many | Cascade |
| Campaign | CampaignRun | 1 to many | Cascade |
| CampaignSchedule | CampaignRun | 1 to many | Cascade |
| Campaign | EmailOutbox | 1 to many | Cascade |
| CampaignRun | EmailOutbox | 1 to many | Cascade |
| Recipient | EmailOutbox | 1 to many | Restrict recipient deletion while outbox rows reference it |
| EmailTemplate | EmailOutbox | 1 to many | Restrict template deletion while outbox rows reference it |
| EmailOutbox | EmailSendAttempt | 1 to many | Cascade |
| Campaign / CampaignRun / EmailOutbox / Recipient | EmailEventLog | optional many to one | Mostly cascade; recipient becomes null |

## Important uniqueness rules

- `EmailTemplate.name` is unique.
- `Recipient.email` is unique and normalized to lowercase in the model.
- `RecipientList.name` is unique.
- `SuppressionEntry.email` is unique and normalized to lowercase in the model.
- `Campaign.name` is unique.
- `CampaignRun.run_key` is unique.
- A schedule can only have one run for the same scheduled time: `(schedule_id, scheduled_for)`.
- `EmailOutbox.idempotency_key` is unique.
- Attempt numbers are unique per outbox row: `(outbox_id, attempt_number)`.
