---
code: CV1
level: Value
status: Active
status_reason: The standalone project boundary is being established before GitHub App authentication and behavior transfer
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
