---
status: Active
pulled: 2026-08-10
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-002 — Move Activity execution mechanics into Motus

## Existing field being refined

Hamsterdan's readiness Net correctly preserves asynchronous request/result
boundaries and current-authority acceptance, but it also expresses execution
mechanics that should be reusable Motus behavior. Dashboard and readiness
publication use explicit lease, delayed retry, due, reissue, and retirement
places because Motus lacks classified durable backoff and terminal-failure
projection. Smaller stateless bridges and behaviorless result paths remain.

## Refinement boundary

Simplify the production Net in two coherent layers. First remove only
behaviorless or redundant current-Petrus topology. Then extend Petrus/Motus with
provider-neutral logical Activity execution policy, integrate its accepted
revision, and remove Hamsterdan's publication retry mechanics.

Preserve exact request/result asynchronous boundaries where completion must
rejoin current concern ownership. Preserve PR/head/base/policy fencing,
same-generation operation supersession, provider lookup-first recovery,
business retry budgets, restart/replay, and the rule that Hamsterdan never
merges.

## Accepted execution structure

- This Hamsterdan thread owns the production lane.
- A dedicated Petrus subthread owns Motus production changes and reports only
  to this thread.
- Petrus is validated and pushed to `main` before Hamsterdan pins its exact
  accepted commit.
- Hamsterdan is then integrated, fully validated, documented, and pushed
  directly to `main`; no pull request is created.
- The independent scoped-lifecycle experiment has separate ownership and no
  reporting or implementation flow into this Refinement Story.

## Change Requests

| Change Request | Outcome |
| --- | --- |
| CR-001 Remove current-Petrus topology redundancies | Complete |
| CR-002 Add production Activity Execution policy to Motus | Active |
| CR-003 Pin accepted Petrus and migrate dashboard/readiness retry | Planned |
| CR-004 Migrate conversation and eligible provider retries | Planned |
| CR-005 Reassess residual concern-state ownership | Planned |
| CR-006 Review, coherence, and documentation | Planned |

## CR-001 scope

- Remove unused publication lease attempt counters.
- Remove the behaviorless reminder result and acceptance paths.
- Collapse only the stateless conversation-classification request bridge.
- Produce Actions decision basis after observation acceptance.
- Route intents only to their applicable destinations.
- Prove direct reminder timer rearming before removing its intermediate place.
- Replace avoidable History reconstruction with supported Engine projections and
  bind business operation identity to Motus invocation identity where current
  APIs safely permit it.

## CR-002 required Motus behavior

- Stable logical Activity identity across operational attempts.
- Classified retryable and non-retryable failures.
- Durable backoff with optional provider retry delay.
- Per-attempt start-to-close and aggregate schedule-to-close deadlines.
- Deterministic typed terminal-failure projection into the Net.
- Projection-only recovery after terminal success or failure.
- Conservative one-attempt defaults and provider-neutral vocabulary.
- A durable dispatch route for delayed attempts; no blocking sleep in
  `InlineDispatch`.

Cancellation is a follow-up unless required to complete these contracts safely.
PR authority and provider reconciliation remain application-owned.

## Validation contract

- Characterization tests precede every topology deletion.
- Topology counts and complete transition ownership are recorded per stage.
- Focused tests cover retry classification, exact identity, deadline exhaustion,
  projection recovery, same-generation supersession, stale authority, ambiguous
  provider recovery, restart, and replay.
- `scripts/check quick` follows each coherent Hamsterdan stage.
- Both repositories' full gates pass before their accepted `main` pushes.

## Progress

### 2026-08-10 — Closed the current-Petrus cleanup boundary

- Publication retry leases now retain only their exact immutable request; their
  unused attempt counters and test-only exposure are gone.
- Actions ingress and Activities emit only observations. `accept_actions`
  creates decision basis after currentness and novelty admission, so stale or
  duplicate observations cannot race policy against state folding.
- Conversation classification routes each intent only to its applicable
  mutation, disposition/reminder, or reply path. Status/no-effect intents no
  longer create three tokens merely to retire them, and the unreachable
  `retire.intent_noop` transition is gone.
- A direct reminder timer self-loop was rejected by experiment: the re-emitted
  token remained immediately mature. The intermediate rearm transition is the
  required fresh entry-instant boundary and remains.
- Reminder-result and stateless conversation-bridge removal would require
  bespoke Hamsterdan Activity handlers because current `DerivedActivityHandler`
  requires a typed output and cannot publish begin-time state. They are deferred
  to the general Motus boundary rather than reimplementing framework behavior
  locally. Current Engine projections likewise do not expose enough terminal
  phase/identity information to replace History inspection cleanly.
- The topology moved from 46 places, 162 transitions, and 481 arcs to 46 places,
  161 transitions, and 477 arcs. The full gate passes 446 Python tests with one
  provider test deselected, nine Bun tests, static analysis, formatting, and
  both package builds.
