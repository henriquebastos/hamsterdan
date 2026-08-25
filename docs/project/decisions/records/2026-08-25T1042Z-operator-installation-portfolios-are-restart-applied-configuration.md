---
status: Decided
raised: 2026-08-25
decided: 2026-08-25
recorded: 2026-08-25T1042Z
deciders:
  - Henrique (Navigator)
supersedes_in_part:
  - 2026-08-01T0203Z-hamsterdan-is-a-standalone-petrus-application.md
  - 2026-08-01T0335Z-githubkit-and-a-durable-relay-own-provider-ingress.md
related:
  - CV19
---

# Operator installation portfolios are restart-applied configuration

## Decision

One operator-controlled Hamsterdan instance may use one GitHub App registration
across multiple configured installation accounts and multiple selected
repositories. The configuration is an authority allow-list, not a SaaS tenant,
user-account, billing, or administration model. GitHub must first install the
App and grant its permissions on each configured account; configuration admits
that provider-owned installation but does not create it.

The first application mechanism is a supervised restart. A replacement
configuration must validate as one complete snapshot before publication. On
startup the host validates every configured installation and repository, then
atomically reconciles the complete routing portfolio before starting webhook
or recovery workers. Added routes become admissible. Removed routes admit no
new work and fence pending effects through current routing authority while
retaining durable state.

Live reload by signal or file watch is deferred. It may later apply the same
validated snapshot atomically without process restart; it must not introduce a
second configuration or routing contract.

One App registration remains the selected first-release boundary. Using that
registration outside its owning GitHub account requires a separately approved
provider visibility/installability change. That change does not turn the
self-hosted runtime into SaaS. Supporting several private App registrations in
one process would add multiple App keys, webhook secrets, and registration
identities and is not selected.

## Consequences

- The single-installation-account limit in the two linked 2026-08-01 decisions
  is superseded; their remaining architecture, custody, and ingress rulings
  stand.
- Configuration identifies accounts and repositories with stable GitHub IDs
  plus expected names. Installation tokens remain discovered, short-lived
  provider artifacts.
- The existing runtime's installation- and repository-keyed state is retained.
  Configuration, registration inventory, portfolio reconciliation, health, and
  operator deployment must be generalized before production launch.
- The current HBNetwork private App and `demo-pr-readiness` repository remain
  the first controlled qualification target. No App visibility change or
  second installation is authorized by this decision alone.
