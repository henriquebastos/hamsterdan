---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-011 — Make agent execution identity explicit

## Existing field refined

Agent Activities used a two-call protocol before every provider call. The host
first claimed durable route ownership through `agent_dispatch(operation,
attempt)` and, for Pi, wrote a derived runtime identity into a `ContextVar`.
The subsequent `AgentRunner` call implicitly consumed that ambient value.
Correctness therefore depended on call order and process-local mutable scope.

## Accepted boundary

Every `AgentRunner` method now receives the logical `operation` and positive
`attempt` explicitly. `RoutedAgentRunner` is the host-owned composition edge:
it validates the Attempt, atomically claims the logical operation against the
active `AgentComposition`, runs the optional qualification hook after custody
exists, and delegates the unchanged pair.

Provider execution identity belongs to the provider adapter. `PiNativeRunner`
alone derives `pi:sha256(operation + "\\0" + attempt)` for runtime, workspace,
Episode, and Turn identity. Replay of one Attempt is stable; later Attempts are
distinct. Route settlement and restart repair remain keyed only by the logical
operation. RS-013 subsequently removed the legacy Amp adapter entirely.

The `ContextVar`, `OperationRoutedRunner`, `route_operation`, `agent_dispatch`,
and Activity-side fault-routing surfaces were deleted. No generalized
execution-scope value or serialized runtime context was introduced.

## Validation and review

Focused agent, Agenticus, Activity, application, and service evidence passed
209 tests with one explicitly external test skipped. `scripts/check quick`
passed static, format, and production type checks. `scripts/check full` passed
package and relay gates, then 593 Python tests with one explicitly external
route deselected. Adversarial review initially found qualification-before-claim
and logical/provider identity ambiguity; both were corrected. Final review
returned `APPROVE` with no release blocker.

## Consequences

- Agent invocation has one explicit call boundary instead of an ambient
  selection handshake.
- Durable route ownership remains host composition; Pi runtime identity remains
  provider-adapter behavior.
- Qualification failure cannot bypass unresolved-route fencing.
- Coding retries preserve one logical route while deriving one runtime identity
  per Attempt.
- No Net, lifecycle, Motus, scheduler, provider-storage, or Petrus behavior
  changed.
