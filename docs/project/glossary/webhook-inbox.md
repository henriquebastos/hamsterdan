# Webhook Inbox

The database table where every bounded, correctly signed GitHub webhook is saved as exact raw evidence before JSON parsing. The HTTP handler verifies the signature, writes the row, and answers 200. A later host-owned Webhook Inbox Worker normalizes it, classifies semantic equality, and hands only a novel observation to History.

- Use when: the durable table where raw deliveries wait and where their Intake handoff outcome is recorded.
- Do not use for: the per-subnet inbox slots inside the PR workflow.
- Avoid: custody, webhook custody, delivery custody.
- Example: two delivery IDs with the same PR observation occupy two Inbox rows, but only the first reaches History; the second is a semantic duplicate.
- Related: [Intake](intake.md), [PR Identity](pr-identity.md)
