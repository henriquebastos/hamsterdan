---
code: CV1.DS1
level: Delivery Story
status: Active
status_reason: Navigator approved standalone bootstrap and the HBNetwork private-instance validation model
updated: 2026-08-01
related:
  - docs/project/decisions/records/2026-08-01T0203Z-hamsterdan-is-a-standalone-petrus-application.md
---

# CV1.DS1 — Private GitHub App identity

## In scope

- Standalone Python package, tests, checks, Amp project, and Ariad memory.
- Exact pinned Petrus dependency and executable package boundaries.
- Bounded GitHub SDK adoption spike.
- App JWT and installation-token lifecycle.
- App-owned webhook custody and installation/repository routing.
- Transfer of qualified PR-readiness behavior under parity tests.
- Host-only composition through public Petrus Engine and Motus Activities.
- Minimal permissions/events, HBNetwork registration and installation bootstrap.
- Visible bot attribution, brokered rerun, guarded ref effects, restart, rollback,
  and real-provider acceptance evidence.

## Acceptance behavior

Given a private HBNetwork-owned Hamsterdan App with selected repository access
When a controlled pull request enters the readiness workflow
Then visible admitted comments and dashboard updates are attributed to the
Hamsterdan App
And exact installation/repository routing selects only the admitted authority
And one-hour token expiry, refresh, restart, suspension, deletion, and key
rotation fail safely
And duplicate or stale deliveries cannot duplicate or supersede fenced effects
And agent Activities receive no GitHub credential
And the currently working human-PAT deployment remains available as an isolated
rollback target until Hamsterdan is accepted.

## Out of scope

- Public App distribution or Marketplace publication.
- Generalized multi-registration tenancy in one host.
- Formal GitHub reviews, Checks, statuses, direct Actions writes, workflow
  editing, automatic merge, or bypass.
- AgentRunner, execution-environment, Dispatch-custody, or CV10 redesign.
- Broad internal renaming of transferred historical grammar and markers.

## Version intent

Remain at private `0.0.0` during delivery. Qualifying a `0.1.0` application
candidate requires the complete real-GitHub acceptance portfolio and separate
Navigator approval; no package or App publication is implied.
