# Experiment 10 — Readiness simulation

Readiness fan-out session S10x. Durable inputs: the ES-010 index, accepted
[`04-ports-adapters.md`](04-ports-adapters.md), accepted
[`05-readiness-tree.md`](05-readiness-tree.md), accepted
[`07-step-contract.md`](07-step-contract.md), the R3 decision
[`Timeline and coroutine stepper share bounded execution`](../../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md),
and accepted [`09-simulation-runtime.md`](09-simulation-runtime.md). The clean
repository baseline was local `main` and `origin/main` at
`cdc685e8f2b979057f15e851c35c482322c87dac`, which contains accepted S9.

Method: inventory the production one-PR readiness, mutation, authority, and Git
publication seams; mount one isolated readiness module under S9's exact
structural module contract and unchanged `Timeline`; execute the current
production mutation gate against deterministic strict agent and Git adapters;
cross the claim, accepted-effect, and recorded-terminal cuts with generation
loss; check the resulting state through a separately derived local model; and
encode, decode, and exactly replay the meaningful response-lost scenario. The
R2 and R3 architecture is fixed input. No production change, whole-Hamsterdan
composition, other local module, Experiment 11, or R4 ruling is in scope.

## Verdict

The readiness boundary can run alone under S9's runtime without constructing a
host, GitHub client, Petrus Engine, workflow Net, or agent runtime:

```text
strict Timeline commands
  -> retained readiness grant + workflow-owned MutWork
  -> readiness ActionRef(settle_mutation, stable operation)
  -> S9 CoroutineStepper offers one leaf
  -> production V5MutationGate.git_gate
       -> deterministic coding-agent seam
       -> deterministic production-shaped Git publication seam
  -> process-local terminal result
  -> retained readiness terminal on owner finish
```

The executable candidate is
[`spikes/10-readiness-simulation/readiness_simulation.py`](spikes/10-readiness-simulation/readiness_simulation.py),
with behavioral contracts in
[`spikes/10-readiness-simulation/test_readiness_simulation.py`](spikes/10-readiness-simulation/test_readiness_simulation.py).
The S9 runtime was neither copied nor changed. The focused invocation puts the
accepted S9 candidate on `PYTHONPATH`, so `ReadinessModule` mounts through the
same `ActionRef`, `Budget`, `Timeline`, fault, crash-generation, artifact, and
replay implementation accepted in S9.

The proof reuses these real production interfaces and values:

- `V5MutationGate.git_gate()` and `V5MutationGate.request()`;
- `MutationPublisher`'s concrete `reconcile(...)` and `publish(...)` method
  shape;
- the zero-argument `CurrentClaim` authority reader;
- workflow-owned `MutWork`, `Pushed`, `MovedM`, `FaultM`, and `DeclinedM`;
- credential-free `CodingRequest` and `CodingResult`; and
- `GitReconciliation`, `GitPublishResult`, `GitPublishError`, and
  `PublicationCategory`.

There is no real production readiness step to reuse yet. The current
`PrReadinessV5Application.settle()` still nests its 500-turn loop around
`V5Runtime.drain()`, and current Worker execution still combines claim, effect,
serialization, and terminal report. The experimental `ReadinessGeneration`
therefore supplies the S7/R3 target step around the real production mutation
gate. This is evidence for the target seam, not a claim that the current V5
application already implements it.

## Production interface and cut inventory

### Real effect and authority seam

`V5MutationGate.git_gate()` already preserves the central S4 contract:

1. derive one credential-free coding request and canonical payload digest from
   `MutWork`;
2. reconcile the stable Git operation before any authority read or agent call;
3. compare every `CurrentClaim` field before and after agent execution;
4. publish through the operation-keyed Git seam; and
5. return one declared workflow terminal.

`HostGitPublisher.reconcile()` and `publish()` define the real adapter shape.
The production implementation performs complete first-parent lookup, identity
and digest collision checks, fresh PR evidence, Git object creation, and exact
ref compare-and-swap. The deterministic adapter implements that same caller
interface without importing provider or simulation truth into the production
gate.

The deterministic `AuthorityReader` combines the retained readiness grant with
fresh modeled provider authority. Any difference in phase, incarnation, head,
base, or policy raises the same credential-free provider boundary class the
production gate already classifies as `FaultM`. The authority-movement contract
proves that an absent lookup followed by a mismatched claim performs no agent
call and accepts no Git effect.

### Missing production step seam

S7 requires separate `activity_attempt_claimed`,
`activity_effect_observed`, and `activity_terminal_recorded` cuts. Current
production does not expose those cuts:

- the Motus Worker claim and terminal report surround the Activity invocation;
- the entire mutation gate, including coding and Git publication, is one
  Activity call; and
- the application and runtime public convenience methods drain multiple
  actions.

The spike maps S9's fixed process-local phases to the evidence needed now:

| S9 position | Retained module state | Readiness meaning in this spike |
|---|---|---|
| after `start()` / `offered` | stable request and one idempotent claim marker | after `activity_attempt_claimed`, before any leaf effect |
| after `execute()` / `executed` | provider ledger may contain one accepted Git effect; terminal remains outside the owner | after `activity_effect_observed`, before terminal recording |
| after `finish()` / `idle` | one typed terminal is retained | after `activity_terminal_recorded` |

The second and third positions are distinct under Timeline, but terminal
recording currently happens when the suspended owner resumes in `finish()`;
it is not a second independently schedulable readiness action. Delivery still
needs the Petrus/Motus split named by S7 and R3 before production can return
both cuts as separate readiness `StepResult`s. The spike does not conceal this
gap behind finer production claims.

## Local simulation interface

`ReadinessModule` implements S9's exact structural boundary:

```text
name = readiness
open(context) -> ReadinessGeneration
drop(generation)
close(generation)
resource_usage(generation | None) -> exact named gauges

ReadinessGeneration:
  command(name, payload, context) -> StrictJSON
  observe(name, payload, context) -> StrictJSON
  eligible_actions(context) -> tuple[ActionRef, ...]
  async step(action, context) -> StrictJSON
```

The module object owns two retained stores across process generations:

- readiness custody: one admitted grant, operation-keyed `MutWork` requests,
  idempotent claim markers, and typed terminals; and
- deterministic provider truth: current authority, operation-keyed accepted
  Git publications, and an ordered port-call ledger.

`open()` creates only a process-local generation around those stores. `drop()`
does not transfer a frame, callable, held result, gate object, or exception.
Fresh generation eligibility comes solely from a request lacking a retained
terminal. The S9 runtime remains unaware of requests, claims, authority, Git,
terminals, and lookup-first recovery.

### Commands

| Command | Exact payload | Meaning |
|---|---|---|
| `admit_grant` | `phase`, `incarnation`, `head`, `base`, `policy` | retain the readiness-owned complete authority grant |
| `set_provider_authority` | the same five fields | set deterministic fresh provider truth independently of the grant |
| `request_mutation` | exactly the eleven production `MutWork` fields | retain one workflow-declared Activity request under its stable `op_key` |

`request_mutation` invokes production request projection as admission
validation, requires its complete authority to equal the durable grant, and
rejects reuse of one stable operation with different work.

### Observation, action, and fault vocabulary

| Kind | Name | Meaning |
|---|---|---|
| observation | `state` | detached grant, requests, claims, terminals, provider authority, publication ledger, and call order |
| observation | `check` | local independent checker report over the detached state |
| action | `settle_mutation` | execute or recover one exact pending mutation operation |
| fault | `git_response_lost` | accept one exact Git operation, move provider head, then lose the response |

The module-local `arm_readiness_fault()` validates the closed fault vocabulary
and exact operation payload before delegating to S9's generic occurrence fault
controller. Direct low-level `Timeline.fault()` remains intentionally generic;
Exp 11 composition must route named local faults through their module-owned
entry points if it wants unknown fault names rejected before execution.

Unknown command, observation, local fault, action, missing field, extra field,
malformed authority, undeclared agent operation, undeclared Git operation, and
operation-identity collision all fail loudly. No fake invents a plausible
terminal for unknown work.

### Bounds

The candidate uses one explicit S9 `Budget`:

| Measure | Limit |
|---|---:|
| expanded Timeline operations | 128 |
| completed owner steps | 16 |
| eligible actions per decision | 8 |
| leaf calls | 16 |
| choice draws | 8 |
| active faults | 8 |
| generations | 8 |
| logical time | 1,000 µs |
| journal entries | 512 |
| encoded artifact | 1,000,000 bytes |
| readiness calls | 32 |
| claims, publications, requests, terminals | 8 each |

One module action names one operation, offers one leaf, performs at most one
production gate invocation, and records at most one terminal. The production
gate's internal fixed sequence includes one coding call and one Git publication
call on the first path; recovery exits from initial reconciliation and makes
neither call again. This bounded single-operation proof does not claim the
current production gate's complete Git history scan satisfies S7's future
row/byte bound.

## Independent checker

`ReadinessChecker` receives only the detached simulation observation. It does
not read a desired-state field, the module's mutable stores, a gate return
expectation, or a production History representation. It treats the ordered
provider call ledger as the physical-effect observation and the operation-keyed
publication map only as provider result evidence. It derives:

- at most one `publish_accepted` call per stable operation;
- every physical acceptance has one provider result and every provider result
  has one physical acceptance;
- every accepted effect has one retained workflow request;
- accepted authority and Git parents equal the request's complete authority;
- any retained `Pushed` terminal names the provider-derived result head; and
- from call order, recovery's first post-acceptance call is reconciliation,
  with no later agent or publication acceptance.

One sensitivity contract leaves the operation-keyed publication map at one
entry and appends a second attainable `publish_accepted` call at the next
sequence. The checker independently reports exactly:

```text
operation = push:comment:9:<head>:i3
rule = one_effect_acceptance_per_operation
observed = 2
```

A second contract clears the result's implementation-supplied `recovered` flag
and replaces the first post-acceptance reconciliation call with an agent call.
The checker still reports `recovery_is_lookup_first`, proving it derives
recovery order from the ledger rather than trusting the result flag. These
separate derivations earn the checker: it catches a duplicate physical effect
even when the map and readiness terminal each look singular, and it catches
non-lookup-first settlement even when the result denies recovery. Direct shape
and vocabulary checks remain ordinary assertions rather than duplicated models.

## Accepted-but-response-lost proof

The scenario starts with one matching durable grant and provider authority, one
production `MutWork`, and one occurrence fault for that exact operation.

1. `Timeline.start()` retains the claim marker and offers
   `mutation.git_gate`. Crash in `offered` drops the frame before any provider
   or agent effect. Generation 2 derives the same pending action from stores.
2. The production gate reconciles absent, reads complete current authority,
   calls the deterministic credential-free agent once, reads authority again,
   and invokes the Git port.
3. The Git adapter accepts one operation and payload digest under the complete
   requested authority, derives one result head, moves provider truth to that
   head, and loses the response. The production gate classifies the boundary
   loss as `FaultM`.
4. Timeline stops in `executed`: the `FaultM` value exists only outside the
   suspended owner. Crash discards it. Generation 3 observes one response-lost
   publication, no terminal, and one still-pending request.
5. The fresh generation executes the same operation. The production gate's
   first call is `reconcile`; it finds the existing operation and returns
   `Pushed` before any moved-authority read or second agent invocation.
6. Owner finish records one `Pushed` terminal. Crash in `idle` and generation 4
   reconstruction preserve that terminal and expose no eligible action.

The complete port-call order is:

```text
reconcile
claim
agent
claim                 # agent's continuous-current callback
claim                 # post-agent authority fence
publish_accepted
reconcile             # fresh-generation lookup-first recovery
```

There is one agent call, one accepted Git effect, no second claim after the
accepted effect, and one final terminal. The provider's own effect moves the
head, but lookup-first recovery precedes and therefore does not misclassify the
operation as stale.

The generated evidence was:

```text
expanded operations   21
journal entries       51
artifact bytes        31,907
final generation      4
accepted Git effects  1
agent calls           1
response lost         true
lookup recovered      true
final terminal        Pushed
crash phases          offered, executed, idle
journal digest        sha256:bbd5ece634cf1d1524a249214735400316e4d71bf09a203d892f4a14684812fe
replay                 exact
```

The artifact was encoded through S9's single-version strict JSON contract,
decoded, and replayed against a fresh `ReadinessModule` builder. Expanded
operations, observations, generations, journal entries, final digest, and the
response-lost/recovery path matched exactly.

The pre-acceptance review's independent run exposed the earlier 31,916-byte
record as an envelope mismatch. Re-executing the exact tested scenario with
scenario ID `readiness-response-lost` produces 31,907 bytes. Encoding the same
Timeline state as `readiness-response-lost-evidence`, a nine-byte-longer
scenario ID, produces the old 31,916-byte figure while preserving all 21
operations, all 51 journal entries, and the journal digest. S9's digest covers
the journal, while encoded artifact size also includes `scenario_id`; the
canonical tested artifact is therefore 31,907 bytes.

## TDD and verification evidence

The behavioral contract was written first. After orb setup restored the locked
Python environment, the intended red run failed during collection with
`ModuleNotFoundError: No module named 'readiness_simulation'`. The smallest
implementation then made the same focused command pass all four scenarios:

```text
4 passed in 0.75s
```

Pre-acceptance review then supplied an attainable duplicate-effect
counterexample: the provider can physically accept the same operation twice
while its operation-keyed result map still contains one entry. The new
ledger-sensitivity contract failed against the first checker with `1 failed, 3
passed`; its facts reported one accepted effect where two
`publish_accepted` calls existed. The corrected checker and an additional
call-order sensitivity contract now pass with the original response-loss,
authority-fencing, and strict-vocabulary scenarios. The final focused rerun and
both repository gates exited zero:

```text
focused pytest          5 passed in 0.78s
focused Ruff            All checks passed; 2 files already formatted
scripts/check quick     10 passed in 1.49s
scripts/check full      10 Python policy tests passed in 1.44s
                        9 relay tests passed
                        44 live-capture tests passed
                        source and wheel distributions built
                        1,165 Python tests passed in 79.35s
```

## Correspondence and scope limits

- This is an isolated exploratory module, not `src/hamsterdan2` production.
- The real production mutation gate and its port/value interfaces run; the
  readiness step, retained in-memory stores, provider truth, coding agent, and
  Git adapter are experimental.
- The current V5 gate is one coarse leaf. The proof reaches its exterior
  claim/effect/terminal cuts through S9's phases, but does not solve the S7/R3
  Petrus bounded-load or split Motus Activity-execution gaps.
- Retained stores survive generation loss in one process. Real SQLite/JSONL
  durability, filesystem reconstruction, process death, lease expiry, and
  transaction interruption remain production correspondence evidence.
- The deterministic Git adapter proves operation identity, complete authority,
  one acceptance, response loss, and lookup-first ordering. It does not prove
  Git object construction, complete first-parent traversal, server-side ref
  CAS, network behavior, or provider credentials.
- The deterministic agent proves exact credential-free request and operation
  correlation. It does not run Pi, a subprocess, or workspace cleanup.
- No workflow topology or Petrus Engine is constructed. `MutWork` is the
  workflow-owned seam into readiness; workflow decision correctness belongs to
  the workflow fan-out session.
- No host, webhook custody, timer custody, route lifecycle, multi-PR fairness,
  or process-wide resource cleanup is constructed. Those belong to their local
  simulations and later composition.
- Direct low-level `Timeline.fault()` accepts any normalized point because the
  runtime knows no module semantics. The local readiness fault adapter closes
  the public scenario vocabulary; composition must preserve that routing.
- Current V5 import paths are reused as correspondence evidence only. The R2
  replacement ownership tree and no-compatibility ruling remain unchanged.

## Production-seam gaps carried forward

1. **No bounded readiness lifecycle step exists.** Delivery needs the S7
   `admit/progress/settle_terminal -> StepResult` seam rather than current
   nested drains.
2. **Petrus reconstruction is still coarse.** First-load History replay and
   retained-occurrence repair need the bounded provider seam already named by
   S7/R3.
3. **Motus Activity execution is still coarse.** Claim, effect observation,
   and terminal report need separate production cuts. Timeline phases prove
   the recovery invariant but are not a substitute for those durable return
   values.
4. **Production Git lookup is not page-bounded.** The deterministic adapter's
   one lookup call preserves semantics but supplies no row/byte correspondence
   for complete first-parent traversal.
5. **Module-owned fault routing is above generic Timeline.** Whole-app
   composition needs namespaced local fault entry points so unknown module
   vocabulary fails before a generic runtime fault is armed, without teaching
   the runtime readiness semantics.

These are delivery/interface gaps already implied by accepted S7–S9, not new
production debt and not authorization to change production during ES-010.

## Exit assessment

The isolated readiness candidate uses S9's exact runtime/module interface and
the real production mutation/authority/publication seam where one exists. It
defines strict local commands, observations, one occurrence fault, one action,
and exact global/resource bounds. Unknown inputs fail loudly. Its independent
checker derives physical effect cardinality and lookup-first ordering from the
ordered provider calls, then correlates them with separate request, provider
result, and terminal facts. It detects an attainable second acceptance that an
operation-keyed result map cannot retain.

The required meaningful failure accepts one Git effect and loses its response,
crosses crash/reload at the claimed, observed-effect, and recorded-terminal
positions, reconstructs without a frame, settles lookup-first under the same
stable identity, retains current-authority fencing, and exactly replays with one
effect and one agent call. No whole Hamsterdan was constructed, and the runtime
gained no readiness semantics.

Focused spike checks, `scripts/check quick`, and `scripts/check full` pass. No
production, maintained test, configuration, roadmap, decision, debt, worklog,
or ES-010 index file changed.

Review found no further correctness blocker within the isolated candidate.
Refactoring is not recommended: extracting the corrected ledger derivation
would add a one-use helper without shortening the contract. No new debt record
is recommended. The pre-acceptance checker defect is fixed in the spike, while
the production-seam gaps above remain already-ruled delivery inputs rather than
newly discovered debt.
