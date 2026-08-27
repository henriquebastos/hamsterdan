# Experiment 10 — Agents local simulation

Session S10-agents. The repository baseline was local `main` and `origin/main`
at `cdc685e8f2b979057f15e851c35c482322c87dac`, which contains accepted S9.
Durable inputs were the ES-010 experiment routing, accepted
[`04-ports-adapters.md`](04-ports-adapters.md), the agent-relevant cuts in
[`05-readiness-tree.md`](05-readiness-tree.md),
[`06-host-narrowing.md`](06-host-narrowing.md), and
[`07-step-contract.md`](07-step-contract.md), accepted
[`09-simulation-runtime.md`](09-simulation-runtime.md), and the fixed decisions
for host-owned Agenticus routing, Pi-only execution, lifecycle cancellation, and
the public Timeline/internal CoroutineStepper split. Those inputs were treated
as rulings, not questions to reopen.

Method: inventory the current agent request/result port, Pi operation identity,
host route custody, readiness terminal settlement, and the effect-adjacent cuts;
then implement one isolated agents module under S9's exact structural interface.
Drive submit, acceptance, result availability, cancellation, terminal delivery,
and two response-loss recoveries through strict Timeline commands and one-leaf
actions. Derive expected final state independently from the expanded artifact,
corrupt one observation to test checker sensitivity, and exactly replay the
meaningful failure. No production code, maintained test, configuration, other
module simulation, whole-application composition, or R4 work is in scope.

## Verdict

The agents slice can run alone under S9's exact runtime contract without giving
the runtime agent semantics. The candidate at
[`spikes/10-agents-simulation/agents_simulation.py`](spikes/10-agents-simulation/agents_simulation.py)
and its executable contract at
[`spikes/10-agents-simulation/test_agents_simulation.py`](spikes/10-agents-simulation/test_agents_simulation.py)
cover the required lifecycle:

```text
submit ─▶ accept ─▶ run ─▶ terminal available ─▶ terminal deliver
                  │                              │
                  ├─ runtime response lost       └─ delivery response lost
                  │        │                              │
                  │        ▼                              ▼
                  └─ retained terminal lookup     retained receiver lookup

accept ─▶ cancel ─▶ cancellation terminal available ─▶ terminal deliver
```

The simulation imports the production request/result values and Pi prompt
validation, reproduces Pi's stable execution identity exactly, and keeps all
agent values free of host credentials. Its durable modeled stores live on the
module outside each process-local generation. S9's runtime only schedules
`ActionRef` values, executes the generic leaf phase machine, injects named
faults, enforces budgets, crashes generations, records artifacts, and replays.

This meets the agents part of Experiment 10's local exit criterion: one
meaningful agent failure is generated, checked, and exactly replayed without
constructing workflow, readiness, GitHub, host, or whole Hamsterdan.

## Production interface and custody inventory

| Concern | Current production owner | Experimental use |
|---|---|---|
| Review, conversation, and coding requests/results | `hamsterdan.agents.protocol` dataclasses and `AgentRunner` | All three exact request shapes cross strict `submit`; the meaningful proof uses an exact `ReviewResult` shape |
| Prompt and request validation | `hamsterdan.agents.pi.encode_prompt` | Every submission is constructed as its production dataclass and encoded through the real validator |
| Result validation | `hamsterdan.agents.protocol._validate_result` | The deterministic terminal is validated against the exact production request before it enters modeled runtime custody |
| Agent execution identity | `PiNativeRunner._run` | Exact `pi:sha256(logical_operation + "\0" + attempt)` identity; it remains stable across crashes and retries |
| Route composition | host `AgentRouteStore` | Not simulated as agent state. Host continues to bind a logical operation to immutable Pi composition across attempts and restart |
| Pi runtime, workspace, and secrets | host composition | Deliberately absent. The module sees a repository URL and credential-free request values, never installation credentials or Pi runtime objects |
| Workflow terminal interpretation and route settlement | readiness execution plus host route settlement | Represented only as an idempotent receiver terminal store. The simulation does not make readiness or route-authority decisions |

The production `AgentRunner` surface is synchronous: `review`, `converse`, and
`code` each encompass startup, execution, waiting, validation, and cleanup. The
experimental lifecycle therefore corresponds to real values and real operation
identity while exposing target bounded cuts that production does not yet expose
as public methods.

## Exact local module interface

The module implements S9's structural contract without introducing another
interface class:

```text
AgentsSimulation:
  name = "agents"
  open(context) -> generation
  drop(generation) -> None
  close(generation) -> None
  resource_usage(generation | None) -> named integer gauges

generation:
  command(name, payload, context) -> strict JSON
  observe(name, payload, context) -> strict JSON
  eligible_actions(context) -> tuple[ActionRef, ...]
  async step(action, context) -> strict JSON
```

`open` gives a generation access to retained module stores. `drop` discards no
durable value and preserves no coroutine frame. After restart, eligibility is
recomputed from operation, runtime-terminal, and receiver-terminal stores. The
internal owner coroutine may cross zero leaves for acceptance or exactly one
leaf for run, terminal lookup, cancellation, or delivery. No action calls a
different module.

### Commands

| Command | Exact payload | Durable effect |
|---|---|---|
| `submit` | `kind`, `repository_url`, `operation`, `attempt`, `request` | Validate one production request and retain it under stable execution identity; an exact duplicate is idempotent |
| `terminal` | `operation`, `attempt`, `result` | Validate and retain one deterministic production result for the modeled runtime effect |
| `cancel` | `operation`, `attempt`, `reason` | Retain a cancellation request before terminal availability |

Each command accepts exactly its declared keys and bounded strict JSON. Unknown
commands, kinds, operations, attempts, request fields, result shapes, and
credential-shaped keys fail immediately. The operation-capacity check occurs
before store mutation. A different request under an existing execution identity
and a different repeated terminal or cancellation reason are identity
collisions, not retries.

### Observations

| Observation | Result |
|---|---|
| `operation(operation, attempt)` | One operation's state, terminal kind/status, source, retained availability, and effect counters |
| `state()` | All operation summaries sorted by agent kind, operation, and attempt |

Unknown observations and unknown operation identities fail. The final `state`
observation is the checker boundary; the checker does not read module stores.

### Actions and one-leaf cuts

| Action | Leaf | Completion cut |
|---|---|---|
| `accept` | none | Operation owner has accepted the submission |
| `run` | `runtime.run` | A newly started runtime terminal is available to the owner |
| `terminal.available` | `runtime.terminal.lookup` | A retained runtime terminal is available after reconstruction |
| `cancel` | `runtime.cancel` | One cancellation terminal is available without starting the operation |
| `deliver` | `terminal.deliver` | The receiver response confirms its retained terminal |

Eligibility is derived only from durable state. A submitted operation offers
`accept`; an accepted operation prefers a retained runtime-terminal lookup,
then cancellation, then a declared deterministic run; an available terminal
offers delivery; a delivered operation offers nothing. Runtime loss cannot
turn into a second runtime start because lookup eligibility outranks run.

### Faults

| Fault point | Injection position | Meaning |
|---|---|---|
| `runtime.loss.after_terminal` | Inside `runtime.run`, after the runtime terminal is retained and before owner return | Pi/runtime work completed durably but its process-local response was lost |
| `terminal.delivery.response_lost` | Inside `terminal.deliver`, after the receiver retained the terminal and before owner return | At-least-once delivery was accepted but the acknowledgement was lost |

Both require the exact execution identity in their payload. Wrong identities or
multiple matches fail loudly. The owner state changes only after `finish`, so a
crash at the executed phase leaves enough retained evidence to reconstruct
without a frame.

### Bounds

The default local store admits at most 16 operations. The proof budget caps 256
expanded operations, 64 owner steps, 16 eligible actions per decision, 64 leaf
calls, 64 choice draws, 16 active faults, 16 generations, 1,000 logical
microseconds, 2,048 journal entries, and a 1,000,000-byte artifact. Named gauges
independently cap operations, pending operations, runtime terminals, receiver
terminals, and terminal declarations at 16 each. Commands are bounded to
256,000 bytes and deterministic terminals to 4,000,000 bytes. S9 remains the
single owner of budget termination and artifactability.

## Durable cuts and recovery authority

The modeled stores deliberately separate four authorities:

1. The operation store owns submission, acceptance, cancellation intent, and
   owner-visible state.
2. The deterministic terminal-declaration store supplies the scripted provider
   outcome but cannot settle owner state.
3. The runtime-terminal store owns whether execution has already produced a
   terminal and counts starts/lookups/cancellations.
4. The receiver-terminal store owns whether terminal delivery has already been
   accepted and bounds accepted delivery to one per execution identity.

This separation is what makes at-least-once execution honest. The first run or
delivery leaf may alter its effect store and lose its response while the owner
still reports the pre-call state. After generation loss, the durable effect
owner—not a saved coroutine—authorizes lookup-first recovery. The second
delivery attempt is real, but the receiver returns its retained terminal rather
than accepting a second terminal.

The simulation does not move durable authority into agent territory. A
repository URL, production request value, logical operation, and attempt are
the complete submission. Host route composition and credentials remain absent,
and readiness/host remain the production owners of freshness, revocation, and
route settlement.

## Independent checker

`AgentsChecker` supplies a different semantic derivation for the one property
that benefits from it: final lifecycle state and effect cardinality. It reduces
only expanded artifact operations:

- `submit`, `terminal`, and `cancel` commands declare expected identity and
  intent;
- executed leaves independently count runtime starts, terminal lookups,
  cancellations, delivery attempts, and accepted receiver terminals, including
  effects whose responses were lost;
- completed owner actions derive accepted, available, and delivered states;
- the derived model is compared with the final `state` observation.

It does not call module methods, inspect module stores, or copy the module's
eligibility function. The sensitivity contract changes the final observed
`accepted_deliveries` from 1 to 2; the checker rejects it with
`accepted_deliveries expected 1, observed 2`. Exact replay is a separate
runtime check and does not substitute for this semantic derivation.

Pre-acceptance review found that the original checker replaced this derived
model whenever it encountered another successful `submit`. The module correctly
treats an identical resubmission as idempotent, so a duplicate after delivery
could reset only the checker's model to `submitted` and falsely reject a valid
artifact. The corrected checker retains the first full submission declaration,
compares later declarations independently, preserves all accumulated lifecycle
state for an identical duplicate, and reports a different declaration under the
same execution identity as a collision. Expanded `failure` attempts are ignored
before command state transitions. Under S9, the rejected collision itself is
not a completed command operation; a regression executes checking and exact
replay after that rejection to prove the surviving artifact is not distorted.

A second independent model for production request validation would add no
independence: the useful evidence is that the candidate actually constructs the
real production dataclasses and crosses the production codec/validator.

## Meaningful failure and exact replay

The required failure is one review execution with two ambiguous effect returns:

1. Submit and accept the exact production `ReviewRequest`.
2. Declare a valid deterministic `ReviewResult`.
3. Execute `runtime.run`; retain its terminal and then inject
   `AgentRuntimeLost`. The owner remains `accepted` while the runtime terminal
   is already available.
4. Crash at phase `executed`, restart generation 2, and complete
   `runtime.terminal.lookup`. No second runtime start occurs.
5. Execute `terminal.deliver`; retain the receiver terminal and then inject
   `TerminalDeliveryResponseLost`. The owner remains `available` while the
   receiver terminal is already available.
6. Crash again at phase `executed`, restart generation 3, and redeliver. The
   receiver returns its retained acceptance rather than accepting another
   terminal.
7. Observe final state, run the independent checker, and replay all expanded
   operations against a fresh module.

Executed evidence:

```text
focused contracts:    9 tests, OK
operations:           23
journal entries:      54
artifact bytes:       35,250
final generation:     3
crash phases:         executed, executed
runtime starts:       1
terminal lookups:     1
delivery attempts:    2
accepted deliveries: 1
checker:              passed
replay:               exact
journal digest:       sha256:82ccd84dc965c84db24fb49bc8313097b770575b9c03dabd42a22144e2086559
```

Repository validation was green after restoring the orb dependencies already
prescribed by `.agents/setup`:

```text
uv run --frozen python test_agents_simulation.py     9 passed
uv run --frozen python agents_simulation.py          checker true, replay exact
ruff check + format --check on both spike files      passed
scripts/check quick                                  10 architecture tests passed
scripts/check full                                   9 relay + 44 media + 1,165 Python tests passed
```

The separate cancellation scenario accepts a coding request, records one
cancellation request, performs one cancellation leaf, delivers one typed
`failure/canceled` terminal, starts no runtime, passes the checker, and replays
exactly. Additional regressions resubmit that delivered operation idempotently,
reject a changed request under the same execution identity before rechecking,
and route a non-object coding result through the named production protocol
validator without terminal mutation.

## Production seam gaps

The spike exposes six gaps for the replacement design. They are findings, not
authorization to change production in this session.

1. **The public `AgentRunner` hides bounded lifecycle cuts.** Its synchronous
   `review`, `converse`, and `code` methods do not separately expose submit,
   acceptance, runtime-terminal availability, or terminal delivery. A target
   bounded owner needs those cuts without moving Pi runtime or credentials out
   of host composition.
2. **There is no public lookup/resume terminal seam.** Pi's current runner can
   look up operation state internally while running, but a reconstructed owner
   cannot ask a public agent capability for the retained terminal by stable
   operation identity before deciding to restart work.
3. **Route custody and terminal custody are distinct but not represented by one
   bounded contract.** `AgentRouteStore` durably binds logical operation to
   immutable composition and settles routes after workflow terminals; it does
   not own agent runtime terminals. The replacement needs to preserve that
   distinction while making reconstruction explicit.
4. **Exact result validation is private.** The spike must import
   `_validate_result` to prove correspondence with current review,
   conversation, and coding outputs. A replacement agents boundary needs a
   public defining-module codec/validator, not a new root facade or runtime
   special case.
5. **The maintained deterministic review adapter has a broader fallback than
   the target strict vocabulary.** Conversation and coding modeled terminals
   are declared by exact operation/attempt; review can synthesize a fallback.
   Target simulation should require every terminal to be declared against the
   stable execution identity so an undeclared outcome cannot look successful.
6. **Lifecycle cancellation is currently exception-shaped.** Production
   `AgentProtocolError` carries canceled/timed-out and result/cleanup categories;
   the local module normalizes cancellation into one JSON terminal for checking
   and replay. The target boundary must choose and publicly own the exact typed
   terminal encoding while preserving those distinctions.

## Correspondence and scope limits

| Evidence established here | Evidence deliberately not claimed |
|---|---|
| Exact current request dataclasses and prompt validation for review, conversation, and coding | Real Pi execution, provider protocol behavior, or model output quality |
| Exact current Pi operation identity across two reconstructed generations | Compatibility with historical runtime state or artifacts |
| One-leaf cuts, retained terminals, at-least-once delivery, cancellation, resource bounds, and exact deterministic replay | Real process death, filesystem durability, SQLite durability, thread interleavings, cleanup races, or cancellation of a live Pi subprocess |
| Host credentials and Pi runtime objects do not enter the module or proof artifact | Proof that arbitrary user-controlled text contains no secret; the spike can reject credential-shaped field names only |
| Independent derivation detects a corrupted terminal-acceptance count | Whole-Hamsterdan authority, freshness, route revocation, workflow folding, or cross-module fairness |

The deterministic terminal declaration is test-script input, not a proposed
production API for injecting agent answers. The retained Python stores model
durable owners but are not a storage implementation. The crashes revoke S9
generations and process-local frames; real process-kill correspondence remains
separate evidence. No workflow, readiness, GitHub, host, Experiment 11, or R4
claim follows from this local proof.

## Pre-acceptance review and debt recommendation

The checker correction is local to artifact reduction and leaves module,
runtime, and fixed architecture semantics unchanged. The new tests exercise the
reported failure directly, the rejected-collision boundary, and the adjacent
coding-validation path. No further refactoring is recommended before
acceptance: extracting declaration handling or cancellation setup would add
names without reducing the remaining experiment complexity. No debt record is
recommended. The six production seam gaps above remain bounded exploration
findings for S11/S12 synthesis rather than implementation debt introduced by
this spike.

## Exit assessment

The agents local module satisfies the assigned Experiment 10 exit condition:
strict real-interface submissions, acceptance, run, terminal availability,
terminal delivery, cancellation, runtime loss, response-loss recovery, explicit
bounds, a semantically independent checker where useful, one exact meaningful
failure replay, and no whole-Hamsterdan construction. The production seam gaps
above should be carried into S11/S12 synthesis only after Navigator acceptance;
this record does not alter the ES-010 index or any fixed R2/R3 ruling.

## S11 causal-alignment extension — exact delivered terminal seam

The accepted observation surface reports delivery state and counters but does
not expose the typed value that the receiver accepted. That was sufficient for
the local proof and insufficient for S11: readiness must consume the delivered
agents result itself, not a separately generated equivalent.

The approved extension adds one bounded public simulation seam:

```text
AgentsSimulation.delivered(logical_operation, attempt) -> DeliveredExecution

DeliveredExecution:
  kind
  repository_url
  operation
  attempt
  typed request
  typed result
```

The method derives the existing stable execution identity, requires lifecycle
state `delivered`, reads the exact receiver-terminal store, rejects canceled or
failure terminals, revalidates the typed result against the retained request,
and returns detached deep copies. It does not introduce another terminal
store, reconstruct a result from summary fields, or make a readiness decision.
Pre-delivery access, unknown identity, and canceled delivery fail explicitly;
mutating a returned result cannot mutate retained agent custody.

The original lifecycle, cancellation, response-loss, checker, budget, and
replay contracts remain unchanged. In S11 the seam exposes one delivered
`CodingRequest` and `CodingResult` under
`mutation:owner/repo:pr:7:<workflow op_key>`, attempt 1. The composition-owned
adapter validates all of those fields before returning that exact result to
readiness.
