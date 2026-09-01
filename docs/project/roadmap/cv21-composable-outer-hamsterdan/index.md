---
code: CV21
level: Value
status: Active
status_reason: the alpha decision keeps CV21 as the quality track without production pressure; DS2 tasks 1–5 are delivered and await Navigator Experience Report acceptance and closure
updated: 2026-09-01
related:
  - ../../decisions/records/2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
  - ../../decisions/records/2026-08-28T2037Z-cv21-activities-run-in-separately-supervised-motus-workers.md
  - ../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
  - ../../decisions/records/2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
  - ../cv20-composable-reconstructible-hamsterdan/index.md
  - ../cv22-decomposable-readiness-workflow/index.md
  - architecture.md
  - workflow-bridge.md
  - contract-inheritance.md
  - delivery-sequence.md
---

# CV21 — Composable outer Hamsterdan over the retained workflow

## Intent

Rebuild everything around the PR-readiness Petri Net under clear ownership and
Hamsterdan-owned deterministic simulation while retaining the current working
V5 Net behind one temporary bridge. This isolates outer-system design from
workflow redesign and makes the new source tree reviewable without changing the
only operational runtime.

## Value

The new GitHub, agent, readiness, host, operator, custody, authority, effect,
recovery, discovery, fairness, observability, and simulation owners compose
through explicit typed capabilities. Their complete behavior can be exercised
and exactly replayed against the real retained Net without importing or reusing
the current application around that Net.

## Resulting construction state

```text
current src/hamsterdan ─────────────── sole operational runtime

src/hamsterdan2
  new outer system
    -> final typed workflow boundary
    -> one temporary legacy-workflow bridge
    -> current build_net_v5()/seed/gates

current runtime state ─────────────── current application only
fresh disposable CV21 state ───────── non-selectable construction only
```

CV21 does not create a topology selector, deployment option, compatibility
reader, state migration, dual writer, or second operational service. Its bridge
is internal construction scaffolding removed by CV22.

## Canonical implementation contract

CV21 is self-contained for implementation and review. Read these owners in
order:

1. [Architecture](architecture.md) — package ownership, dependency direction,
   runtime shape, durable cuts, simulation, and construction boundaries.
2. [Workflow bridge](workflow-bridge.md) — sole legacy import allowlist,
   translation rules, correspondence evidence, and removal test.
3. [Contract inheritance](contract-inheritance.md) — accepted contracts and
   pending audit questions transferred from CV20 without reopening or silently
   accepting them.
4. [Delivery sequence](delivery-sequence.md) — tracer ladder, cumulative state,
   review rules, and Value-level acceptance.
5. The selected Delivery Story — its one vertical outcome, owned contract
   slice, exclusions, and evidence.

CV20 remains provenance and comparison material. An implementer does not use it
to fill an unspecified CV21 API. The selected CV21 Plan Checkpoint must rule and
record any missing concrete signature or bound in CV21 before code is written.

## Delivery graph

```text
DS1 bridged lifecycle -> DS2 ingress -> DS3 retained-Net Activity
  -> DS4 GitHub effect -> DS5 agent round -> DS6 causal mutation
  -> DS7 CI/repair effects -> DS8 timers -> DS9 authority/lifecycle
  -> DS10 unknown discovery -> DS11 multi-PR/discovery fairness
  -> DS12 outer-system and bridge qualification
```

## Delivery

1. [CV21.DS1 — Establish the first bridged PR lifecycle](cv21-ds1-first-bridged-pr-lifecycle.md)
2. [CV21.DS2 — Admit one PR observation through the bridge](cv21-ds2-admit-pr-observation-through-bridge.md)
3. [CV21.DS3 — Expose one retained-workflow Activity](cv21-ds3-expose-retained-workflow-activity.md)
4. [CV21.DS4 — Settle one GitHub Activity lookup-first](cv21-ds4-settle-github-activity.md)
5. [CV21.DS5 — Settle one reconstructible agent round](cv21-ds5-settle-agent-round.md)
6. [CV21.DS6 — Publish one causally aligned mutation](cv21-ds6-publish-causal-mutation.md)
7. [CV21.DS7 — Recover CI and repair effects](cv21-ds7-recover-ci-repair-effects.md)
8. [CV21.DS8 — Recover timers and deferred work](cv21-ds8-recover-timers-deferred-work.md)
9. [CV21.DS9 — Fence lifecycle and authority changes](cv21-ds9-fence-lifecycle-authority.md)
10. [CV21.DS10 — Discover unregistered open PRs boundedly](cv21-ds10-discover-unregistered-open-prs-boundedly.md)
11. [CV21.DS11 — Supervise multiple PRs fairly](cv21-ds11-supervise-multiple-prs-fairly.md)
12. [CV21.DS12 — Qualify the outer system and workflow bridge](cv21-ds12-qualify-outer-system-and-bridge.md)

CV21.DS1 is complete. DS2 remains `Active`; tasks 1–5 in its confirmed serial
ladder are delivered and await Navigator Experience Report acceptance and
closure. DS3 through DS12 remain `Planned`; none is pulled merely because its
predecessor's implementation completed. Each selected tracer must expand into
reviewable User and Technical Stories and pass its own API-strengthening Plan
Checkpoint before implementation.

## Done condition

CV21 is complete when:

1. all twelve outer tracers are accepted through the real host composition and
   sole bridge-mounted current Net;
2. every new owner has local deterministic execution, a checker independent of
   the implementation it judges, named crash/reconstruction cuts, exact replay,
   finite resource evidence, and applicable real-seam correspondence;
3. architecture evidence proves that only the bridge imports the allowlisted
   current workflow entry points and that no old type escapes it;
4. the bridge translation census covers every observation, Activity work,
   terminal, timer command, occurrence, and detached posture used by the
   retained workflow;
5. the new outer system uses only fresh disposable state and remains absent from
   runtime configuration, deployment, and operator selection; and
6. CV22 can replace one bridge-supplied workflow factory without changing any
   outer-system import or capability contract.

## Boundaries

- CV21 does not implement or simplify a workflow loop, subnet, fold, topology,
  gate decision, lifecycle decision, or dashboard projection.
- The retained Net's behavior is accepted runtime evidence, not permission to
  reuse the current host or effect implementations.
- The bridge may translate representations but may not compensate for or
  improve current workflow behavior.
- CV21 does not cut over, rename packages, delete V5, or alter current state.
- CV19 is the resumed alpha delivery focus and still requires separate launch
  approval. The current V5 application remains the only runtime while CV21
  construction stays non-selectable.
- Provider mutations, deployment, state actions, commit, push, and release keep
  their separate explicit approval boundaries.
