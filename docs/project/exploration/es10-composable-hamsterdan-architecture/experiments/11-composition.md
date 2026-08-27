# Experiment 11 — Whole-Hamsterdan composition

Session S11 originally started from `5a99349c9945695483db2b438c8479ddb0525914`
and produced an accepted partial negative result. The bounded causal-alignment
follow-up started from clean local `main` and `origin/main` at
`8178b0b5446ad723d28ea5c4fbf5dc569a9877f4`, which records that result and its
blocker. Inputs were the ES-010 index, the accepted S9 runtime record, all five
accepted Experiment 10 records and relevant spike interfaces, and the
Navigator-approved follow-up checkpoint. R1, R2, and R3 remained fixed; R4
remains unruled; Experiment 12 did not start; the engineering style contract was not a prerequisite.

The exact accepted blocker was:

> Workflow exposed only `RerunReq -> RerunLanded`, while readiness required a
> workflow-declared `MutWork`. Composition copied a rerun operation into
> metadata but invented mutation meaning independently. Agents delivered one
> result while readiness generated a second equivalent result. That was
> deterministic co-mounting, not causal semantic composition.

The follow-up was allowed to correct only the workflow, agents, and readiness
Experiment 10 evidence plus the S11 composition spike and records. Production,
maintained tests, S3, S9, other Experiment 10 modules, configuration, project
controls, the ES-010 index, and R4/S12 remained out of scope.

## Follow-up verdict — causal candidate, pending acceptance

The bounded blocker is corrected within the approved experiment-only scope.
One mutation declared by the real production `build_net_v5()` workflow flows
unchanged through agents and readiness. Readiness's injected coding dependency
returns the exact `CodingResult` retained and delivered by agents; its Git
publication digest and result head depend on that value. One publication is
accepted, its response is lost, the mounted process crashes at S9 phase
`executed`, generation 2 reconstructs, readiness reconciles first without a
second agent call or effect, and exact `Pushed` returns to the original workflow
Activity occurrence. The real production fold reaches mutation `idle` and
records the published head as the lifecycle's expected head.

All five local checkers pass, the one causal cross-module checker passes, there
are no causal blockers, and the canonical artifact replays exactly. An A/B
contract changes only one valid delivered-result field; the workflow work,
coding request, and mutation payload digest remain equal while publication
coding-result digest and result head change. This establishes the missing data
dependency rather than value correspondence alone. A separate full-flow
sensitivity substitutes only the handoff instruction; all local checkers still
pass, while the cross checker compares that handoff with the real workflow
History request and rejects the substitution.

This is still an experimental candidate. It does not promote production,
complete ES-010, rule R4, or authorize Experiment 12. Navigator acceptance of
the Experience Report remains separate.

## Smallest corrections to accepted local evidence

### Workflow: execute the real V5 Net

`V5MutationWorkflowSimulation` was added beside the unchanged S3
`WorkflowSimulation`. It mounts the current production:

```text
hamsterdan.readiness.net_v5.topology.build_net_v5()
seed_marking()
GATES / DERIVED / wire_gates()
```

under real Petrus `Engine`, `InMemoryHistoryStore`, and `InMemoryDispatch`.
Every V5 Activity has a declaration-only typed stub; no stub executes, and
unrelated Activities remain held. The spike does not copy `_classify`,
`MutationRequest`, `_start`, or any workflow fold.
The real production conversation-to-mutation path receives `HeadSeen` followed
by authorized `CommentSeen(kind="change", id="501")` and declares:

```text
MutWork(
  op="change",
  op_key="push:comment:501:<head>:i1",
  head=<head>,
  base=<base>,
  policy="policy-1",
  incarnation=1,
  lineage="",
  kind="change",
  instruction="rename the config key",
  run_id=0,
  attempt=0,
)
```

At the request cut, `dash_gate`, `git_gate`, and `reply_gate` are held. The
simulation exposes only the real `git_gate` occurrence, correlation,
idempotency, and decoded `MutWork`; unrelated Activities do not execute. A
durable request projection derives those values directly from the production
`ActivityRequested` History record and remains available after terminal fold.
It is independent of composition handoffs, readiness requests, and the
process-local Dispatch pending map.

### Agents: expose the exact delivered typed terminal

`AgentsSimulation.delivered(operation, attempt)` returns a frozen
`DeliveredExecution` only after receiver state is `delivered`. It contains the
exact repository URL, logical operation, attempt, production request, and
production result. It reads the retained receiver terminal, revalidates the
result against the retained request, rejects failure/cancellation and
pre-delivery access, and deep-copies mutable values. It does not derive a result
from summary metadata or share mutable custody.

### Readiness: inject one coding-only dependency

`ReadinessModule` now accepts an optional typed `CodingRunner`. The existing
`DeterministicCodingAgent` remains the default, so all standalone behavior is
unchanged. `RecordedCodingAgent` records the same `agent` ledger event at the
actual runner invocation for either path. S11 supplies the injected dependency;
readiness no longer constructs a second deterministic result on that path.

The deterministic Git adapter records a canonical digest of the exact runner
result and includes it in result-head derivation:

```text
coding_result_digest = payload_digest({
  "schema_version": 1,
  "coding_result": asdict(result),
})

result_head = sha256(
  expected_head + operation + mutation_payload_digest + coding_result_digest
)
```

`MutWork` does not carry `CodingResult`; workflow meaning and agent output stay
separate typed values at their existing boundaries.

## Composition-owned typed flow

Only S11 imports all local simulations. The local spikes still do not import
one another. The composition owner routes typed values and owns the concrete
adapter, but does not construct, reinterpret, or substitute workflow meaning:

```text
workflow = V5MutationWorkflowSimulation(build_net_v5)
agents = AgentsSimulation()
runner = DeliveredAgentsCodingRunner(agents)
readiness = ReadinessModule(runner=runner)

pending = workflow.pending_git_gate
work = pending.work                         # exact workflow MutWork
occurrence = pending.occurrence

request = V5MutationGate.request("owner/repo", 7, work)
agent_operation = f"mutation:owner/repo:pr:7:{work.op_key}"

agents.submit(
  operation=agent_operation,
  attempt=1,
  request=request,
)
agents.declare_terminal(valid_coding_result)
agents.run_and_deliver()

readiness.request_mutation(work)            # same typed value, no rewrite

DeliveredAgentsCodingRunner.code(
  repository_url,
  readiness_request,
  operation=agent_operation,
  attempt=1,
  is_current,
):
  require is_current()
  delivered = agents.delivered(agent_operation, 1)
  require delivered.repository_url == repository_url
  require delivered.operation == agent_operation
  require delivered.attempt == 1
  require delivered.request == readiness_request
  require isinstance(delivered.result, CodingResult)
  return delivered.result                  # exact retained/delivered value

pushed = readiness.lookup_first_settlement()
workflow.complete_mutation(
  occurrence=occurrence,
  value=pushed,
)
```

The stable workflow and publication identity is
`push:comment:501:<head>:i1`. Agent execution adds its existing namespace but
does not replace that identity. The readiness terminal's operation and payload
close the original workflow occurrence; no composition-selected rerun or
independent workflow settlement remains.

## Checker ownership

The accepted local checkers retain their original boundaries:

| Owner | Property retained locally |
|---|---|
| workflow | at most one real `git_gate` request; correlation and idempotency equal its decoded `MutWork.op_key`; terminal preserves request correlation |
| agents | stable execution lifecycle, effect counts, retained terminal lookup, one accepted delivery |
| readiness | one physical Git acceptance, requested authority/parents, lookup-first recovery, terminal/result-head correlation |
| GitHub | detached authority/read/effect consistency for the co-mounted GitHub simulation |
| host | route, wake, reconstruction, and artifact consistency for the co-mounted host simulation |

One property is genuinely cross-module and belongs to S11:

1. composition's handoff occurrence and exact work equal the durable real
   workflow `ActivityRequested` projection, including correlation and
   idempotency;
2. readiness receives that unchanged workflow-declared `MutWork`;
3. agents receives the canonical `V5MutationGate.request(work)`;
4. agents reaches accepted delivery before readiness admission;
5. the accepted publication's `coding_result_digest` equals the canonical
   digest of that delivered agents `CodingResult`; and
6. readiness's `Pushed` closes the original workflow occurrence and operation.

A separate composition-only authority substitution leaves all five local
checkers passing and produces exactly:

```text
readiness authority differs from the signed webhook and GitHub authority
```

That retained sensitivity belongs at composition scope. The previous copied-
operation checks and causal-blocker marker are removed because they no longer
describe the candidate.

A second composition-only sensitivity copies the real workflow request but
changes only `MutWork.instruction` from `rename the config key` to
`composition substituted this instruction`. The complete agents, response-loss,
lookup-first recovery, and workflow settlement path still completes. Every
local checker passes because each local value is internally valid, but the
cross checker now reports exactly:

```text
composition handoff altered the real workflow-declared MutWork
```

The checker reads workflow truth from the retained production
`ActivityRequested` projection, not `handoff.work`; `workflow_work` metrics use
the same independent projection. The sensitivity artifact has 179 operations,
395 journal entries, 408,928 bytes, digest
`sha256:cc315cffb050256d4accc49708afb9df2ebb1e6d56a084ed3b62673664280a58`,
and exact replay.

The existing workflow-local `RerunLanded` correlation counterexample remains
unchanged. Its co-mounted artifact reduces to the same workflow-only artifact
and exact violation, preserving the accepted local-checker localization
contract without making S3 part of the causal path.

## Crash, recovery, effect, and replay proof

The canonical path is:

1. accept one composition-owned signed webhook projection;
2. admit the head through the real V5 workflow and advance boundedly until the
   production lifecycle holds that head;
3. deliver the authorized change comment and advance until the real `git_gate`
   requests one workflow `MutWork`;
4. route its exact request to agents, start one modeled runtime, and accept one
   delivered result;
5. admit the unchanged work to readiness after delivery;
6. reconcile absent, read current authority, invoke the injected adapter once,
   publish once, accept the Git effect, and lose the response;
7. crash the whole S9 Timeline at phase `executed`, discarding every mounted
   generation and suspended frame;
8. restart generation 2 and reconcile the retained publication first; no agent
   or publication call repeats;
9. retain one `Pushed`, route it to the original workflow occurrence, and let
   the real production fold reach mutation `idle`; and
10. encode, decode, and exactly replay against fresh module construction.

The provider call order is exact:

```text
reconcile
claim
agent
claim
claim
publish_accepted
reconcile
```

The canonical evidence is:

```text
operation                push:comment:501:<head>:i1
expanded operations      179
journal entries          395
artifact bytes           408,112
final generation         2
crash phase              executed
accepted Git effects     1
agent runtime starts     1
accepted deliveries      1
readiness agent calls    1
lookup recoveries        1
workflow terminal        Pushed
workflow expected head   7b5be3d963a189f1e751c971cfdb62dc57ba4e59
journal digest            sha256:dda44d8e8425eaac78adb4123a87ff151db1214855ac352499901fa04fadacea
replay                    exact
```

## Exact-result sensitivity

The A/B scenarios share the exact workflow work, canonical coding request, and
publication payload digest. Only `CodingResult.proposed_commit_message` changes
from `Apply requested change` to `Apply bounded rename`.

```text
same workflow work                 true
same CodingRequest                 true
same mutation payload digest       true

first coding-result digest         9652e099bb4b6f1cbd562d81ec39e28f3430d2ae65ed3a18b391c2e0b42ad178
second coding-result digest        8742a5287492c3eed242ea19f05e1b1e83ae6a2b1ac42a6292bf12ff94404276

first result head                  7b5be3d963a189f1e751c971cfdb62dc57ba4e59
second result head                 1ef9171c26728845bcd0ef0cbc055b8e494f1a5f

both replays                       exact
```

This is the decisive correction to the prior noncausal path: publication
observably consumes the delivered agents value rather than another equivalent
result. The readiness-local `unchanged` sensitivity also proves that an exact
delivered non-changing result returns `DeclinedM` and performs no publication.

## Resource and artifact bounds

S11's global limits remain 1,024 operations, 256 owner steps, 64 eligible
actions, 256 leaf calls, 256 choice draws, 32 active faults, 8 generations,
1,000 logical microseconds, 4,096 journal entries, and 4,000,000 artifact
bytes. The V5 path requires bounded S11 workflow limits of 256 History records
and 16 pending Activities. The exact resource-key union is still enforced at
`Timeline.open()`; removing `workflow.commands` fails before execution.

Canonical peaks are:

```text
composition webhooks / handoffs       1 / 1
workflow commands / History / pending 3 / 154 / 4
agents operations / pending           1 / 1
agents runtime / receiver terminals   1 / 1
readiness calls / requests / terminals 7 / 1 / 1
readiness claims / publications       1 / 1
GitHub authorities / calls / reads    1 / 4 / 2
GitHub pending / retained bytes       1 / 1,392
host instances / routes / runnable    1 / 1 / 1
host loaded / readiness operations    1 / 2
```

Thirty-two deterministic `runtime:event_order` draws select work from agents,
GitHub, host, readiness, and workflow. These are simulation interleavings, not
thread, process, or distributed-concurrency evidence.

## Correspondence and limits

1. Production `host` remains the only runtime composition root. S11's
   composition module is an experimental router and detached-body HMAC
   projector, not a proposed host API.
2. The workflow proof executes the current real V5 Net and folds, but uses
   declaration-only Activity stubs, an in-memory History, and the real Petrus
   throughput policy to expose the relevant gate while unrelated gates remain
   held. It does not execute the complete target workflow.
3. Readiness executes the real production mutation gate and port/value shapes,
   but its bounded step, stores, authority truth, Git adapter, and injected
   coding runner remain experimental.
4. The accepted agents simulation models stable identity and delivery custody;
   it does not run Pi, workspaces, provider protocols, secrets, or cleanup.
5. The accepted GitHub and host simulations co-mount and pass their local
   checkers, but they are not readiness's live Git publisher or agents runtime.
   The proven causal vertical is specifically workflow `MutWork` -> agents
   delivered `CodingResult` -> readiness publication -> workflow `Pushed`.
6. Generation loss is process-local frame loss. No OS kill, SQLite/filesystem
   durability, transaction interruption, lease expiry, or restart discovery is
   exercised.
7. S9 exact replay applies only to this experimental artifact family. It does
   not claim artifact, profile, operation-count, digest, or byte compatibility
   with production CV18 or earlier experiments.
8. Current production correspondence tests still prove that a real change
   comment carries its instruction to `git_gate` and the current readiness
   world recovers one ambiguous authorized publication after crash. S11 does
   not claim semantic equivalence beyond those named overlaps.

No correction required reopening R1-R3, changing production, extending S3, or
placing result meaning in `MutWork`; therefore the approved stop conditions did
not trigger.

## TDD and verification evidence

Tests were changed before implementation. The three decisive red cuts were:

```text
agents      AttributeError: AgentsSimulation has no delivered
readiness   TypeError: ReadinessModule does not accept runner
composition ImportError: run_causal_composition does not exist
```

The acceptance review then supplied a valid full-flow instruction-substitution
counterexample. The correction tests were also written first: workflow tests
failed with `KeyError: 'request'`, and the S11 sensitivity failed because
`run_causal_composition` did not yet accept the substitution. The implementation
added only the History-derived projection and the missing cross-edge check.

The first real-V5 attempt used Petrus's conservative policy and stalled behind
held `dash_gate`. The correction selected Petrus's existing
`choose_throughput` policy; the real Net then exposed `git_gate` while unrelated
Activities remained held. No fold or transition meaning was copied.

Executed focused and correspondence evidence:

```text
S10 workflow + agents + readiness pytest     28 passed, 3 subtests passed
S11 composition pytest                       8 passed
current production correspondence pytest     2 passed
S11 Ruff format/check                         passed
S10 extension + S11 ty, sibling search paths passed
S11 evidence runner                           exact causal, result sensitivity,
                                              work-substitution, authority, and
                                              reduction artifacts
scripts/check quick                           10 passed
scripts/check full                            10 quick + 9 relay + 44 live,
                                              source/wheel built, 1,165 passed
```

The retained evidence runner emits the canonical causal artifact, the A/B
exact-result sensitivity, the workflow-work substitution observation, the
composition authority observation, and the workflow-local reduction. Every
emitted replay is exact.

The first full-gate attempt stopped before tests because the orb lacked the
locked demo-video TypeScript dependencies. After `bun install
--frozen-lockfile`, the next attempt installed the required Playwright browser
but its first cold browser launch exceeded the maintained five-second hook
timeout. The focused locked media gate then passed 44 tests, and a complete
rerun passed all stages above without changing a timeout, test, or assertion.

The follow-up changes exactly these 13 existing experiment files:

```text
10-workflow-simulation.md
spikes/10-workflow-simulation/workflow_simulation.py
spikes/10-workflow-simulation/test_workflow_simulation.py
10-agents-simulation.md
spikes/10-agents-simulation/agents_simulation.py
spikes/10-agents-simulation/test_agents_simulation.py
10-readiness-simulation.md
spikes/10-readiness-simulation/readiness_simulation.py
spikes/10-readiness-simulation/test_readiness_simulation.py
11-composition.md
spikes/11-composition/composition.py
spikes/11-composition/test_composition.py
spikes/11-composition/evidence.py
```

No production source, maintained test, S3, S9, other Experiment 10 module,
configuration, roadmap, decision, debt, worklog, ES-010 index, R4, or
Experiment 12 file changed. No commit or push was made.

## Exit assessment

The follow-up supplies the smallest honest causal alignment that the accepted
partial result lacked: real workflow-declared mutation meaning, exact agents
delivery custody, an injected readiness consumer of that exact result, one
observable result-dependent Git publication, lookup-first crash recovery, and
exact return to the original workflow occurrence. Local defaults and local
checker contracts remain intact, while one cross-module checker owns only the
new causal invariant.

The S11 candidate is ready for independent review and Navigator Experience
Report acceptance. That review may accept this bounded S11 result; it cannot
infer R4 or begin Experiment 12 without a separate Navigator ruling.
