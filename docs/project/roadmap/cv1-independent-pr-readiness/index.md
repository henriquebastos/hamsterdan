---
code: CV1
level: Value
status: Completed
status_reason: The private App identity, full rerun workflow, restart/remint, and duplicate-delivery behavior are proven live on HBNetwork
updated: 2026-08-01
---

# CV1 — Independently identifiable PR-readiness application

## Intent

Deliver Hamsterdan as a durable, independently visible GitHub application that
coordinates qualified PR-readiness behavior through Petrus without exposing
provider credentials to agents or coupling workflow semantics to GitHub.

## Scope and sequence

1. [CV1.DS1 — Private GitHub App identity](cv1-ds1-private-github-app-identity.md)
   establishes the standalone project, App authentication, HBNetwork sandbox
   instance, qualified behavior transfer, and visible real-GitHub evidence.

## Done condition

Given an HBNetwork-owned private Hamsterdan App installed on selected sandbox
repositories
When developers interact with a controlled pull request
Then Hamsterdan visibly owns its comments and admitted effects
And one durable Petrus Instance coordinates qualified readiness behavior
And GitHub credentials remain in the trusted host
And restart, expiry, duplicate delivery, stale work, rollback, and installation
lifecycle behavior are proven without a human PAT writer.

## Completion evidence

The accepted live portfolio is
[PR 14](https://github.com/HBNetwork/demo-pr-readiness/pull/14): an App-authored
one-file commit triggered an intentional first-attempt failure,
`hamster-dan[bot]` published the exact rerun marker, the strict broker reran the
same workflow and head, attempt 2 passed, and the App published its dashboard
and readiness advisory. A subsequent host restart minted a fresh one-hour
installation token, reconciled unchanged history, and deduplicated a provider
redelivery without another effect.
