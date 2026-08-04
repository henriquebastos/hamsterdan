---
code: CV4.DS1
level: Delivery Story
status: Accepted Live
status_reason: PR47 completed the bounded three-actor journey with four native findings, two confirmed App mutations, green current-head CI, distinct approval, readiness, and safe unmerged closure
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

## Live acceptance

The existing runtime custodian deployed exact Hamsterdan SHA
`7df9baf5847726f22f94d1512f56a5c07ed91787`. Fresh PR47 began at human-authored
head `d231386f02837f22f773f78be6b14efd4b614f36`. Dan published the three required
native review shapes exactly once, and Henrique's exact digest confirmation
authorized a three-line repair at App-authored head
`ac5739ad96a7691ecf7c7a6384c4298edffb3386`.

The repaired code exposed a deterministic demo-gate defect. Correction PR48
made CI accept only the exact seeded state or exact complete repaired state and
reject partial repairs. Its merge advanced the strict base. Dan published a
fourth native finding, then a second exact confirmation authorized one App-owned
base merge at final head `47e7e9be7bb7b3dc8e6d886f3d4f09fe95e71332`.
All six checks passed on attempt 1, coordinating review cleared all four finding
lineages, Cris resolved all four native threads and approved the exact current
head, and dashboard plus readiness publication converged.

The instance completed 67 Activity requests with 67 completions, zero failures,
and zero unresolved work. The inbox drained to zero pending and zero failed.
Henrique closed PR47 unmerged; closure produced no later Activity, comment,
review, commit, dashboard update, or readiness loop. Runtime custody was
preserved and the supervised host stopped safely.
