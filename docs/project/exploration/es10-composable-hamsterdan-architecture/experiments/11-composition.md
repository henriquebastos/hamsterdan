# Experiment 11 — Whole-Hamsterdan composition

Session S11 started from local `main` and `origin/main` at
`5a99349c9945695483db2b438c8479ddb0525914`, which records accepted S9 and the
five accepted or corrected Experiment 10 local simulations. The session inputs
were the ES-010 index, the full accepted S9 runtime record, and the full
workflow, readiness, GitHub, agents, and host Experiment 10 records. R1, R2,
and R3 remained fixed. the engineering style contract was not treated as an S11 prerequisite.

The approved checkpoint was to inventory and mount the five accepted local
interfaces under S9's unchanged `Timeline`; test the composition first; route
namespaced commands without local simulation imports; exercise recorded
interleavings, crash/reconstruction, and replay; compose local checkers; add
only cross-module properties; localize one failure; compare one retained CV18
scenario semantically; and report correspondence limits. The target workflow,
ports/adapters, readiness, host, bounded-step model, `Timeline`,
`CoroutineStepper`, process-local frames, durable scheduling/recovery
authority, and accepted local-simulation rulings were not reopened.

## Verdict: partial negative result

The experiment proves deterministic **co-mounting**, not the required causal
whole-Hamsterdan semantic composition.

All five unchanged accepted modules mount under one S9 clock, scheduler,
generation, resource budget, journal, and artifact. Their eligible work
interleaves, their local checkers compose, the mounted process crashes and
reconstructs, an independently constructed readiness mutation settles one
response-lost Git effect lookup-first, every retained artifact replays exactly,
and a workflow-local failure reduces to the workflow simulation.

The required minimum vertical and S11 exit remain unmet. The blocking mismatch
is exact:

> Accepted workflow exposes only `RerunReq -> RerunLanded`; accepted readiness
> requires workflow-declared `MutWork`; composition cannot create or reinterpret
> typed workflow meaning.

In the retained mechanics, workflow exposes pending operation
`rerun:tests-red:7:1`. The composition owner copies that operation into handoff
metadata, but independently invents instruction `rename the config key`,
constructs `MutWork` and an agents coding request under the different operation
`push:comment:501:<head>:i3`, and later gives that mutation to readiness. The
agent does not execute workflow's requested Activity, and workflow never
declares the mutation. Recording `RerunLanded` does not bridge those two typed
meanings.

The actual evidence therefore has two parallel branches, not a causal
workflow-to-agent arrow:

```text
                         ┌─ workflow branch ──────────────────────┐
composition.signed_webhook                                      │
   composition-owned     │  RerunReq(rerun:tests-red:7:1)        │
   macro/projector       │               │                       │
         │               │               ▼                       │
         │               │           RerunLanded                 │
         │               └───────────────────────────────────────┘
         │
         └─ composition-owned mutation branch
              invent "rename the config key"
                         │
                         ▼
              MutWork + coding request
              push:comment:501:<head>:i3
                         │
                         ▼
                    agents delivery
                         │
                         ▼
                 readiness mutation
                         │
                 Git effect accepted
                 response lost
                         │
                 Timeline crash
                         │
              reconstruct all modules
                         │
                 lookup-first Pushed
```

This counterexample withdraws the earlier minimum-vertical,
semantic-composition, and exit-met claims.

## Co-mounting candidate and ownership

The partial candidate lives in
[`spikes/11-composition/composition.py`](spikes/11-composition/composition.py),
its executable contracts in
[`spikes/11-composition/test_composition.py`](spikes/11-composition/test_composition.py),
and its retained evidence runner in
[`spikes/11-composition/evidence.py`](spikes/11-composition/evidence.py).

One `Timeline` mounts these structural modules in order:

```text
composition, workflow, readiness, github, agents, host
```

The five local modules are the unchanged Experiment 10 implementations. An AST
contract proves that none imports another local simulation implementation; only
the S11 composition spike imports all five.

Commands, observations, and faults require a declared namespace, and unknown
namespaces fail before delegation. This is strict namespaced dispatch, with one
important qualification: `composition.signed_webhook` is a composition-owned
macro/projector. It verifies an experimental HMAC over a detached body and
expands that ingress into recorded local commands. It is not a host command,
not generic pass-through routing, and not evidence that production host exposes
this simulation interface. Naming it `composition.signed_webhook` makes its
actual ownership explicit.

The composition owner also retains synthetic handoff metadata. Exact retries
are idempotent, including after readiness enriches a retained record; a changed
value under the same operation is rejected. This proves the co-mounting
mechanics, not that composition is authorized to manufacture typed workflow
meaning.

## Resource-budget union and interleaving

S9 accepts exactly the union of every mounted resource key. A test removes one
key and proves `Timeline.open` rejects the incomplete budget. The counterexample
peaks were:

| Owner | Gauge | Limit | Peak |
|---|---|---:|---:|
| composition | `webhooks` | 8 | 1 |
| composition | `handoffs` | 8 | 1 |
| workflow | `commands` | 8 | 3 |
| workflow | `history_records` | 128 | 61 |
| workflow | `pending_activities` | 1 | 1 |
| readiness | `calls` | 32 | 7 |
| readiness | `claims` | 8 | 1 |
| readiness | `publications` | 8 | 1 |
| readiness | `requests` | 8 | 1 |
| readiness | `terminals` | 8 | 1 |
| GitHub | `authorities` | 16 | 1 |
| GitHub | `calls` | 128 | 4 |
| GitHub | `effects` | 32 | 0 |
| GitHub | `pending` | 32 | 1 |
| GitHub | `reads` | 32 | 2 |
| GitHub | `retained_bytes` | 262,144 | 1,392 |
| agents | `operations` | 16 | 1 |
| agents | `pending` | 16 | 1 |
| agents | `receiver_terminals` | 16 | 1 |
| agents | `runtime_terminals` | 16 | 1 |
| agents | `terminal_declarations` | 16 | 1 |
| host | `cleanup_errors` | 8 | 0 |
| host | `instances` | 8 | 1 |
| host | `loaded` | 8 | 1 |
| host | `readiness_operations` | 64 | 2 |
| host | `routes` | 8 | 1 |
| host | `runnable` | 8 | 1 |

The global experiment limits are 1,024 operations, 256 owner steps, 64
eligible actions, 256 leaf calls, 256 choice draws, 32 active faults, 8
generations, logical time 1,000 microseconds, 4,096 journal entries, and
4,000,000 artifact bytes. These are modeled ceilings, not production capacity.

Twenty-two recorded `runtime:event_order` draws select work from all five local
modules while other local work is eligible. This proves deterministic
interleaving in S9, not threads, processes, or distributed parallelism.

## Checker composition and its boundary

S11 invokes each accepted local checker at its unchanged detached boundary:

| Owner | Checker input |
|---|---|
| workflow | workflow observation over retained transcript and History-derived state |
| readiness | readiness state and provider ledger |
| GitHub | detached `github.state` observation |
| agents | expanded S9 operations and final detached agents observation |
| host | expanded S9 operations and final detached host observation |

The co-mounting checker compares composition-owned metadata with detached local
states: signed-webhook/GitHub/readiness authority, copied workflow operation,
composition-owned publication operation, agent terminal, host route custody,
and recorded delivery-before-readiness order. The authority mismatch is beyond
any one accepted local checker. With a composition-only head substitution, all
five local checkers pass while this cross-state observation reports:

```text
readiness authority differs from the signed webhook and GitHub authority
```

That observation is useful co-mounting evidence, but it does not establish a
typed workflow-to-agent-to-readiness relationship. Both sides of the supposed
relationship are correlated only to composition-owned metadata. A checker
cannot repair the missing workflow declaration by comparing those records.
Consequently this is not yet the genuinely cross-module semantic property
required for S11's exit.

## Retained evidence

All three canonical artifacts encode, decode, and replay against fresh modules
with exact operations, journal, state, findings, resource peaks, and bytes.

| Scenario | Operations | Journal | Bytes | Digest | Result |
|---|---:|---:|---:|---|---|
| co-mounting counterexample | 121 | 269 | 240,950 | `sha256:48c04363d277769d07363e93831322f8b4f3fc92dc257070fbab28e3d2776735` | five local checkers pass; no cross-state violation; one causal blocker |
| co-mounting authority mismatch | 122 | 272 | 242,696 | `sha256:06652888c10b1b2394f6df0ddec7f9378c25be5608f5a34bb8bec1e566e6744f` | five local checkers pass; one cross-state observation; same causal blocker |
| co-mounted workflow failure | 50 | 103 | 72,169 | `sha256:446b636850e17931d77939573368b53a8c094f46bf38dd688a802352350ac9af` | workflow checker fails and localizes |
| workflow-only reduction | 40 | 83 | 35,645 | `sha256:abb0cb84abeeb7870052591436b520141d0915b9c5fbef526df492e6e7e6b197` | identical workflow violation |

The 121-operation counterexample additionally records:

```text
final generation       2
crash phases           executed
interleaved modules    agents, github, host, readiness, workflow
signed webhooks        1
agent runtime starts   1
agent deliveries       1
readiness agent calls  1
accepted Git effects   1
lookup recoveries      1
workflow terminal      RerunLanded
replay                 exact after canonical encode/decode
```

The accepted effect belongs to readiness's deterministic local Git adapter;
`github.effects` correctly remains zero. After that adapter accepts the effect
and loses its response, an `executed`-phase Timeline crash discards every
mounted process-local generation, including host. Generation 2 reconstructs
every module, and readiness's retained request/provider ledger makes the same
operation eligible for lookup-first `Pushed` settlement before another effect.
These crash/recovery mechanics are valid, but they occur on the independently
constructed mutation branch.

## Localization and exit assessment

The co-mounted workflow-correlation scenario gives `RerunLanded` the wrong
operation. Exactly one local checker reports:

```text
RerunLanded terminal operation 'rerun:other:99:9' does not match requested
operation 'rerun:tests-red:7:1'
```

The unchanged workflow simulation reproduces the identical violation in the
40-operation reduced artifact. The authority observation remains replayable at
co-mounting scope because every local module is internally valid. This proves
the mechanics of local checker composition, localization, reduction, and
cross-state replay.

It does **not** meet S11's exit. Without a causally aligned typed Activity, the
authority observation is not a whole-application semantic failure and the
nominal path is not the required minimum vertical. There is therefore no
whole-Hamsterdan simulation candidate yet.

Completing S11 requires Navigator authorization for a new bounded follow-up
that either adds aligned local evidence or explicitly revises the accepted
local simulation inputs. This experiment does not choose between those changes
and does not modify the accepted evidence to manufacture a pass.

## Semantic coverage and CV18 comparison

| Area | Demonstrated | Not demonstrated |
|---|---|---|
| runtime | one S9 clock/scheduler, exact resource union, recorded choices, crash/restart, canonical exact replay | production concurrency or artifact compatibility |
| five local modules | unchanged co-mounting and all five detached checkers | plug-compatible live ports or causal module handoffs |
| ingress | composition-owned exact-body HMAC macro and fail-before-mutation verification | GitHub webhook verification, delivery custody, HTTP acknowledgement, or host-owned ingress |
| workflow | pending rerun request and correlated `RerunLanded` | workflow-declared `MutWork` or agent execution of the workflow Activity |
| agents/readiness | independently constructed production-shaped coding request; one accepted/lost/recovered local Git effect | causation from workflow; Pi execution; accepted agents/GitHub modules as readiness's live adapters |
| host/GitHub | route custody, wakes, authority, reads, reconstruction, local checks | production host composition or one shared provider implementation |
| checkers | local composition, localization, one composition-owned authority observation | the required causal cross-module semantic property |

The retained current comparator is
`test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash`
(`hamsterdan-v5-git-ambiguity-restart-v1`). The overlap is limited to mechanics:
stable publication identity, one accepted response-lost Git publication,
crash/restart, lookup-first recovery, and one-effect cardinality. CV18 has the
stronger causal path through the real readiness world, including recovery
authorization and final readiness/Git custody semantics. S11 reproduces similar
mutation mechanics only on its independent composition-owned branch.

No semantic equivalence, field compatibility, operation-count compatibility,
artifact compatibility, profile compatibility, checker identity, byte count,
or digest compatibility is asserted.

## Production correspondence limits

1. Production `host` remains the only runtime composition root. The S11
   composition owner is an experimental macro/router, not a proposed live
   owner.
2. Readiness and host retain their accepted local strict adapters. Readiness
   does not call the accepted agents or GitHub simulation, and host does not
   open the accepted readiness simulation.
3. The signed webhook is synthetic and composition-owned. It is not GitHub
   signature, installation, delivery-custody, HTTP, or acknowledgement evidence.
4. The coding request is production-shaped but no workspace, Pi subprocess,
   provider protocol, model output, secret, or cleanup behavior executes.
5. The Git effect is deterministic. The spike does not prove GitHub consistency,
   pagination, rate limits, CAS transport, or network interruption.
6. Generation loss is in-process. Stores survive while generation objects and
   suspended owner frames are discarded; no OS kill, filesystem, SQLite,
   transaction interruption, or restart discovery is exercised.
7. Recorded interleaving and resource gauges model experiment behavior, not
   thread scheduling, multiprocess races, production rows, memory, handles,
   subprocesses, or latency.
8. S9 canonical replay proves only this candidate's artifact family. It does
   not establish compatibility with CV18, Petrus, earlier experiments, or
   future Delivery artifacts.
9. Most importantly, typed semantic causality is absent. Shared strings and
   composition-owned metadata cannot substitute for a workflow-declared
   mutation executed by agents and admitted by readiness.

## TDD, correction, and verification

The contracts were written before `composition.py`; the first red run failed
during import because the implementation did not exist. The initial
implementation then exposed missing production-required validation evidence,
which was supplied without weakening the validator. A later red retry contract
found that readiness enrichment made an exact handoff retry look conflicting;
the fix compares immutable fields while retaining conflict rejection.

Pre-acceptance review found the semantic blocker documented above. A new
focused contract first failed because `CAUSAL_VERTICAL_BLOCKER` did not exist.
The correction exports that blocker, inspects artifact commands to prove the
workflow and mutation operations are different, renames the harness and
scenarios as co-mounting evidence, reports a causal blocker on relevant
artifacts, removes the false workflow-to-agent claim, and renames synthetic
ingress from `host.signed_webhook` to `composition.signed_webhook`.

Focused checks after the correction:

```text
uv run --frozen pytest -q <S11 test_composition.py>
7 passed in 1.44s

uv run --frozen ruff format --check <S11 spike directory>
3 files already formatted

uv run --frozen ruff check <S11 spike directory>
All checks passed!

uv run --frozen ty check <S11 sibling search paths> <S11 spike directory>
All checks passed!

uv run --frozen python <S11 evidence.py>
three canonical artifacts and one local reduction emitted; every replay exact
```

Retained comparator and repository gates after the correction:

```text
uv run --frozen pytest -q \
  tests/integration/testing/test_readiness_world.py::test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash
1 passed in 9.56s

scripts/check quick
10 passed in 2.09s

scripts/check full
10 quick tests passed
9 relay tests passed
44 demo/live tests passed
source distribution and wheel built
1165 Python tests passed in 92.05s
```

Normal disk-backed temporary storage was used. No `TMPDIR=/dev/shm`
workaround, timeout change, skipped test, or weakened assertion was needed.

Before acceptance, the spike changed only these paths:

```text
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/11-composition.md
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/11-composition/composition.py
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/11-composition/evidence.py
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/11-composition/test_composition.py
```

No production source, maintained test, configuration, roadmap, decision, debt,
worklog, S9, Experiment 10, Experiment 12, or R4 surface changed. The Navigator
accepted this partial negative result and the recommendation to make no
pre-integration refactor or debt record. Acceptance did not complete S11 or
authorize the bounded follow-up. The ES-010 Current state now records the
blocker; S11 remains blocked and R4 remains unruled.
