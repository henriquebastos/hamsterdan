---
status: Resolved
raised: 2026-08-18
resolved: 2026-08-18
owner: CV18.DS3
related:
  - CV18.DS2
  - CV18.DS3
---

# Readiness DST composition must split before campaign expansion

CV18.DS2's accepted vertical keeps provider truth, strict GitHub transport,
agent adapter, Petrus profile, independent checker, author-facing Timeline, and
replay composition in one 1,495-line `readiness_world.py`. That made the first
end-to-end ownership path reviewable without inventing reusable layers before
the Petrus seam existed, but adding generated fault families in place would
cross the project's coherent-module boundary.

This does not block DS2: the module owns one fixed, bounded production-host
scenario profile and its behavior is covered as a unit. It blocks DS3
vocabulary expansion. Before adding generated commands or new provider fault
families, split provider truth and boundary adapters from the
profile/checker/Timeline composition. Preserve one interpreter, public
`petrus.testing.dst` imports, artifact/profile/checker identities, strict
detached values, and the existing vertical replay. Do not create one file per
noun or move concrete sibling composition outside `host`.

Resolution requires behavior-preserving focused and exact-replay tests across
the split, followed by at least one generated dimension using the resulting
boundary without circular imports or mutable global registration.

## Current state

Resolved by CV18.DS3. Its prerequisite slice completed and fully verified the
behavior-preserving split: shared strict contracts, modeled provider truth, and
real-host DST composition have separate acyclic owners; exact profile and
checker identities are characterized; and the accepted vertical replay remains
green.

The next accepted slice satisfied the remaining resolution condition by
running one bounded Hypothesis state machine through that split. It generates
one-step host progress, duplicate delivery, effect ambiguity, and abrupt
reconstruction without circular imports or mutable global registration, then
exactly replays both successful schedules and a retained checker failure.
Broader campaign vocabulary remains planned DS3 scope rather than debt in this
ownership boundary.
