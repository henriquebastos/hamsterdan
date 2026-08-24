---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/candidate-review.md
---

# RS-025 — Make the current V5 maintainer route explicit

## Existing field to refine

ES-009 produced three current vertical reading routes: clean-green
reconciliation, automatic CI repair, and ambiguous Git publication recovery.
They are easy to follow after a maintainer reaches the exploration index, but
the README's normal source-reading path does not link to them.

The same review found several local terminology and documentation seams:

- `docs/project/briefing.md` says canonical History is reconstructible, while
  current evidence supports reconstructing runtime state from intact canonical
  History and identifies missing History as RS-020;
- the development guide does not explain why some `tests/unit` modules use real
  Engine, JSONL, and SQLite implementations;
- `_terminal_operations` actually returns logical agent operations that History
  proves settled, excluding terminal `FaultM` and `RoundDeferred` occurrences;
- `fault_git_publication(..., "ref_cas")` is accepted low-level simulation
  vocabulary but reads poorly in journey-level tests whose scenario is an
  accepted ref update with a lost response and temporarily unavailable proof;
- `FaultM` and `CurrentClaim` docstrings do not state their complete current
  roles; and
- `real_provider_acceptance` is an intentionally reserved opt-in safety marker
  with no current marked test.

Durable V5 types and accepted simulation artifact vocabulary remain valid. The
refinement should improve the maintainer route without renaming persisted colors,
operations, or replay fields.

## Candidate boundary

Treat the work as independent parked Change Requests. A future session may pull
one without taking the whole story.

### CR-001 — Link the three guided V5 journeys from the README

Status: Parked

Add a short maintainer-reading section after the current architecture source
list. Link clean green, automatic CI repair, and ambiguous Git recovery. Use
"automatic CI repair" in prose so readers do not confuse the evidence-authorized
`repair` rung with a human-authorized conversational `change`.

Likely file:

- `README.md`

### CR-002 — Correct current History and test-layer documentation

Status: Parked

Update the briefing to state that Hamsterdan reconstructs runtime state and
projections from intact canonical History. Missing or torn canonical History is
not reconstructed from projections and remains owned by RS-020.

Add a concise test-layer guide based on the tested seam:

- root architecture/distribution rules;
- local subsystem and real-Net tests under `tests/unit`;
- composed host semantic journeys;
- deterministic World, generated schedules, replay, and coverage; and
- separate opt-in real-provider evidence.

State that `real_provider_acceptance` is intentionally reserved even while it
selects no current test.

Likely files:

- `docs/project/briefing.md`
- `docs/process/development-guide.md`

### CR-003 — Name logical agent-operation settlement accurately

Status: Parked

Rename private `_terminal_operations` and its local variables to describe
logical agent operations that canonical History proves safe to settle. Clarify
that `FaultM` terminates one Activity occurrence while leaving the logical
mutation unresolved, and that `CurrentClaim` represents the complete authority
tuple used for persisted grants and fresh gate comparisons.

Do not rename durable `FaultM`, `ProvisionalHead`, operation identities,
transition paths, or stored schemas.

Likely files:

- `src/hamsterdan/host/agenticus.py`
- `src/hamsterdan/contracts/readiness_v5.py`
- `src/hamsterdan/host/v5/claim.py`
- focused agent-route tests

### CR-004 — Add journey-level vocabulary for a lost Git publication response

Status: Parked

Add a semantic Timeline helper such as `lose_git_publication_response` and use it
at the human-readable fixed and generated journey call sites. Keep
`fault_git_publication` and the accepted `ref_cas` value as the low-level fault
activation and exact replay vocabulary.

Likely files:

- `src/hamsterdan/host/testing/readiness_world.py`
- `tests/integration/testing/test_readiness_world.py`
- `tests/integration/testing/test_readiness_campaign.py`

Validation must prove that the convenience helper does not change artifact
encoding, operation counts, semantic coverage, or exact replay.

## Pull state

This candidate and all four Change Requests are captured but parked. No README,
briefing, process guide, private helper, durable type, simulation artifact,
commit, or release change is authorized by this record. ES-009 remains a
learning session.
