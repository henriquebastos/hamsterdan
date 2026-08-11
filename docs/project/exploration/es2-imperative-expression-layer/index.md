---
status: Thickening
opened: 2026-08-11
navigator: Henrique
---

# ES-002 — Imperative expression layer compiled to the readiness Net

## Inquiry

Can Hamsterdan's workflow logic be expressed in an imperative-ish, direct-style
DSL — sugar that compiles to the existing Petri-net topology — so the durable
machinery (Petrus Engine, marking, History, Motus Activities, lifecycle scopes,
host composition) stays exactly as it is while the expression surface stops
feeling low-level and ad hoc? And separately: does any other language or
paradigm offer enough leverage to justify leaving Python, given that adoption
demands simplicity and strong developer experience?

This inquiry is distinct from ES-001. ES-001 resolved *which layer owns which
execution mechanics*; ES-002 asks *how the remaining genuine workflow should be
written down*.

## Signals

- Navigator hunch (2026-08-11): the way we express Petri nets and transitions
  "feels very low-level and very ad hoc"; effect-oriented programming's
  isolation of side effects resembles what Petrus/Hamsterdan already do at the
  host boundary.
- GOTO Book Club episode on *Effect Oriented Programming* (Frasure, Eckel,
  Ward — the ZIO/Scala book, Feb 2026): effects as typed, deferred, composable
  descriptions; retry/timeout/fallback/test substitution as value
  transformations.
- `suned/stateless`: generator-based one-shot algebraic effects in Python.
- `readiness/net/topology.py` after the ES-001 refinements: 46 places, 69
  transitions, 17 retirements — but 1,672 lines of hand-wired arcs, string
  place names, `_hydrate`/`_guard`/`_put` binding plumbing, and one
  "authorize → typed request → result rejoins current marking →
  accept/supersede/retire" fragment repeated per concern.

## Assemblage — evidence gathered 2026-08-11

### Hamsterdan is already effect-oriented; the gap is notation

Activities are the typed effect descriptions (exact Pydantic request/result
contracts), the host is the handler/environment, and the Net is the durable
program that sequences them. ES-001 independently named the Activity module
"an effect interpreter." What the effect ecosystems add is a direct-style
surface, not better durability.

### The literature splits into two families

**Code-is-the-workflow (durable execution).** Temporal, Azure Durable
Functions, DBOS, Restate, Resonate obtain an imperative surface by
deterministic replay against a journal or step-result checkpointing in a
database. Costs: determinism sandboxes, versioning/patching pain
(`workflow.patched()`, immutable deployments, drained workers), durable state
implicit in code position. No production system persists continuations; all
re-derive them. OCaml 5 continuations are explicitly one-shot in-memory;
Unison Cloud verifies only typed value storage; Golem replays an oplog.

**Compile a structured surface onto a coordination substrate.** Direct
precedent exists: BPMN→Petri-net transformations (Dijkman/Dumas/Ouyang), van
der Aalst's Task Structures→workflow nets, process-algebra net semantics, and
Colored Petri Nets/CPN ML (net owns concurrency and synchronization; a real
language owns guards and data). The Workflow Patterns catalogue plus WF-net
soundness supply acceptance criteria. No mainstream compiler exists from
imperative Python-like syntax to net topology; the sound approach in every
precedent is a *restricted* workflow language compiled construct-by-construct
into verified fragments, never arbitrary code.

Petrus's marking + typed History is a more declarative and inspectable durable
representation than any replay journal. The missing piece is expressiveness,
not machinery.

### `stateless`: right syntax, wrong persistence

Business logic `yield from`s typed Ability values; handlers interpret and
`send()` results back; the suspended generator frame is the continuation. Best
current Python syntax precedent (same shape as Effect-TS `Effect.gen`), typed
through unions without a checker plugin, actively maintained — but small,
single-maintainer, pre-1.0, and a suspended generator is live process state,
not durable data. Role here: design reference for the surface, never the
runtime or the workflow representation.

## Hypothesis — three-layer model

```text
Surface   restricted imperative-ish Python DSL
          authorize / effect / accept / race / retry-scope
          (builder or generator syntax — sugar only)
              | compiles at build time, never at runtime
IR        typed net fragments — the durable program
          places, transitions, arcs; WF-net soundness and
          workflow-pattern checks; diffable, inspectable
              | executes unchanged
Machinery Petrus Engine, marking, History, Motus Activities,
          lifecycle scopes, host composition
```

The Net remains the durable "free program" (the effect world's description
value). Mapping: operation declaration = Activity contract; performing an
operation = the request/result place pair ES-001 proved must exist; handler =
host-composed Activity module. Nothing about markings, History, Motus custody,
authority fencing, or recovery changes even in principle.

## Candidate experiments

1. **Combinator layer first.** Define `sequence`,
   `authorized_effect(owner, request, accept, supersede)`, `race`, and
   retirement-scope combinators, each lowering to a verified net fragment.
   Decisive test: regenerate the current readiness topology from combinators
   and diff it against the hand-written net. No semantic change; pure
   expression change.
2. **Imperative sugar second**, only after fragment semantics are stable —
   possibly `stateless`-style generator syntax traced or compiled statically,
   never executed as a live continuation.
3. Each surface construct documents its generated fragment, delivery
   semantics, cancellation behavior, and soundness assumptions, using the
   Workflow Patterns catalogue as the test suite.

## First production refinement — 2026-08-11

### A bridge-only production helper did not earn its abstraction

The current topology has a real repeated Activity bridge:

```text
typed request place -> Activity transition -> typed result place
```

The smallest proposed production helper only replaced the already fluent and
more visible `work >> transition >> result` expression with a name. Applying a
single broad `owned_effect` helper directly in production would immediately
have needed callback hooks, custom relational reads, preprocessing, recovery
destinations, optional fan-out, and exceptions. That one universal shape would
serialize the existing arcs into configuration rather than remove a workflow
concept, so no combinator or DSL was introduced into `main`.

This narrows rather than falsifies the independent prototype below. Repetition
alone does not earn a helper, and one universal owned-effect combinator is not
the emerging answer; exact regeneration is separately testing a small grammar
of named semantic fragment families. Promotion still requires each family to
eliminate a demonstrated burden while retaining an obvious lowering.

### Direct typed transformations clarified a narrower boundary

Six one-output acceptance transitions did contain accidental expression
mechanics. Generic handlers hydrated every selected token, searched values by
runtime type, reflected through a folder wrapper, zipped one result to one
output, and serialized it. Petrus's existing direct handler contract expresses
the same rules as ordinary typed functions:

```python
def _accept_dashboard(
    authority: Authority,
    state: DashboardPublicationState,
    result: DashboardPublicationResult,
) -> DashboardPublicationState:
    ...
```

RS-014 applies that form only to human, change, repair, conversation,
dashboard, and readiness acceptance. Dynamic fan-out, optional output,
multi-owner folding, and target-sensitive routing remain Petri-aware because
their topology is part of their meaning. The strict Pydantic converter moved
from `host` to `readiness` so replayed inputs and direct outputs share the same
domain-owned validation boundary.

The result preserves the exact 46-place, 69-transition, 309-arc Net. It is a
local notation improvement, not by itself evidence that an imperative layer or
fragment IR is warranted. It establishes a stronger experiment rule: first use
the smallest existing Petrus expression that says the truth directly;
introduce a new surface only when that is still insufficient. It also removes
the application-private `_fold_owned` seam used by the early prototype, so the
prototype's next rebase must reconstruct these acceptance fragments through
public typed direct transformations rather than depend on that accidental
helper.

### The relational conversation join is also an honest direct transformation

RS-015 inspected every remaining use of `_hydrate`, `_values`, `_put`,
`_route`, `_guard`, and `_typed_guard`. One more adapter was accidental:
`start_conversation` reads the nine current concern states, consumes one
authorized `ConversationObservation`, and produces exactly one
`ConversationClassificationRequest`. The domain function already declared
that complete ten-input/one-output contract; its Petri adapter only repeated
the types, searched the binding, and serialized the result.

The domain function is now the direct Petrus handler. Its arcs still expose the
relational join, and the readiness Pydantic converter owns strict replay
hydration. The other residual helpers were retained: they implement
heterogeneous output, optional/target routing, enabledness, retirement, or
advanced Petri handlers. This reinforces the production rule: direct typed
functions are sufficient for one unambiguous result even when the read set is
large; a fragment grammar must address the remaining *topological* semantics,
not reproduce typed function binding.

## Language evaluation

1. **Stay in Python.** Machinery, team, and the compile-to-net strategy all
   favor it. Weakness: no effect rows, so unhandled-effect tracking is encoded
   in unions with the limits `stateless` demonstrates. Tolerable, because
   durability guarantees come from the Net, not the type system.
2. **TypeScript + Effect** is the only ecosystem move worth revisiting later:
   production core, best direct-style DX (`Effect.gen`, typed errors, Layers),
   but `@effect/workflow` was still alpha in 2026 and the move means rewriting
   Petrus, not sugaring it.
3. **Scala (ZIO/Kyo)**: most mature typed-effect ecosystem; maximizes exactly
   the adoption friction Hamsterdan wants to minimize. Kyo advertises durable
   workflows but is pre-1.0.
4. **Unison, Koka, Effekt, Flix, OCaml 5**: design references only. None has
   verified durable continuations; Koka self-describes as not production-ready.

Decisive negative finding: switching languages buys syntax and types, never
durability. The language question is separable from, and subordinate to, the
expression-layer question.

## What must not change

- The Net stays the single durable workflow representation; no live
  continuation (generator, fiber, coroutine) may become workflow state.
- ES-001's boundary holds: Motus owns execution, lifecycle scopes own
  generation cleanup, the Net owns authorization/acceptance, the host composes.
- Any Petrus enhancement must preserve the trivial application path.

## Ownership — Navigator direction 2026-08-11

The DSL's destination is Petrus; the inquiry's home is Hamsterdan. The tension
between those was resolved by observing that the comparison experiment needs no
Petrus change: the combinators lower to the existing public
`petrus.impetus.dsl` surface (`NetSpec`, `arc`, `petri_guard`,
`petri_handler`) that `topology.py` already calls by hand.

- Exploration and prototyping happen in Hamsterdan as application-local code.
  Hamsterdan owns the pressure, the comparison target, and acceptance —
  regenerating the real readiness topology and diffing it against the
  hand-written net — which only the application can own.
- On promotion, the validated vocabulary graduates upstream as a Petrus
  `impetus.dsl` evolution owned by a Petrus story/subthread, following the
  ES-001 lane pattern: accepted Petrus lands first, Hamsterdan re-pins and
  deletes its local copy.

Petrus cannot prove the DSL is good enough; only a real Net can. Exploration
evidence therefore precedes framework contract.

## Prototype evidence — branch `es2/expression-layer`, 2026-08-11

Experiment 1 (combinator layer) is running as additive code only:
`src/hamsterdan/readiness/net/expression.py` plus
`tests/unit/readiness/test_expression_fragment.py`. Production
`topology.py` is untouched and remains the comparison oracle; nothing
imports the prototype. Commits `62250d3` (dashboard/readiness) and
`adda7a1` (all bridges, conversation, retirement family).

Vocabulary so far — three items regenerate every external-effect fragment:

- `activity_bridge` — one typed Activity boundary (request place →
  `execute.<activity>` transition → result place). Covers all 11 bridges,
  including the two actions bridges sharing one result place.
- `authorized_effect` — the full owned-effect fragment ES-001 proved must
  stay explicit: bridge, acceptance against current `Authority` and exact
  operation ownership, pure fold into owner state, retirement of superseded
  results. Covers dashboard, readiness, and conversation (whose extra
  requested-state condition lives in `_effect_matches`, not the combinator).
- `retired_result` — one superseded/stale-result retirement. Covers the
  8-member retirement family, including review's distinct `_review_matches`
  and actions' `_duplicate_actions` predicates as declarative parameters.

The regeneration tests compare 22 transitions and their places/arcs as
frozen schema values (exact structural equality, not counts) and evaluate
lowered guards/handlers of both nets on identical bindings (accepted,
superseded-head, foreign-operation, and conversation not-requested cases).
Full suite stays green: 602 passed.

Findings:

1. Petrus's fluent `>>` arc syntax was never the pain; the pain is the
   repeated guard/handler/binding plumbing and the per-concern repetition of
   the authorize→request→accept/supersede/retire fragment. One combinator
   absorbs `_typed_guard`, `_fold_owned`, operation matching, and retirement
   wiring in a single declaration per concern.
2. The prototype reuses private topology seams (`_effect_matches`,
   `_fold_owned`, `_guard`, `_typed_guard`, `_review_matches`,
   `_duplicate_actions`). A promoted Petrus DSL needs neutral, public
   equivalents of exactly these: typed-binding hydration, typed guards, an
   owned-state fold helper.
3. The combinator normalizes an incidental inconsistency: hand-written
   `accept_conversation` uses the untyped `_guard` where dashboard/readiness
   use `_typed_guard`. Behavioral tests prove the judgments identical —
   regeneration surfaces and absorbs ad-hoc drift rather than copying it.
4. Petrus's position-based anonymous declaration identity makes exact
   schema-level regeneration comparison possible; a promoted DSL must
   preserve it.
5. Concurrent `main` evolution is itself evidence: the experiment merges
   `main` and reruns exact diffs, testing whether the vocabulary absorbs
   real topology change. First merge (RS-013) passed untouched.
6. The honesty test passed by refusing generalization (commit `6b8a672`).
   Mutation acceptance did not fit `authorized_effect` — repair and change
   share one `MutationState` owner, and repair enriches a fingerprint-less
   result from the read `ActionsState` before folding. Forcing those under
   the generic fragment would have hidden workflow decisions behind
   parameters, so they became a distinct `MutationAcceptance` vocabulary
   item whose enrichment read arc is a visible declarative `reads`
   parameter. Grammar shape emerging: a small set of named fragment
   families, not one universal combinator. Coverage: 24 transitions of 69;
   the fingerprint-stamping behavior is proven identical to the
   hand-written net.
7. The authorization family confirmed the grammar shape (commit `bc83fad`).
   `authorize_change`, `authorize_rerun`, `authorize_repair`, and
   `authorize_reply` share one fragment: read current `Authority` plus
   adjacent states, consume the owner and one basis token, reproduce the
   owner alongside a typed work request. The `Authorization` item keeps
   the decision predicate and request-building handler as visible named
   functions — nothing about the workflow decision moved into the
   combinator. Typed-guard normalization again absorbed hand-written
   drift (argument-reordering wrapper lambdas), proven identical by a
   verdict-grid test. Coverage: 28 of 69 transitions across five
   vocabulary items: `activity_bridge`, `authorized_effect`,
   `retired_result`, `MutationAcceptance`, `Authorization`.

8. Intent routing and recovery joined the grammar (commit `35a955c`).
   `FanOut` (unpack_intents; the handler owns routing), `IntentAcceptance`
   (each owner names the intent kinds it may fold), and
   `PublicationRecovery` (per-target replay; recoverability is a
   three-owner decision, so cross-owner read arcs stay explicit).
   `Retirement` generalized to declarative `reads`, absorbing the basis
   retirements alongside the operation family. Coverage: 38 of 69 across
   eight vocabulary items; guard grids prove kind splitting and target
   dispatch identical.

9. Entries and the simple acceptance family (commit `fb0f03e`). `Entry`
   declares the bare typed places where verified external observations
   appear — admission, generation boundaries, human/actions/conversation —
   honestly host-fed, not disguised Activities. `Acceptance` folds one
   result into its owning concern states: read current `Authority`,
   consume the owners plus the result, reproduce the owners with optional
   emissions (actions' basis copy, review's publication request); a
   handler-less acceptance (`accept_reminder`) simply absorbs.
   `retire.actions_basis` confirmed `Retirement(reads=...)` handles
   relational basis completion. Coverage: 51 of 69.

10. Generation lifecycle, admission folds, and marker retirement (commit
    `d0c6cbe`). Four results, coverage 65 of 69:

    - `GenerationBirth` and `GenerationStopRoute` made the concern cohort
      a first-class constant: births (initial, resume, supersede) consume
      a committed start plus an optional prior marker and always emit the
      full nine-state cohort, initial review/actions work, and the
      reminder timer; stops route between markers. The family owns the
      commit-matching plumbing that every hand-written guard repeated;
      admitted-relation sets and per-route predicates stay visible.
    - `refresh_basis`, `refresh_admission`, and `retry_review` are
      `Acceptance` instances whose owner is `Authority` itself: the rule
      "read authority unless folding into it" plus adjacent `reads`
      absorbed all three without a new family. Retry precedence is proven
      by a verdict grid.
    - `Retirement` gained an `anchor`: pre-generation admissions retire
      against the seed/dormant/terminal marker that observed them rather
      than `Authority`, and a `None` predicate expresses terminal's
      unconditional retirement. Retirement's true shape is "against a
      watching state", not "against authority".
    - `PureStep` expresses `rearm` as a pure typed transformation; the
      lowered derived transforms compare equal across both nets.

    Regeneration again surfaced incidental drift: the hand-written net
    leaves `p.terminal` colorless while typing every sibling marker, and
    the birth guards compare one exact relation where the family declares
    an admitted set. Behavioral grids prove all judgments identical.

11. RS-014 absorption (commit `ac54263`). The second `main` merge was the
    first to force vocabulary change: production replaced six binding-style
    acceptance handlers with `@direct` typed folds and deleted the
    `_fold_owned` seam the prototype reused. The families absorbed it as a
    carrier change only — `OwnedEffect` and `MutationAcceptance` now hold
    the direct `HandlerSpec` instead of a fold callable; no fragment shape,
    guard, or arc changed. Handler comparisons became stronger: lowered
    derived transforms compare by their full typed plan (inputs, outputs,
    colors, result type) rather than by synthetic-binding calls. This is
    the open question about surviving the direct-acceptance change without
    application-private binding helpers answered in the affirmative.

12. Snapshot gates and explicit boundaries complete the net (commit
    `20ab9dd`). The Navigator chose Option 2 for the four relational
    snapshot decisions: name only the genuine twins, keep the genuinely
    relational ones verbatim.

    - `SnapshotGate` captures exactly the two semantically identical
      publication gates, `request_dashboard` and `authorize_readiness`:
      read every `COHORT` state except the gate's own owner, consume and
      reproduce the owner, emit one typed work token when the named
      snapshot predicate opens. The reads derive from the first-class
      cohort constant; predicate and handler stay named workflow
      functions.
    - `start_conversation` and `reminder_due` remain verbatim relational
      Petri declarations inside the experimental builder — deliberately.
      Their topology is their meaning: a full-cohort snapshot joined with
      one authorized observation or one armed timer into a single typed
      decision. Forcing them under a universal `reads/consumes/emits`
      combinator would serialize the workflow decision into configuration,
      the exact failure mode the first production refinement rejected.
      This is evidence, not an incomplete abstraction.
    - Coverage: the vocabulary honestly expresses 67 of 69 transitions
      through 14 named fragment families; the compiled experimental net
      regenerates all 69. The decisive whole-net tests assert exact
      equality of every place, transition (including the configurable
      `Delay`), and all 309 arcs — at the default and a non-default
      reminder delay. Behavioral grids prove the gate, conversation, and
      reminder guards judge identically over open/closed snapshots
      (including the dashboard format-upgrade case), and every lowered
      handler compares equal as a derived typed transform.
    - Validation: 24 fragment tests, `scripts/check quick`, and
      `scripts/check full` (608 passed) all green.

    This closes Experiment 1 with the universal-combinator approach
    rejected on concrete evidence: a small grammar of named semantic
    fragment families plus a visible residue of irreducibly relational
    declarations regenerates the production net exactly.

## Value assessment and promotion decision — 2026-08-11

Experiment 1's numbers answer the value question against the prototype:

- `expression.py` is 1,094 lines: ~115 of imports (including ~40 named
  domain guards/handlers that never left `topology.py`), ~540 of family
  machinery (14 dataclasses plus lowering functions), ~440 of declarations
  and builder — the workflow actually written in the vocabulary.
- The fair comparison is those ~440 declaration lines against `build_net`'s
  ~510 hand-wired lines; the other ~1,160 lines of `topology.py` are domain
  functions both versions share. Compression ~510 → ~440, bought with 540
  lines of one-off machinery. For a single net the economics are negative.
- Only 4 of the 14 families are general Petri/Petrus shapes (`Bridge`,
  `PureStep`, `Entry`, roughly `Retirement`). The rest name Hamsterdan's
  domain discipline — authority fencing, operation identity, the concern
  cohort, generation lifecycle. Workflow vocabulary turned out to be domain
  vocabulary.
- The category error the experiment exposed: `expression.py` is not the
  analog of a general effect library (`stateless`); it is the analog of an
  *application written with one*. Petrus's `impetus.dsl` is the general
  layer, and the pain was never `>>` wiring — it was binding plumbing,
  which the two production refinements (RS-014, RS-015) already fixed at
  the right layer.

**Decision: the 14 families are not promoted to Petrus and do not ship in
Hamsterdan production.** `expression.py` remains disposable branch-only
evidence, per its own docstring. `topology.py` stays the production
expression.

What the experiment would promote instead is a small general kernel:

1. Public typed guards and typed binding hydration (today the app-private
   `_typed_guard` / `_hydrate` seams every family reused).
2. A uniform step declaration — one typed function plus an execution
   marker (pure transition vs Motus Activity) lowering to the correct
   fragment. Declaration ergonomics may unify; the net shapes must not:
   an external effect is request/result places plus operation identity,
   fencing, and recovery (ES-001), and collapsing that in the durable
   representation would rebuild the replay world's implicit state.
3. Possibly a first-class named parametrized fragment concept, so any
   application can define its own vocabulary in a page instead of 540
   lines — the general *mechanism*; families stay app-owned.

Ownership: the Petrus kernel lane already carries this work in threads
with the necessary context; ES-002 delegates the kernel items to that lane
rather than opening a new one, and records here what the evidence
supports. Promotion still follows the ES-001 pattern — accepted Petrus
lands first; Hamsterdan re-pins.

## Guard decomposition audit — 2026-08-11

The libpetri-prompted question — how much of the readiness net's guard
content is decidable correlation equality rather than opaque predicate —
was answered by classifying every guard atom across all 69 transitions
(guard inventory extracted mechanically from the built net; predicate
decomposition read from the named guard functions in `topology.py`).

Result: **45 of the 48 guarded transitions decompose completely into
decidable atoms; zero guards are irreducibly opaque as a whole.**

- 21 transitions carry no guard at all: the 7 observation entries, the 11
  Activity bridges, `rearm`, `unpack_intents`, and
  `retire.terminal_admission`.
- 45 of 48 guarded transitions are built entirely from four decidable atom
  kinds:
  1. **Token-pair field equality** (the `MatchSpec` shape, including
     tuple-valued and optional-field-conditional equality): `_current`
     (epoch/head plus conditional base_head/policy_digest), `_subject`,
     `_same`, `_same_basis`, operation identity (`_effect_matches`,
     `_review_matches`), commit/generation matching, observation identity,
     fingerprint equality, and the recovery four-field authority tuple.
  2. **Constant filters** (field vs literal, set membership, flags,
     presence): `authorized`, `blocking`, intent kinds, conclusions,
     stop status, boundary, relation sets, state flags.
  3. **Ordered field comparisons** (linear arithmetic): attempt
     orderings, retry-attempt thresholds.
  4. **Boolean combination including negation** — every `retire.*`
     operation guard is literally the complement of its acceptance
     guard, so declared as data the acceptance/retirement partition
     becomes mechanically checkable for disjointness and totality
     (the experiment's hand-written verdict grids proved exactly this
     pairwise).
- The only semantic residue lives in the 3 projection gates
  (`request_dashboard`, `authorize_readiness`, `reminder_due`), and it is
  exactly **two atoms**: the dashboard projection-digest currency check
  (a sha256 over merged facts compared to the stored projection) and the
  blocking-findings list scan inside `workflow_gates_ready`. Everything
  else inside those three guards is constant filters over merged cohort
  fields plus one `_current` correlation (`reminder_due`'s timer).
  `start_conversation`, despite reading the full cohort, has a fully
  decidable guard — the snapshot feeds its handler, not its guard.

Implication for the Petrus kernel lane: a declared correlation/filter
construct with those four atom kinds would express 94% of this
production net's guard content as analyzable data — directly consumable
by the structural/SMT verification work — leaving named opaque
predicates only where genuine domain computation exists (digest
currency, findings scan). This is the concrete spec the earlier
`MatchSpec` open question asked for; that open question is resolved.

## Typed-guard carrier production evidence — 2026-08-11

The first delegated Petrus kernel slice landed as
`3b41f19aa68ed228e68324f7c6888371f805b560`. Its public
`typed_guard(..., converter=...)` declaration exposes converter-backed typed
guard derivation without adding Pydantic, correlation expressions, routing,
fragments, or application concepts to Petrus.

RS-016 pins that revision and converts eight production guards whose selected
arcs and typed function signatures correspond exactly: admission refresh,
review retry, Actions acceptance, change/rerun/repair/reply authorization, and
Actions-basis retirement. Strict Pydantic hydration now occurs through the
public Petrus typed plan, and Net construction checks each selected typed arc
against the predicate signature.

This is deliberately not a mechanical conversion campaign. Guards that inspect
only a subset of a broad relational binding, arise from heterogeneous dynamic
families, or construct cohort snapshots remain Petri-aware. The production
result establishes the typed carrier needed for future executable correlation
evidence; it does not turn the manual 45/48 decomposition into a theorem or
approve a `MatchSpec` language.

### Lifecycle predicates become explicit without a lifecycle grammar

RS-017 applies that carrier to the six generation boundaries. Initial, resumed,
and superseding births and active, dormant, and seed stops previously embedded
their authority in captured untyped lambdas. They now have named exact typed
predicates, with commit/start and commit/stop matching factored as visible
domain atoms.

This is intentionally not promotion of the experimental `GenerationBirth` or
`GenerationStopRoute` families. The production arcs still show cohort creation
and distinct stop routing; only predicate binding and call-stack naming changed.
It demonstrates that useful correlation atoms can become explicit ordinary
Python rules before—and independently of—any declared correlation language.

## Open questions

- Build-time compilation artifact: what is diffed, versioned, and reviewed —
  generated `NetSpec`, a serialized IR, or both? libpetri's
  `bindActions` separation (pure structural net value, behavior bound by
  name in a later composition step) is prior art for the answer.
- Is generator-based sugar worth its tracing/static-analysis cost over a
  plain builder API, given the Navigator's DX goal?
- From libpetri: which handler-owned routing decisions are static
  XOR/AND output contracts (generation stop routes, intent fan-out) that
  could be declared as data — and how much exact-incidence verification
  coverage would that buy the structural-analysis lane, whose current
  limit is precisely Petrus's variable output effects?

## Sources

- GOTO Book Club, "Effect Oriented Programming" (Frasure, Eckel, Ward,
  interviewer Harmel-Law), episode page:
  <https://gotopia.tech/episodes/420/effective-oriented-programming>;
  book: <https://effectorientedprogramming.com/>.
- `suned/stateless`: <https://github.com/suned/stateless> (v0.6.1, active
  2026; one-shot generator effects, `Effect[A, E, R]` aliases, `handle`,
  `supply`, `run`).
- ZIO `ZIO[R, E, A]` semantics: <https://zio.dev/reference/core/zio/>.
- Effect-TS: <https://effect.website/> (`Effect.gen`, Layers;
  `@effect/workflow` alpha as of 2026-07).
- Temporal Python determinism/versioning:
  <https://docs.temporal.io/develop/python>,
  <https://docs.temporal.io/develop/safe-deployments>.
- DBOS Transact Python step checkpointing:
  <https://docs.dbos.dev/python/tutorials/workflow-tutorial>.
- Restate journaling and immutable deployments:
  <https://docs.restate.dev/foundations/key-concepts>.
- Golem oplog replay and snapshotting:
  <https://learn.golem.cloud/develop/snapshotting>.
- Plotkin & Pretnar, Handlers of Algebraic Effects:
  <https://homepages.inf.ed.ac.uk/gdp/publications/Effect_Handlers.pdf>.
- OCaml 5 one-shot effect handlers: <https://ocaml.org/manual/effects.html>.
- van der Aalst, Application of Petri Nets to Workflow Management:
  <https://www.worldscientific.com/doi/10.1142/S0218126698000043>.
- Dijkman, Dumas & Ouyang, Semantics and Analysis of Business Process Models
  in BPMN: <https://doi.org/10.1016/j.infsof.2008.02.006>.
- Workflow Patterns Initiative: <http://www.workflowpatterns.com/>.
- Jensen, Kristensen & Wells, Coloured Petri Nets and CPN Tools:
  <https://cs.au.dk/fileadmin/site_files/cs/research_areas/centers_and_projects/sttt2007.pdf>;
  CPN Tools superseded by CPN IDE: <https://cpntools.org/>.
- SNAKES (Python high-level Petri nets): <https://github.com/fpom/snakes>.
- XState (machines as inspectable data): <https://stately.ai/docs/xstate>.
- libpetri TypeScript authoring surface, re-read 2026-08-11 at the pinned
  revision `6345140` (transition-centered builder, `one`/`exactly`
  cardinalities, `and`/`xor` output trees, `MatchSpec` decidable
  correlation instead of general guards, `bindActions` topology/behavior
  separation): <https://github.com/debe/libpetri>. Verifier evaluation and
  the no-semantics-import stance are owned by the Impetus structural
  analysis lane.
