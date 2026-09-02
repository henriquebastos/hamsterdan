# Intake

Accepting one normalized GitHub observation into a pull request's History exactly once. Intake begins after raw Webhook Inbox retention: normalize, classify semantic equality, durably authorize a novel observation, and hand that exact observation to History.

- Use when: the exactly-once acceptance of events into a PR's history.
- Do not use for: deciding which repositories the app touches; that is the watchlist.
- Avoid: admission, when speaking of events; comment admission.
- Example: `recorded` means History accepted the observation; it does not mean the workflow completed that occurrence.
- Related: [Webhook Inbox](webhook-inbox.md), [Watchlist](watchlist.md)
