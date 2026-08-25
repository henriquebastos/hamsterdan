# Experiment 1 — Current ownership and deletion map

Session S1. Inputs: the ES-010 index and current `src/hamsterdan` source at
commit `01c8f11`. Method: the AST import-graph tool at
[`tools/import_graph.py`](tools/import_graph.py) (same relative-import-aware
mechanism as `tests/test_architecture.py`) plus a full classification read of
all 61 source modules. File sizes are recorded only as navigation signals.

Classification vocabulary is the ES-010 working language: **workflow** (pure
readiness definition), **readiness execution** (one PR's effectful workflow
run), **host supervision** (trusted process-wide concerns), **provider
adapter** (GitHub/agent effect implementation), plus **operator support** and
**simulation-test support** categories.

## Import graph

61 modules. The top-level DAG is clean; exactly one strongly connected
component exists:

```text
hamsterdan.readiness.net_v5 <-> hamsterdan.readiness.net_v5.topology
```

Mechanism: `net_v5/__init__.py:3` imports `topology` to re-export
`build_net_v5`/`seed_marking`, while `topology.py:28` imports the nine loop
modules through the still-initializing package object. The cycle is a facade
artifact, not a semantic dependency; `topology.py` never reads a name back from
the package initializer.

Fan-in concentrates in the value vocabulary and provider models; fan-out
concentrates in composition cones:

| Fan-in | Module | | Fan-out | Module |
|---:|---|---|---:|---|
| 20 | `contracts.readiness_v5` | | 19 | `host.v5.application` |
| 15 | `github_app.models` | | 15 | `host.service` |
| 9 | `readiness.net_v5.folding` | | 10 | `readiness.net_v5.topology` |
| 8 | `contracts.readiness` | | 9 | `host.testing.readiness_world` |
| 7 | `host.v5.claim` | | 8 | `host.v5.runtime` |

Regenerate the full edge list with the tool; it is deterministic from source.

## Module ledger

Role: interface / implementation / pass-through / mixed-owner. Verdict:
earns-its-depth (E) / pass-through (P) / residue (R). Category: production /
operator / simulation-test / residue.

### Workflow definition (currently `readiness/net_v5` + `contracts`)

| Module | Lines | Role | Verdict | Category | Owner today |
|---|---:|---|---|---|---|
| `net_v5/ci.py` | 220 | implementation | E | production | pure workflow: CI loop, `CiState` |
| `net_v5/conversation.py` | 310 | implementation | E | production | pure workflow: conversation loop, `ConvMemory` |
| `net_v5/dashboard.py` | 300 | implementation | E | production | pure workflow: dashboard loop, `DashMemory` |
| `net_v5/esc.py` | 462 | implementation | E | production | pure workflow: escalation ladder |
| `net_v5/life.py` | 410 | implementation | E | production | pure workflow: lifecycle admission hub |
| `net_v5/mutation.py` | 420 | implementation | E | production | pure workflow: mutation custody, `MutState` |
| `net_v5/readiness.py` | 833 | implementation | E | production | pure workflow: readiness projection, `Snapshot` |
| `net_v5/reminders.py` | 413 | implementation | E | production | pure workflow: reminder/timer protocol |
| `net_v5/review.py` | 614 | implementation | E | production | pure workflow: review rounds, `ReviewMemory` |
| `net_v5/topology.py` | 76 | implementation | E | production | pure workflow: Net composition, `GATES`, seeds |
| `net_v5/folding.py` | 49 | implementation | E | production | pure workflow: token hydration (fan-in 9) |
| `net_v5/gating.py` | 291 | **mixed-owner** | E | production | workflow gate names + Motus Activity execution wiring |
| `net_v5/__init__.py` | 5 | pass-through | P | production | re-export facade; source of the only cycle |
| `contracts/readiness_v5.py` | 1456 | interface | E | production | complete workflow value vocabulary (fan-in 20) |
| `contracts/readiness.py` | 797 | **mixed-owner** | R | **residue** | retired pre-V5 model; 4 live names (see below) |
| `readiness/payloads.py` | 28 | implementation | E | **simulation-test** | Motus payload converter; no production importer |
| `readiness/__init__.py`, `contracts/__init__.py` | 1+1 | pass-through | R | residue | docstring-only markers |

Purity result: the nine loop modules, `folding`, and `topology` import only
Petrus Petri-definition APIs and `contracts.readiness_v5`. They are already
extractable as pure workflow. `gating.py` straddles: it declares workflow gate
vocabulary but imports Motus execution handlers, `ActivityInvocation`, retry
policy, and `wire_gates()` binding (`gating.py:27,31-39,143-150,267-291`) —
that half belongs to readiness execution.

`contracts/readiness_v5.py` internal groups (approximate lines): aliases 19–39,
host-normalized observations 40–122, loop-private memory 123–264, loop-to-loop
facts 265–435, specialized readiness facts 436–603, Activity work/results per
concern 604–1456. This grouping is the direct input to experiment 2.

`contracts/readiness.py` live surface, verified by search: `WorkflowModel`
(base for all `readiness_v5` values; `folding.py:15`, `ingress.py:17`),
`AdmittedConversation` (`webhooks.py:18`, `protocol.py:10`, `service.py:20`,
`application.py:15`), `ChangeResult`+`RepairResult`
(`publication_qualification.py:14` only). Roughly 50–60 of 797 lines are live;
~93% is retired residue with production fan-in 8 through those four names.

### Readiness execution (currently `host/v5` + parts of `host`)

| Module | Lines | Role | Verdict | Category | Owner today |
|---|---:|---|---|---|---|
| `host/v5/application.py` | 531 | **mixed-owner** | E | production | one-PR composition root; also constructs concrete provider adapters (`L104-141`) |
| `host/v5/runtime.py` | 616 | **mixed-owner** | E | production | Petrus adaptation, History recovery, dispatch, timer/wake projection |
| `host/v5/ingress.py` | 912 | **mixed-owner** | E | production | provider normalization + durable manifest/grant custody + process inbox inspection (`L495-558`) |
| `host/v5/timers.py` | 927 | implementation | E | production | restart-safe per-PR timer ledger, History rebuild |
| `host/v5/claim.py` | 32 | interface | E | production | current-authority value + `ClaimReader` port (fan-in 7) |
| `host/v5/gates.py` | 442 | provider adapter | E | production | five comment-publication Activities, lookup-first + fencing |
| `host/v5/rerun.py` | 171 | provider adapter | E | production | same-head rerun Activity |
| `host/v5/mutation.py` | 283 | provider adapter | E | production | coding + exact-CAS Git mutation Activity |
| `host/v5/review.py` | 361 | **mixed-owner** | E | production | review-request SQLite custody + agent invocation + custody deferral |
| `host/binding.py` | 207 | implementation | E | production | durable state-root ↔ PR/topology anti-aliasing |
| `host/protocol.py` | 43 | interface | E | production | host↔one-PR control seam; leaks `github_app` types (`Observation`, `AdmittedConversation`, `L10-24`) |
| `host/git_publish.py` | 460 | provider adapter | E | production | App-authored Git objects, exact ref CAS, lookup-first |
| `host/v5/__init__.py` | 1 | pass-through | R | residue | docstring only |

The four Activity adapters (`gates`, `rerun`, `mutation`, `review`) plus
`git_publish` are the concrete shape of the future `readiness/effects`: each
already couples one typed workflow Activity to a provider seam with operation
identity, authority fencing, and lookup-first recovery.

### Host supervision (currently rest of `host`)

| Module | Lines | Role | Verdict | Category | Owner today |
|---|---:|---|---|---|---|
| `host/service.py` | 845 | **mixed-owner** | E | production | process supervision + hidden one-PR readiness policy (see below) |
| `host/__main__.py` | 267 | mixed-owner | E | production | CLI composition + operator inspection commands (`L104-188`) |
| `host/api.py` | 52 | interface | E | production | FastAPI boundary over `HostService` |
| `host/runnable.py` | 165 | implementation | E | production | disposable wake-hint scheduler index (pure host supervision) |
| `host/agenticus.py` | 481 | **mixed-owner** | E | production | agent-route custody; parses per-PR Histories and knows `mut.git_gate`/`review.agent` result policy (`L396-463`) |
| `host/pi_a2.py` | 421 | implementation | E | production | Pi installation, credential custody, runtime factory |
| `host/pi_workspace.py` | 357 | provider adapter | E | production | exact-checkout workspace + archive-to-patch |
| `host/publication_qualification.py` | 532 | implementation | E | **operator** | qualification evidence; only src importer is `operator.py` |
| `operator.py` | 1269 | implementation | E | **operator** | human JSON CLI; no production importer |
| `host/__init__.py` | 6 | pass-through | P | production | two re-exports |
| `hamsterdan/__init__.py` | 3 | interface | E | production | explicit empty-root policy |

Hidden one-PR readiness policy inside `HostService`, verified in source:
`pump()` orders all due authority custody before publication claiming and
refuses to claim a PR publication while that PR has pending inbox custody
(`service.py:508-530`); `_activate_instance` settles an Activity/timer
terminal before optional provider reconciliation and reconciles only without
pending custody on an active route (`service.py:689-731`). These are one-PR
execution-order decisions living in the process supervisor — direct input to
experiments 5 and 6.

### Provider packages (`github_app`, `agents`)

| Module | Lines | Role | Verdict | Category | Owner today |
|---|---:|---|---|---|---|
| `github_app/auth.py` | 278 | mixed-owner | E | production | GitHubKit client custody + normalized inventory; SDK `GitHub` crosses only intra-package seams |
| `github_app/config.py` | 245 | implementation | E | production | strict config + credential custody, redacted repr |
| `github_app/transport.py` | 287 | implementation | E | production | GitHubKit/httpx wrapped into `WireResponse` and bounded operations |
| `github_app/gateway.py` | 472 | implementation | E | production | normalized reads, Git-object writes, secret-safe failures |
| `github_app/effects.py` | 538 | implementation | E | production | lookup-first fenced publications and rerun brokerage |
| `github_app/webhooks.py` | 416 | **mixed-owner** | E | production | provider ingress + durable webhook custody + secret custody (`L136-146`) |
| `github_app/routing.py` | 192 | implementation | E | production | durable installation/repository route registry |
| `github_app/models.py` | 146 | interface | E | production | frozen normalized provider values (fan-in 15); no SDK shapes |
| `github_app/__init__.py` | 1 | pass-through | R | residue | docstring only |
| `agents/protocol.py` | 547 | interface | E | production | credential-free typed agent contracts |
| `agents/pi.py` | 574 | implementation | E | production | Pi A2 adaptation; Petrus runtime types cross the agents→host composition seam |
| `agents/__init__.py` | 39 | pass-through | P | production | pure re-export facade (fan-in 5); consumers split between facade and submodule imports |

Boundary findings: no GitHubKit/HTTP type escapes `github_app`'s public
surface toward host or readiness; `models.py` values are normalized and frozen
but GitHub-semantic, not neutral cross-provider facts. Credentials appear only
in `config`/`auth`/`pi_a2` custody plus `webhooks._secret` (webhook custody is
itself a trusted-host concern living in a provider package — a seam question
for experiment 6).

### Shipped test support

| Module | Lines | Role | Verdict | Category | Owner today |
|---|---:|---|---|---|---|
| `testing/readiness.py` | 498 | implementation | E | simulation-test | independent expected-readiness model; zero production imports |
| `host/testing/_readiness_contract.py` | 242 | interface | E | simulation-test | strict command/fault vocabulary, profile identity, budgets |
| `host/testing/_readiness_provider.py` | 827 | implementation | E | simulation-test | deterministic GitHub/agent/Git models behind production-shaped ports |
| `host/testing/readiness_world.py` | 1715 | **mixed-owner** | E | simulation-test | real host+readiness under deterministic control; checkers know History records and SQLite schemas (`L1481-1697`) |
| `host/testing/readiness_coverage.py` | 839 | implementation | E | simulation-test | artifact-based semantic coverage accounting |
| `testing/__init__.py`, `host/testing/__init__.py` | 1+1 | pass-through | R | residue | docstring only |

`readiness_world` confirms the ES-010 evidence claims: its checkers read
canonical History record names and Activity payloads (`L528-564`, `L899-938`,
`L1481-1565`) and exact SQLite schemas (`v5_timer_operations`, dispatch tables,
`L1568-1697`); and three timeline operations drain multiple internal steps in
one call (`advance_time` `L1387-1392`, `run_until` `L1400-1406`, `converge`'s
`while world.pending(): world.step()` `L1414-1429`) — the coarse-step evidence
behind experiment 7.

## Observed mixed owners (summary)

1. `host/v5/application.py` — one-PR readiness composition that also
   constructs concrete GitHub/agent/Git adapters.
2. `host/v5/ingress.py` — provider normalization, durable custody, and
   process-wide inbox inspection in one module.
3. `host/service.py` — process supervision embedding one-PR execution-order
   policy (`pump`, `_activate_instance`).
4. `host/protocol.py` — topology-neutral control seam leaking provider types.
5. `net_v5/gating.py` — workflow gate vocabulary fused with Motus execution
   wiring.
6. `github_app/webhooks.py` — provider ingress fused with trusted webhook and
   secret custody.
7. `host/agenticus.py` — host route custody that parses per-PR workflow
   Histories and encodes Activity-variant settlement policy.
8. `host/__main__.py` — process composition fused with operator inspection
   commands.
9. `host/testing/readiness_world.py` — simulation runtime, command adapter,
   projections, checkers, and storage introspection in one module.

## Deletion-test outliers

- `contracts/readiness.py`: ~93% retired residue held live by four names;
  `WorkflowModel` and `AdmittedConversation` are the genuinely neutral
  survivors, `ChangeResult`/`RepairResult` are operator-support-only.
- Docstring-only initializers (`host/v5`, `github_app`, `testing`,
  `host/testing`, `readiness`, `contracts`): no owned meaning.
- `readiness/payloads.py`: earns its depth as a converter but has no
  production importer; its category is test support, not production.
- Re-export facades (`net_v5/__init__` — also the only cycle,
  `agents/__init__`, `host/__init__`): pass-throughs whose value is import
  ergonomics only.
- Everything else classified earns its depth where it stands; no module was
  found whose deletion would lose nothing.

## Path traces by owner

Written in the ES-010 ownership language; current module names in parentheses.

**Clean-green: CI success on the exact head → readiness published.**
Provider ingress verifies and durably custodies the delivery
(`github_app.webhooks`); host supervision routes it to the owning PR instance
(`host.service`); readiness execution freezes the ingress manifest and
authority grant, normalizing fresh GitHub truth into a typed run observation
(`host.v5.application` + `host.v5.ingress`); readiness execution folds it into
canonical History through the Petrus adaptation (`host.v5.runtime`); the
workflow decides all gates pass and requests a typed announce Activity
(`net_v5.readiness` and siblings); a readiness effect adapter fences current
authority, recovers lookup-first, and publishes (`host.v5.gates` over
`github_app.effects`); readiness execution folds the typed landed terminal
back into History (`host.v5.runtime`).

**Mutation recovery: Git effect accepted, response lost → lookup-first
settlement.** The workflow classifies the authorized instruction and issues
mutation work with stable operation identity (`net_v5.conversation`,
`net_v5.mutation`); readiness execution dispatches it to the bound effect
adapter (`host.v5.runtime`, `host.v5.application`); the adapter derives the
same operation, ref, and digest on every attempt and reconciles lookup-first
before any authority read or agent call (`host.v5.mutation`); the original
attempt's provider effect landed but the response was lost, so the workflow's
fault-recovery path reissues the same operation (`net_v5.mutation`); the
retry's reconciliation finds the existing effect and returns the pushed
terminal without re-running the agent (`host.v5.mutation` over
`host.git_publish`); readiness execution folds the terminal and settles the
route (`host.v5.runtime`).

## Exit assessment

Both required paths are explainable by owner without V5 package names. The
mixed-owner list gives experiments 2–6 their concrete targets: the workflow
loops are already pure and extractable; the readiness-execution seam runs
through `host/v5` plus `gating.py`'s execution half; host supervision must
shed the one-PR policy in `service.py` and the History knowledge in
`agenticus.py`; and `contracts` reduces to at most `WorkflowModel` and
`AdmittedConversation` pending experiment 2's neutrality test.
