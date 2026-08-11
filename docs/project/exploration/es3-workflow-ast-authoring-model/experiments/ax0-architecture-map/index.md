# AX0 — Architecture map and baseline example

- State: Completed, 2026-08-11.
- Question: what is the actual current architecture, and which small real
  workflow fragment serves as the baseline for every later experiment?
- Method: read-only inspection of the pinned Petrus checkout
  (`3b41f19aa68ed228e68324f7c6888371f805b560`) and Hamsterdan source. No
  code changed; nothing redesigned.

## Corrections to the working premise

1. **Typing is nominal, not structural.** `type Color = str`
   (`petrus/impetus/petrinet/schema.py`). The DSL accepts a Python class
   but stores `cls.__name__`. No registry maps colors back to classes;
   replay reconstructs generic `Token(color, data)` with JSON data. Domain
   hydration belongs to the application
   (`readiness/payloads.py::PydanticPayloadConverter`).
2. **CEL exists but is unused here.** Arcs accept
   `filter=Cel(...) | "symbol"` and transitions accept CEL guards
   (`petrus/impetus/binding/cel.py`), yet the production readiness net has
   0 filter declarations and 48 guard declarations, all Python. The
   incumbent for AX6 to beat is public `typed_guard`, and CEL's three
   deliberately different variable scopes (filter: bare token data fields;
   guard: place-named binding structs; completion: place-named marking
   queues) are a known Petrus design debt.
3. **Activities are not callbacks attached to transitions.** A transition
   declares a handler symbol. Two execution paths:
   - Pure `Handler` — `(Binding, output_arcs) -> {place: [tokens]}`,
     inline on the engine writer lane; `direct(fn)` derives one from type
     hints (`derive_typed_transform`).
   - `ActivityHandler` — `prepare(binding) -> ActivityInvocation`, frozen
     into history (`ActivityRequested`), dispatched by occurrence ID
     through `Dispatch` to a `Worker` that resolves the implementation by
     activity name; the frozen result (`ActivityCompleted`) is projected
     deterministically by `project(binding, result)` on the same
     transition occurrence. `DerivedActivityHandler` derives the bridge
     from an `@activity`-decorated typed function.
4. **Events are the only durable state, and the Net is not among them.**
   The 23-record `History` union is authoritative; marking, in-flight
   firings, timers, and idempotency indexes are replay projections.
   `Instance.resume(net, history, ...)` requires the identical `Net`
   re-supplied. Consequence for the whole series: **the AX compiler must
   be deterministic — same source, byte-identical net — or old histories
   will not replay.** `NetDefinitionV3` (canonical, round-trip-exact) and
   `NetUri` (canonical addresses for every declaration, e.g.
   `transition:/execute/review#handler`, `arc:/a->/b#filter:$0`) are the
   serialization and source-mapping substrate.

## Architecture map

```text
Authoring   petrus.impetus.dsl: NetSpec, p/t proxies, >>, arc.read(),
            direct(), typed_guard(), petri_handler(), ScopeSpec.stamp()
            -> build() -> BuiltNet(net, handlers, guards)
Structure   petrus.impetus.petrinet.schema: Net, Place(path, color),
            Transition(path, handler, guards, timers: Delay|Until),
            Arc(source, target, CONSUME|READ|INHIBIT, weight, color,
            filter), Cel, NetPath, NetUri; validated once, immutable
Serialized  petrus.impetus.net_definition: NetDefinitionV3 — canonical,
            versioned, language-neutral, no Python code, round-trip exact
Runtime     petrus.impetus.instance.Instance: marking = fold of History;
            enabledness/timers derived; fail-loud replay integrity
            petrus.engine.Engine: single-writer lock, advance(), deliver()
            with idempotent identity, lifecycle scopes
Persistence HistoryStore (JSONL/SQLite/Postgres), append-only Record
            union (FiringBegun, TokensConsumed, ActivityRequested,
            ActivityCompleted, TokensProduced, ...)
Execution   petrus.motus: ActivityInvocation -> Dispatch (Inline/Local
            SQLite with epoch+claimant fencing, retry policy) -> Worker /
            AsyncWorker resolve by activity name -> result by occurrence
```

Key facts for later experiments:

- Marking/tokens: `Token(color, data)` with JSON-faithful data; `Marking`
  immutable, sparse, FIFO per place; `TokenQueue` pairs tokens with entry
  instants (the `Delay` timer anchors).
- Typed derivation (`petrus/impetus/binding/__init__.py`) matches each
  parameter's dataclass annotation `__name__` to exactly one input arc
  color and fails loudly on 0 or >1 — the engine already enforces "types
  are not sufficient identity for topology" at this boundary.
- Guards conjoin; source transitions (no inputs) fire only on external
  delivery and refuse guards/timers.
- Output routing: `route()` deposits a token on every admitting output
  arc; tokens admitted by no arc are silently dropped — AX5 must confront
  this.
- Validation stages: DSL construction → `Net.__init__` structural →
  typed-derivation at bind → CEL compile at instance construction →
  replay integrity.
- Hamsterdan binding: `ACTIVITY_TRANSITIONS` (`topology.py` L64–75) maps
  11 `execute.*` transition paths to activity names and exact Pydantic
  request/result contracts, bound in `PrReadinessHost.open()`
  (`host/runtime.py` L336–346). Retry already exists at two levels:
  worker-level (`RetryPolicy` in dispatch) and net-level (the rerun
  fragment below) — the AX8 comparison is real, not synthetic.

## Baseline example

The **actions failure → rerun-or-repair fragment**,
`readiness/net/topology.py` L1461–1476 plus activity bridges L1228 and
L1239 (line numbers at the RS-017 state of `main`):

```python
rerun = t.authorize_rerun(
    handler=petri_handler(_rerun),
    guards=typed_guard(_first_failure, converter=PydanticPayloadConverter()),
)
(p.authority, p.mutation_state) >> arc.read() >> rerun
(p.actions_state, p.actions_basis) >> rerun >> (p.actions_state, work.p.actions_rerun)

repair_work = t.authorize_repair(
    handler=petri_handler(_repair),
    guards=typed_guard(_repairable, converter=PydanticPayloadConverter()),
)
(p.authority, p.actions_state) >> arc.read() >> repair_work
(p.mutation_state, p.actions_basis) >> repair_work >> (p.mutation_state, work.p.repair)

basis_retire = retire.t.actions_basis(guards=typed_guard(_basis_done, ...))
for place in (p.authority, p.actions_state, p.mutation_state):
    place >> arc.read() >> basis_retire
p.actions_basis >> basis_retire

# activity bridges, declared ~230 lines away:
work.p.actions_rerun(ActionsRerunRequest) >> execute.t.actions_rerun(handler="actions_rerun") >> p.actions_result
work.p.repair(RepairRequest) >> execute.t.repair(handler="repair") >> p.repair_result(RepairResult)
```

Why it qualifies:

- Two worker-dispatched activities (`actions_rerun`, `repair`).
- Six token types: `Authority`, `ActionsState`, `MutationState`,
  `ActionsObservation`, `ActionsRerunRequest`, `RepairRequest`.
- A three-way value branch on the same `actions_basis` token — competing
  guards `_first_failure` / `_repairable` / `_basis_done` — exactly AX6's
  single-type guard-routing case.
- Explicit wiring including read arcs and consume/replace state loops.
- Exhibits every named pain point: `_rerun`/`_repair` defined ~550 lines
  before attachment; one logical step spread across predicate, handler,
  wiring, activity bridge, and host binding; repeated
  `p.authority >> arc.read() >> t` boilerplate.

Caveat carried forward: these guards are **relational** (they read
`Authority` and adjacent concern state alongside the branched token) —
richer than a single-token filter. CEL guards support this (place-scoped
binding variables); CEL filters do not. Combinator-generated branches must
be able to express "guard over multiple bound tokens" or they fail this
baseline.

## Verdict

Complete; baseline selected. The architecture supports the layering
hypothesis cleanly — `NetSpec.build()` already is a small compiler onto
`Net`, and `NetDefinitionV3` + `NetUri` provide the serialization and
source-map substrate. Proceed to AX1.
