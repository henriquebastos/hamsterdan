---
status: Active
captured: 2026-08-27
navigator: Henrique
source: CV20 coherence verification
---

# RS-035 — Make orb setup independent of ambient USER

## Existing field to refine

`.agents/setup` runs with `set -u` and passes `$USER` to `usermod` while
enabling Docker feedback. The orb-setup test sandbox deliberately supplies a
minimal environment without `USER`, so setup aborts before reaching the
behavior each test exercises. At the CV20 history checkpoint, `scripts/check
full` reported 1,151 passing tests and 14 failures with the same
`.agents/setup:229: USER: unbound variable` cause; the setup script and tests
matched `origin/main` exactly.

## Candidate boundary

Resolve the effective setup account without trusting ambient `USER`, preserve
the existing Docker group/socket behavior, and cover missing or contradictory
identity environment. The correction should restore the full gate without
weakening the scrubbed-environment tests or broadening setup authority.

## Change Request

### CR-001 — Resolve the setup account from process-owned identity

Status: Implemented within the accepted RS-037 work; acceptance/history pending.

RS-037 replaced the ambient `$USER` argument with `id -un` while preparing the
new build authentication path. Linux tests cover both an absent USER and a
contradictory value and verify that the effective process identity reaches
`usermod`. The Docker group and socket behavior is unchanged.
