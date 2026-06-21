# Out Of Scope

This capstone focuses on scheduled outbound delivery with a DB-owned outbox. The following
are deliberately **not** implemented:

- **Inbound bounce / complaint webhooks** (SES SNS, SendGrid events, etc.)
- **Automatic suppression from provider feedback loops**
- **Double opt-in subscription management** (only manual/import suppressions and the
  `Recipient.subscribed` flag checked at send time)
- **Per-recipient send-time timezone** (schedules evaluate in UTC; `timezone_name` is display-only)

These are reasonable extension points for a follow-on project: a webhook view that calls
`suppress_email(..., source=SuppressionEntry.Source.BOUNCE)` would integrate cleanly with the
existing send-path suppression check.
