# Intake

Accepting one GitHub event into a pull request's history exactly once: normalize it, drop duplicates, record it durably before acting on it.

- Use when: the exactly-once acceptance of events into a PR's history.
- Do not use for: deciding which repositories the app touches; that is the watchlist.
- Avoid: admission, when speaking of events; comment admission.
- Related: [Webhook Inbox](webhook-inbox.md), [Watchlist](watchlist.md)
