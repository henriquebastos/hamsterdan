# DS5 concept extraction

## Source

- Delivery Story: [`../cv20-ds5-settle-agent-round.md`](../cv20-ds5-settle-agent-round.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Authority claim", "Protocol values", "Durable execution lifecycle", "Pi
  and workspace" and "Exact delivered result"
- Cumulative sequence: [`../delivery-sequence.md`](../delivery-sequence.md),
  "DS5 — One reconstructible agent round"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS5 introduces a credential-free agent execution whose logical operation and
attempt determine one stable execution identity. Submit, acceptance, terminal
availability and receiver delivery are distinct durable positions; retained
lookup precedes another start or delivery. Readiness receives the exact typed
delivered result and returns a classified terminal to the original occurrence.
Protected findings work also introduces the complete readiness-owned authority
claim composed from a durable grant, fresh provider read and fresh host evidence.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–24 | One workflow review request reaches one retained exact result and returns after restart-safe lookup | agent round, agent execution, exact delivered result |
| Vertical path, lines 26–37 | Workflow request, readiness projection, host route, agent lifecycle, delivered lookup and terminal admission remain distinct | agent request/result, operation route, agent delivery |
| Fixed design, lines 64–86 | Stable execution identity, four durable positions, one start/delivery, exact typed lookup, split custody and bounded cleanup are fixed | execution identity, durable agent lifecycle, agent custody |
| Fixed design, lines 78–82 | Findings begins under a complete three-source readiness-owned claim; DS9 later completes the policy matrix | authority claim, current-authority policy |
| API contracts / Authority claim, lines 81–107 | Claim has phase/incarnation/head/base/policy and requires durable readiness, fresh provider and fresh host agreement | AuthorityClaim as enduring candidate; fields subordinate |
| API contracts / Durable execution lifecycle, lines 683–699 | Submit→accepted→terminal available→delivered is durable and lookup-first with one start/receiver terminal | agent execution lifecycle |
| API contracts / Pi and workspace, lines 701–709 | Agent adaptation/workspace stay credential-free while host owns runtime and secret lifetime | credential boundary and split custody |
| API contracts / Exact delivered result, lines 711–720 | Publication must consume the exact accepted result, not invoke or manufacture another | exact delivered result |
| Delivery sequence / DS5, lines 186–197 | DS5 hands off one-start/one-delivery execution under first strong three-source authority policy | candidates survive into mutation and repair |

## Later ownership and refinements

- DS6 adds conversation and coding request/result variants to the same agent
  lifecycle and makes Git publication depend on the exact delivered coding
  result (DS6 Outcome, lines 18–24; Fixed design, lines 74–84).
- DS7 reuses the established agent and mutation chain for persistent regression
  rather than creating a repair shortcut (DS7 Fixed design, lines 69–72).
- DS8 routes deferred review through established agent seams while preserving
  original Activity/operation correlation (DS8 Fixed design, lines 80–81).
- DS9 retains the complete claim and three-source composition, and completes
  operation-specific and lifecycle policies without changing claim meaning
  (DS9 Fixed design, lines 68–93).
- DS11 extends host route/resource composition across multiple PRs; it does not
  move agent meaning into host (DS11 Vertical path, line 30; owned paths, line
  65).

## Subordinate vocabulary to evaluate

- `RoundOpen` and `AgentReview` are request/terminal API variants for a review
  Activity, not the general agent-execution concepts.
- submit, accepted, terminal available and delivered are positions within one
  durable lifecycle, not four standalone concepts.
- cancellation, timeout and cleanup failure are closed terminal variants.
- logical operation, attempt and Pi execution ID are identity vocabulary;
  `pi:sha256(...)` is a fixed grammar, not a separate domain concept.
- protocol codecs, workspace/archive mechanics and runtime route method names
  are API or implementation vocabulary.

## Unresolved DS-review items

- review request/result/envelope fields and codec API;
- execution and operation grammar representations;
- submit, lookup, step, cancel, timeout, deliver and delivered APIs;
- Pi/workspace calls and host route custody APIs;
- authority claim, evidence, factory and findings-fence APIs;
- result classification and original-occurrence admission; and
- error taxonomy and calibrated runtime/workspace/retention bounds.

## Construction-only exclusions

- Pi correspondence fixtures, optional authenticated evidence and checker/
  simulation mechanics qualify the behavior but are not product concepts.
- Temporary replacement route/execution stores and paths do not survive DS13
  under those construction names.

## Trace handoff

The DS6–DS13 trace is complete in the
[candidate register](candidate-register.md). Whether agent round is only a use
of durable agent execution remains for later Navigator review.
