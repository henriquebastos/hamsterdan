# Experiment 3 — Pure workflow package shape

Session S3. Inputs: the ES-010 index and the ruled Phase A records
([01-ownership-map.md](01-ownership-map.md),
[02-value-ownership.md](02-value-ownership.md)); current source at commit
`0686067`. Method: a mechanism-ownership read of `net_v5`, `gating.py`, and
the Activity-definition sites in `host/v5`, plus a throwaway structural
prototype at [`spikes/03-workflow-shape/`](spikes/03-workflow-shape/) whose
`prove.py` executes three proofs: package structure (acyclic, no
package-object imports, externals bounded), one decision run end to end on a
real Petrus Engine with zero `hamsterdan` imports, and loud build-time
registry failure.

## Mechanism ownership map

| Mechanism | Today | Target owner |
|---|---|---|
| Net topology composition | `net_v5/topology.py` (`build_net_v5`, place-then-wire protocol) | `workflow/net/topology.py` (`build_net`) |
| Concern loops (declare/wire/seed, folds, batons) | nine `net_v5/<concern>.py` modules | `workflow/net/<concern>.py` (`esc.py` renamed `escalation.py`) |
| Pure folds and hydration | `net_v5/folding.py` via `vars(_colors)` discovery | `workflow/net/folding.py`, hydration by requested type (below) |
| Gate declaration | smeared across three places: per-loop `GATES` variant tuples, `gating.py` lane frozensets and handler `isinstance` chains, activity signatures | `workflow/activities.py` gate manifest (below) |
| Initial marking | `topology.seed_marking` (subject validation, per-loop contributions) | `workflow/net/topology.py`, unchanged protocol |
| Activity manifest | implicit: `host/v5/application.py:141-157` builds `ActivityDefinition`s from concrete implementations; the declared name/variant/lane facts live in the three gate-declaration sites | explicit `MANIFEST` in `workflow/activities.py`; readiness builds definitions from its implementations and validates them against the manifest |

The gate-declaration finding is the load-bearing one. Today one gate's
identity is stated three times and must agree silently: the loop's `GATES`
tuple lists variant color strings, the activity implementation's return union
lists the same classes, and `gating.py`'s handler subclasses hardcode the
operation-identity derivation and blocked synthesis in per-request
`isinstance` chains (`gating.py:181-208,213-236,244-263`). The target
manifest states each gate once:

```python
GateDeclaration(
    activity="rerun_gate",
    request=RerunReq,
    results=(RerunLanded, RerunMoved, RerunFault),
    lane="identified_inline",            # or "durable_publication"
    operation=lambda request: request.op,  # the lookup-first identity
    blocked=None,                        # durable lane: request -> *Blocked
)
```

Loops keep only `GATES = {"esc.rerun_gate": "rerun_gate"}` (transition path →
activity name); variants derive from `results`; the two lane frozensets
become the `lane` field; one generic `DeclaredGateHandler` replaces
`DurablePublicationActivityHandler` and `IdentifiedInlineActivityHandler`.
The manifest is workflow meaning: which work exists, which typed terminals
may answer, under which stable operation identity, and what a
durable-publication exhaustion synthesizes are all decisions the workflow
already owns through its values.

### S1's `gating.py` mixed-owner verdict, revised

S1 expected the module to split, with its execution half moving to readiness.
The trace says otherwise: `gating.py` imports only Petrus Activity- and
binding-defining modules (`petrus.motus.activity`, `petrus.impetus.binding`,
`petrus.impetus.{dsl,petrinet}`), which the index's dependency rule allows
for `workflow`. The genuinely effectful machinery — Dispatch, Worker, durable
queues, redispatch — already lives in `host/v5/runtime.py`. So the whole
gate-declaration-and-binding module stays workflow
(`workflow/net/gating.py`): `VariantPayloadConverter` (the durable `$variant`
result representation is part of the workflow's History interface),
`VariantRoutingActivityHandler`, the manifest-driven `DeclaredGateHandler`,
and `wire_gates`. Readiness execution contributes implementations and calls
`wire_gates`; it owns no gate machinery. This also keeps
`workflow/simulation` (S10) able to bind fake activities without importing
readiness — the harness pattern `tests/unit/readiness/net_v5/harness.py`
already proves that composition works.

Consequence for S5: `runtime.py`'s current imports of
`DURABLE_PUBLICATION_GATES` and `wire_gates` become reads of the manifest's
`lane` field and the same `wire_gates` — readiness → workflow, the permitted
direction. `host/service.py:198,222` reads the same lane fact for its durable
activity resolver seam.

## Target `workflow` tree and import graph

```text
workflow/
  values.py          WorkflowModel, cross-group aliases (per S2)
  observations.py    host -> workflow seam (per S2)
  facts.py           loop-to-loop mail (per S2)
  activities.py      Activity work/results + GateDeclaration MANIFEST
  net/
    folding.py       values / revive / route
    gating.py        variant converter, declared-gate handler, wire_gates
    topology.py      composer: build_net, seed_marking, GATES, TOKEN_CLASSES
    life.py  ci.py  escalation.py  review.py  mutation.py
    conversation.py  dashboard.py  reminders.py  readiness.py
  simulation/        S9/S10 scope, not designed here
```

Import graph, verified acyclic in the prototype (proof 1):

```text
values
  <- observations <- facts
  <- activities   (facts and activities also <- observations for shared aliases)
  <- folding? no: folding imports nothing of the vocabulary
activities <- net/gating           (GateDeclaration type)
values, observations, facts, activities, folding <- net/<loop>
net/<loop>, gating <- net/topology (full-module-path imports)
workflow.* -> petrus.impetus.{dsl, petrinet, petrinet.schema, binding,
              history_store*}, petrus.motus.activity, pydantic, stdlib
```

(*`history_store` only if `workflow/simulation` later needs it; production
workflow modules do not.)

### Cycle removal

The current SCC (`net_v5/__init__.py` re-exporting `topology` while
`topology.py:28` imports the nine loops through the still-initializing
package object) disappears under two rules, both demonstrated in the
prototype and both AST-checkable later (S12):

1. No package initializer re-exports. `workflow/__init__.py` and
   `workflow/net/__init__.py` state policy in a docstring and define nothing
   — the same explicit-empty-root pattern as `hamsterdan/__init__.py`.
2. No `from <package> import <module>` imports. The composer imports loops as
   `import workflow.net.ci as ci`, an AST edge to the module, never to the
   package object.

## Public import seam

Candidates:

1. **Defining-module seam (recommended).** Building:
   `workflow.net.topology.build_net`. Seeding: `topology.seed_marking`. Gate
   binding: `topology.GATES` + `activities.MANIFEST` +
   `gating.wire_gates(built, GATES, definitions, MANIFEST)`. Observing:
   `topology.TOKEN_CLASSES` (the color-namespace authority) plus
   `folding.revive` for hydrating place reads. This is the rule the project
   already applies to Petrus itself: import concepts from their defining
   modules; no root facade.
2. `workflow/__init__.py` re-exporting those names — rejected. S1 classed
   re-export facades as pass-throughs whose only value is import ergonomics,
   and one such facade is the source of today's only cycle.
3. A separate `workflow/net/build.py` beside `topology.py` — rejected by the
   deletion test: composition, gate aggregation, registry aggregation, and
   build validation are one unit; splitting them re-creates a pass-through.

**Stepping is deliberately absent from this seam.** The workflow exposes a
pure `BuiltNet`; the bounded step over it is `Engine.advance()`, owned by
Petrus and composed by readiness execution in production and by
`workflow/simulation` deterministically. Giving the workflow its own stepper
would create the second scheduler the index's driver rules reject. The
bounded-step *contract* over these cuts is S7's scope.

Naming fallout, permitted by the no-compatibility ruling: `build_net_v5` →
`build_net`; the Net identity `NetSpec("pr_v5")` → `NetSpec("pr_readiness")`
(History-visible; recorded on the instance identity fact).

## Explicit token-class registry (open item from S2)

Two mechanisms replace `vars(_colors)` discovery, and they solve different
problems:

1. **Hydration needs no registry at all.** Every fold names exactly the types
   its arcs bind, and a token's color is a class name, so
   `folding.values(binding, *types)` hydrates each requested type by matching
   `type.__name__` against token colors, building the adapter from the class
   in hand. `revive(cls, data)` likewise. One semantic is preserved
   deliberately: hydration keys on the **arc-stamped color**, not the
   producer's class — that is what lets a specialized fact ride into the
   dashboard's open envelope (below).
2. **The composer owns the explicit registry for validation and for external
   readers.** Every token-owning module (`values`, `observations`, `facts`,
   `activities`, each loop) exports an explicit `TOKENS: tuple[type, ...]`.
   `topology.py` aggregates them into `TOKEN_CLASSES: dict[str, type]`,
   refusing name collisions, and `build_net` validates that every declared
   place color and every manifest request/result names a registered class.
   Proof 3 demonstrates the loud failure S2 asked for: removing a class fails
   at build time with `place ci.state declares color 'CiState' with no
   registered token class`, not at first hydration. `TOKEN_CLASSES` also
   gives the string-coupled readers S2 catalogued (`agenticus` successor,
   World checkers) one importable authority for the durable color namespace.

## `GateFact` rename and legacy-lane deletion (open item from S2)

**Rename `GateFact` → `DashboardEvent`, owned by `workflow/facts.py`.** Its
single surviving meaning is the dashboard's deliberately open projection
mail. The mechanism worth documenting on the value itself: producers of
*specialized* facts (for example `ci.py` mailing its `ChecksFact` to both
`ready.checks_facts` and `dash.facts`) never construct the envelope —
`folding.route` stamps the **arc's** color, and every specialized fact's dump
(`{kind, incarnation, body}`) validates structurally against the open
envelope. That structural subtyping is the envelope's real interface;
`conversation`, `esc`, `reminders`, and `readiness` also construct it
directly for events with no specialized color. Loop-owned naming follows:
`dash.facts` → `dash.events`.

**The legacy `ready.facts` lane dies with the replacement tree.** Deletion
inventory in the readiness loop (`net_v5/readiness.py`):

- the input-only `ready.p.facts(GateFact)` place (`:499`);
- nine `migrate_*` transitions and their `_migrate_*` folds (`:263-300`,
  `:528-600`);
- the two inhibit-arc ordering groups over the legacy place (`:596-600`);
- `_migrate_legacy`'s `revive`-based envelope conversion.

A consequence worth naming: those migration branches are the **only** CEL
filters in the entire workflow (the topology docstring already says so), so
the replacement workflow is CEL-free — `Cel` and `arc` imports drop from
`readiness.py`, and arc filters leave the workflow's mechanism inventory
entirely.

## Loop file boundaries after the value moves

The S2 value moves change loop import lists, not loop content: each loop
keeps its folds, `declare`/`wire`/`seed`, its baton, sentinels, and terminal
record (now defined in-module per S2's locality ruling), its `GATES` entry,
and its `TOKENS` export. Assessment:

- **All nine loops still earn their depth.** Each owns one concern's durable
  decisions with a one-sentence interface; nothing in the value reshuffle
  merges or hollows any of them. The readiness loop shrinks by the legacy
  lane (~120 lines and all arc filters) and keeps its typed mailboxes.
- **`folding.py` survives, smaller.** It is the fold-authoring language of
  all nine loops; hydration-by-requested-type removes the discovery registry
  and the `contracts` import entirely.
- **`topology.py` grows** gate aggregation (unchanged), registry aggregation,
  and build validation (~40 lines) — all composition-time concerns that the
  deletion test keeps in one place.
- **`gating.py` stays whole as a workflow module** (revised S1 verdict,
  above), with the two handler subclasses dissolved into the manifest-driven
  one.

## Purity proof

Static: all nine loop modules, `folding.py`, and `topology.py` import only
`petrus.impetus.{dsl,petrinet}`, the value vocabulary, and stdlib;
`gating.py` adds `petrus.motus.activity`, `petrus.impetus.binding`, and
`petrus.impetus.petrinet.schema` — all within the index's "Petrus Net,
History-value, and Activity defining modules only" rule. Nothing imports
host, `github_app`, `agents`, or simulation.

Executable (proof 2): the prototype builds the Net, seeds a marking, and
drives one decision — `HeadSeen` and a failing `RunSeen` through ingress
doors, `HeadWork`/`RunWork` folds, a `ChecksFailure` mail, a `RerunReq` with
operation identity `rerun:fp-1:7:1` prepared through the manifest handler,
and the `RerunLanded` terminal folded into the ladder — on a real Petrus
Engine over in-memory History with a fake activity, and then asserts
`sys.modules` contains no `hamsterdan` module.

## Spike limits

The prototype is three mini loops (life, ci, escalation) with reduced fields,
one identified-inline gate, and no durable-publication gate:
`GateDeclaration.blocked` and `DeclaredGateHandler.project_failure` are
transcribed from today's `DurablePublicationActivityHandler` but **not
exercised** by the run proof. Nine-loop composition scale, the timer
protocol, and review's deferred-custody wake protocol are asserted from the
S1/S2 evidence, not re-proven here.

## Exit assessment

A workflow-only reader traces one decision end to end inside the package: an
observation enters through a door (`observations.py`, `life.py`), becomes
loop mail (`facts.py`, `ci.py`), becomes an Activity request whose terminals,
lane, and operation identity are declared beside its values
(`activities.py`), and the typed terminal folds back into loop memory
(`escalation.py`) — with no readiness-execution module in the trace. Proof 2
executes exactly that trace. Exit criterion met.

Handed onward: S4/S5 — readiness consumes `MANIFEST`, `GATES`, and
`wire_gates` instead of owning gate machinery, and `runtime.py`'s lane
imports become manifest reads; S6 — the `publication_qualification` record
shape (unchanged from S2); S12 — the two cycle-prevention rules and the
`TOKENS`/place-color validation as candidate architecture checks.
