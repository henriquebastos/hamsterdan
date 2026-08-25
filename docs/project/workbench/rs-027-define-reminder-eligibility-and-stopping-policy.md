---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/reminder-timer-recovery-journey.md
---

# RS-027 — Define reminder eligibility and stopping policy

## Existing field to refine

V5 currently runs one recurring reminder clock for every active PR incarnation.
Active head admission starts the clock, draft pauses it, ready-for-review resumes
it under a new incarnation, and close ends it. Human approval, requested changes,
unresolved conversations, and readiness publication do not control reminder
eligibility.

Concrete scenario: an active PR has successful CI, a clear agent review, zero
required approvals, no requested reviewer, and an existing readiness advisory.
At timer maturity Hamsterdan asks the author to assign a reviewer and immediately
arms the next reminder.

The implementation and lifecycle delivery records describe this behavior, but no
current product owner states whether reminders are meant for every active PR or
only while a human-readiness condition remains unmet. ES-009 discovered the gap
when its planned scenario assumed that missing qualifying human readiness was the
eligibility predicate.

## Candidate boundary

Select and document one reminder eligibility and stopping contract before
changing production behavior.

The current choices are:

1. retain lifecycle-driven reminders for every active PR;
2. make reminders depend on explicit human-readiness blockers, with named start,
   cancellation, resumption, and recipient rules; or
3. choose another bounded product rule.

If the current lifecycle rule is retained, add direct characterization and
operator-facing documentation rather than relying on topology inference. If the
rule changes, keep workflow policy in the readiness Net and keep timer custody,
provider rendering, and host scheduling free of product decisions.

## Correctness obligations for a future behavioral plan

- **Authoritative state.** Lifecycle continues to own active, draft, resumed, and
  closed incarnations. The selected human or readiness facts must have one named
  workflow owner.
- **Safety.** A stale eligibility fact, timer acknowledgement, or maturity cannot
  revive a canceled generation or publish under an unintended incarnation.
- **Liveness.** When the selected blocker becomes present, a fair environment
  eventually arms one timer. When it clears, the current timer reaches one
  explicit canceled, overdue, or retained disposition.
- **Bounds.** Keep one outstanding timer command and at most one armed timer per
  PR. Do not add polling or unbounded reminder work.
- **Races.** Cover approval or reviewer movement before arm acknowledgement,
  before maturity, while reminder publication is pending, and after a provider
  response is lost.
- **Recovery.** Preserve stable reminder operation identity and lookup-first
  settlement across restart and head movement.
- **Product effect.** State whether a ready PR, an approved PR, a PR with no
  requested reviewer, and a PR with unresolved conversations should each receive
  a reminder.

## Change Request

### CR-001 — Select the reminder eligibility contract

Status: Parked

A future Navigator session must answer this question in plain language:

> Which current PR condition makes a reminder useful, and which observed event
> should stop or postpone the next reminder?

Likely files after that ruling may include:

- `docs/product/` or another current product behavior owner;
- `src/hamsterdan/readiness/net_v5/life.py`;
- `src/hamsterdan/readiness/net_v5/reminders.py`;
- `src/hamsterdan/contracts/readiness_v5.py`;
- `tests/unit/readiness/net_v5/test_reminders_loop.py`;
- semantic or deterministic World tests; and
- operator documentation if cadence becomes configurable or observable.

Validation seeds:

- characterize the selected rule for active, draft, resumed, and closed PRs;
- cover zero and nonzero required approvals;
- cover requested reviewer assignment and removal;
- cover a blocker clearing before arm acknowledgement and before maturity;
- preserve timer-command, maturity, lookup-first, and restart portfolios;
- run `scripts/check quick` and `scripts/check full` before acceptance; and
- exercise a real provider route if the visible reminder experience changes.

## Pull state

This candidate is captured but not pulled. No product policy, runtime behavior,
timer cadence, publication rule, provider operation, launch prerequisite, or
release action is authorized by this record. ES-009 remains a learning session.
