# Webhook Inbox

The database table where every incoming GitHub webhook is saved before anything else happens. The HTTP handler verifies the signature, writes the row, and answers 200; a worker processes rows later, dropping duplicates by delivery id.

- Use when: the durable table where raw deliveries wait to be processed.
- Do not use for: the per-subnet inbox slots inside the PR workflow.
- Avoid: custody, webhook custody, delivery custody.
- Related: [Intake](intake.md), [PR Identity](pr-identity.md)
