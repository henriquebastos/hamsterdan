---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/index.md
---

# RS-019 — Improve V5 test reading locality

## Existing field to refine

Hamsterdan's V5 semantic journeys and deterministic recovery World already prove
important behavior. ES-009 found three areas where the evidence is harder to
read than the behavior requires:

- the Git-ambiguity World relies on continuous independent-checker parity rather
  than directly asserting its pivotal intermediate state;
- the shared semantic-journey harness constructs a 38-field `JourneyResult`
  positionally; and
- two reminder tests name lookup or cross-restart ambiguity that their bodies do
  not exercise at that exact cut.

These are test-maintainability concerns. Production behavior, topology, durable
contracts, provider effects, and operator behavior remain unchanged.

## Candidate boundary

Improve the locality of existing test evidence without redesigning the shared
scenario harness or changing the production workflow.

In scope:

- one direct intermediate-state assertion in the fixed Git-ambiguity World test;
- keyword construction for the existing `DraftPhase`, `StaleBasePhase`,
  `CollaborationPhase`, and `JourneyResult` aggregates;
- reminder test names and assertions which identify the exercised recovery cut;
  and
- focused validation of the affected semantic and recovery tests.

Out of scope:

- splitting `tests/integration/host/test_readiness_scenarios.py`;
- changing scenario behavior or adding a new production promise;
- renaming `ProvisionalHead` or another durable V5 contract;
- changing CV18's accepted `ref_cas` fault vocabulary;
- modifying production recovery, authority, lifecycle, or Git publication code;
- resolving the missing-canonical-History finding, which is owned separately by
  [RS-020](rs-020-fail-closed-on-missing-canonical-history.md); and
- pulling this Refinement Story into active work.

## Change Requests

### CR-001 — Assert the head-first ambiguity blocker directly

Status: Parked

Context:

`tests/integration/testing/test_readiness_world.py::test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash`
admits H1 and drains successful H1 CI and review before authorizing publication
recovery. The independent checker enforces that readiness remains closed, but the
test does not state that intermediate observation directly.

Requested change:

After H1 admission and before comment 502, record one read-only observation and
assert that:

- independent expected readiness is false;
- no current provider-visible readiness exists for H1;
- mutation ambiguity is the blocker; and
- canonical Git custody still ends in `FaultM`.

Expected leverage:

A reader can see the journey's central safety state without reconstructing
checker cadence or joining the final assertions backward.

Likely files:

- `tests/integration/testing/test_readiness_world.py`

Validation seed:

```sh
uv run --frozen pytest -q \
  tests/integration/testing/test_readiness_world.py::test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash
uv run --frozen pytest -q \
  tests/integration/testing/test_readiness_campaign.py::test_generated_v5_git_publication_recovery_schedules_replay_exactly
scripts/check quick
```

Implementation must first confirm that the read-only observation does not alter
the exact replay contract or operation count.

### CR-002 — Name every shared journey result field at construction

Status: Parked

Context:

`tests/integration/host/test_readiness_scenarios.py::_run_journey` constructs
`DraftPhase`, `StaleBasePhase`, `CollaborationPhase`, and the 38-field
`JourneyResult` positionally. Reviewers must match constructor position to
dataclass position when tracing any of the eleven semantic journeys. The largest
risk is `JourneyResult`, but all four aggregates have the same locality failure.

Requested change:

Replace the positional `DraftPhase(...)`, `StaleBasePhase(...)`,
`CollaborationPhase(...)`, and `JourneyResult(...)` constructions with explicit
keyword arguments. Preserve the dataclasses, captured values, assertions,
scenario branches, and production behavior.

Expected leverage:

Each captured value becomes locally attributable at its construction boundary,
and future field changes cannot silently shift neighboring arguments. One
consistent construction rule is easier to review than treating only the largest
aggregate differently.

Likely files:

- `tests/integration/host/test_readiness_scenarios.py`

Validation seed:

```sh
uv run --frozen pytest -q tests/integration/host/test_readiness_scenarios.py
scripts/check quick
```

### CR-003 — Make reminder recovery tests name their exercised cuts

Status: Parked

Context:

`tests/integration/testing/test_readiness_world.py::test_real_host_recovers_one_ambiguous_reminder_after_timer_maturity_and_crash`
models an accepted reminder with a lost response, but `CommentPublisher` finds
the immediately visible marker and returns `existing` before the World crash.
The later restart proves timer and host reconstruction after recovery rather
than unresolved reminder ambiguity across restart.

`tests/unit/readiness/net_v5/test_reminders_loop.py::TestMaturity::test_a_repeated_maturity_reconciles_lookup_first`
delivers the old maturity after the first fold has advanced the clock to the
next timer. The exact-clock guard makes that fact inert before another
`reminder_gate` lookup. Focused gate, publisher, and inline-restart tests own the
lookup-first claim.

Requested change:

Rename or sharpen these two tests so each name states its actual cut. Preserve
the fixed World's response-loss, reconstruction, checker, and replay evidence.
Preserve the reminder-loop test's repeated-maturity and single-effect evidence.
Do not duplicate the existing cross-head and lost-terminal lookup portfolios.

Expected leverage:

A reader can distinguish provider-response recovery, Activity-terminal recovery,
timer reconstruction, and stale maturity suppression without following helper
calls into the modeled provider or Activity ledger.

Likely files:

- `tests/integration/testing/test_readiness_world.py`
- `tests/unit/readiness/net_v5/test_reminders_loop.py`

Validation seed:

```sh
uv run --frozen pytest -q \
  tests/integration/testing/test_readiness_world.py::test_real_host_recovers_one_ambiguous_reminder_after_timer_maturity_and_crash \
  tests/unit/readiness/net_v5/test_reminders_loop.py::TestMaturity
uv run --frozen pytest -q \
  tests/unit/readiness/net_v5/test_inline_recovery.py::test_reminder_reconciles_before_claim_and_recipient_reads_after_two_lost_terminals \
  tests/unit/github_app/test_github.py::test_operation_scoped_reminder_reconciles_presence_only_across_a_head_move
scripts/check quick
```

## Pull state

This candidate is captured but not pulled. All three Change Requests are parked.
No implementation, test mutation, production change, commit, or release scope is
authorized by this record.

A future Navigator may pull the whole Refinement Story, select one Change Request
only, revise the boundary, or reject the candidate.
