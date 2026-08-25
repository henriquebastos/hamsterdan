# Engineering conventions

This document owns reusable implementation practice for Hamsterdan. Product and
architecture choices belong in decision records, accepted structural costs
belong in the debt ledger, and one change's findings belong in its roadmap,
Refinement, Exploration, or worklog record. Add a convention here only when a
practice should guide future changes.

A more specific decision, specification, or roadmap constraint overrides a
general convention. Surface the conflict during planning or review rather than
choosing silently. Promote mechanically checkable structure into the repository
quality gate when one clear test owner can enforce it.

## Architecture and boundaries

1. Import Petrus concepts from their defining ownership modules; never from the
   empty `petrus` root and never from an `impetus` compatibility namespace.
2. The host is the only concrete composition root. Sibling provider and domain
   packages share neutral contracts but do not import one another. Engine,
   concrete Dispatch, and Worker custody remain under `host`.
3. The readiness Net owns routing and workflow state. Activities perform typed,
   Petri-agnostic work and return frozen JSON-faithful results. If an Activity
   cannot derive cleanly, first inspect whether routing, classification, a join,
   reservation, or authority transfer is hidden outside the Net.
4. Normalize provider data at the boundary. GitHubKit and provider HTTP values
   remain in `github_app`; FastAPI remains at the host HTTP boundary. Do not let
   SDK or HTTP types cross into contracts, readiness, or the Net.
5. Keep CLIs, servers, workers, and transports as thin adapters over importable
   operations. Parse syntax and operator intent at the outside edge; inner
   operations return values or structured reports rather than printing or
   exiting.
6. Prefer coherent modules over one file per noun, but split responsibilities
   before provider, workflow, and hosting concerns accumulate in one module.
   Use a function for a narrow operation with little state. Use an object when
   bound state materially reduces the interface or enforces an invariant.

## Durable values and effects

7. Validate semantic invariants at the boundary that owns them and before
   recording an irreversible fact. Once a webhook, History fact, or Activity
   result becomes durable, later code may rely on it without repeating foreign
   input validation.
8. Snapshot a payload into its canonical durable representation when equality
   controls deduplication, acknowledgement, conflict detection, or recovery.
   Reject an unencodable value at the admitting boundary rather than after a
   partial durable write.
9. Pass a ruled seam contract across the seam whole. An Activity receives the
   typed invocation fields needed for execution and recovery, including current
   authority, operation identity, correlation, and resolved policy. Do not
   replace that carrier with a convenient projection that drops a ruled field.
10. Effects are at-least-once. Spend operation identity at the provider call,
    fence current authority immediately before mutation, and recover uncertain
    outcomes lookup-first. Tests and documentation state the weakest honest
    guarantee and never claim exactly-once effects.
11. An Activity retry policy follows mutation order. Retry failures that happen
    before mutation. A mutating Activity earns retries only through a permanent
    callee-owned idempotency key or an equivalent lookup-first recovery contract.
12. Credentials are opaque, redacted, host-owned values. Logs use identifiers,
    request IDs, rate-limit facts, and bounded error classes, never tokens, keys,
    authorization headers, or indiscriminate payloads. Agent territory receives
    only bounded credential-free values.

## Tests and evidence

13. Test public behavior and the reason it matters rather than incidental helper
    decomposition. A pure semantic unit still earns a direct test when that test
    names a failure more precisely than broader pipeline coverage.
14. Patch at the seam the unit owns. Prefer strict, small fakes whose unknown
    inputs fail loud. A stand-in must not invent plausible responses.
15. Assert complete records when shape is the contract, including ordering,
    multiplicity, payload, operation identity, and correlation. Use partial
    assertions only for fields that are genuinely dynamic and irrelevant to the
    behavior under test.
16. Performance claims require a named bounded workload, concurrency and
    environment, timing or memory evidence, observed failures, and relevant
    ordering or cache caveats. An architectural improvement alone is not a
    throughput claim.
