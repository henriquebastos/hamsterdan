---
code: CV4.DS1
level: Delivery Story
status: Qualified Locally
status_reason: Implementation, compatibility, safety review, demo fixture, and full local suites pass; live provider evidence remains
updated: 2026-08-03
---

# CV4.DS1 — Native review and hero rehearsal

## Scope

- Treat the renamed `crisbastos` account as the current distinct reviewer while
  preserving accepted evidence recorded under its former `hsbastos` login.
- Give review and conversation agents the canonical Dan voice and align
  deterministic user-visible messages without changing machine grammar.
- Publish findings through native GitHub review comments at the exact head,
  including one-line suggestions and one primary anchor with bounded related
  locations.
- Register a deterministic, idempotent, multi-file `hero-review` fixture with
  exactly three independently discoverable defects.
- Give the operator a redacted way to prove the three native review shapes and
  a cohesive recording route for author, reviewer, and App.

## Local evidence

Hamsterdan's full project check passes 258 tests with one opt-in provider test
skipped; all nine relay tests pass. Focused agent, GitHub, activity, operator,
and application suites cover marker safety, exact-head payloads, suggestion and
related-location rendering, narrow fallback, ambiguous outcomes, retry fences,
legacy replay, deterministic voice, multi-file admission, and redacted hero
inspection.

The demo repository merged PR45 at
`51a265b0948c2b797f69f3c5f54f8d6b557f2592`. Its six GitHub checks passed. The
fixture's own suite passes 61 tests with two prepared-state skips, and its Ruff
and ty checks pass. First preparation changes exactly the manifest-admitted
selector and four payload targets; repetition is unchanged and inspection is
stable.

An independent implementation review found and required correction of broad
fallback classification, old-operation replay collisions, and marker injection.
The corrected implementation rejects `403`, `404`, and generic `422` responses,
recognizes only exact legacy bodies, restricts finding and marker identities,
and trusts only final App-owned marker lines.

## Live acceptance remaining

Deploy the exact Hamsterdan commit through the existing runtime custodian, then
create one fresh `hero-review` PR as `henriquebastos` with `crisbastos` requested.
Capture the three App-owned native finding shapes, App repair/head advance,
Henrique's status conversation, Cris's current-head review and approval, final
dashboard/readiness convergence, History/inbox stability, and unmerged closure.
No accepted CV3 PR may be reused or mutated.
