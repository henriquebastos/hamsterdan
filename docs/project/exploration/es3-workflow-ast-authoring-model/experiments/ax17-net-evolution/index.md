# AX17 — Net evolution: one durable history across two compositions

- State: Completed, 2026-08-12.
- Question: when is `Instance.resume(net', history)` sound for a net'
  that is not the net the history was recorded under? This is the
  adoption path for fragment composition — adding (or removing) a
  concern on a **live instance** — and a generic question about any
  compiled net on this runtime, not this workflow.
- Verdict: **Promising; continue** — adding a composed concern to a
  live instance is a **zero-migration** operation: same name, superset
  structure, one ordinary `Engine.load`, no history rewriting. The
  frozen resume door's live-state-only audit yields five generic rules
  (below), including one designed-in gap — ended firings of removed
  transitions resume silently under a narrowed net — and one structural
  payoff: minimal guard scope (AX15's per-target specialization) is
  what decides how much of a new concern works on day one.
- Spike: [`ax17_evolution.py`](ax17_evolution.py) (two same-name
  compositions of the untouched committed fragments; the only authored
  delta between process versions is one argument to `compose`),
  [`test_ax17_evolution.py`](test_ax17_evolution.py) — 8 tests,
  [`conftest.py`](conftest.py) (sys.path bridge). No shared-module or
  production changes.

## The five rules (generic: any net on this runtime)

1. **The net name is the process identity.** `InstanceCreated` records
   it; resume under any other name is refused as a foreign trace —
   proven with a structurally identical net renamed `-v2`. Version
   therefore cannot live in the name: two structures answering to one
   name *is* the evolution mechanism, and version identity must live
   elsewhere (NetUri, definition metadata).
2. **Superset resume is total.** Every narrow-net place replays to the
   identical marking; the added concern's places arrive empty. Nothing
   about the old history is rewritten, migrated, or re-recorded.
3. **A parked hand-off token is deferred capability.** Under the narrow
   net the scatter parks a `recover_publication` intent on
   `recovery_basis` — a place with *no consumer*. After evolution, one
   `drive` lets the added concern consume the token that parked before
   the concern existed: WAIT semantics + composition means work can
   arrive before the code that handles it, durably.
4. **An unseeded state place starves the joined concern — visibly.** A
   dashboard-target recovery intent stays parked forever after
   evolution: the dashboard case needs a `DashboardPublicationState`
   token no pre-evolution marking seeded, and the generated `otherwise`
   retire reads *all* the concern's states, so it starves too. The
   token sits on `recovery_basis` as an observable diagnosis, not a
   silent loss. Corollary: a concern is evolution-safe exactly to the
   extent that its transitions bind only pre-existing places —
   `recover_conversation`'s inputs are a subset of the narrow net's
   places (proven by inclusion), `recover_dashboard`'s are not. AX15's
   per-target predicate specialization is therefore not just fewer
   arcs; it is what made the first recovery target work on day one with
   zero seeding. A concern that must be fully live at join time needs
   an initialization path for its state (a source/delivery, or joining
   at instance creation).
5. **Narrowing audits live state only.** Live tokens on removed places
   refuse the narrow net loudly. But a history containing **ended**
   firings of a removed transition resumes **silently** when all live
   state lands on surviving nodes — proven by firing
   `recover_conversation` under the full net (dp/rp never seeded) and
   resuming under the narrow net. This is Petrus's documented posture
   (whole-trace auditing is a validation-layer concern, kernel debt
   2026-07-09T2310Z), so concern *removal* needs a deliberate
   compatibility check above the resume door; the door will not supply
   it.

## What this settles for the authoring model

- Fragment composition has a real, tested adoption story: concerns can
  ship to live instances by recomposing under the same name. The
  compiler's determinism (AX14) plus rule 2 is the whole mechanism.
- The compatibility check for narrowing (and, honestly, for any
  recomposition) belongs in the authoring layer: compare the old and
  new `NetDefinitionV3` projections against the recorded live state
  before loading — a compiler-side preflight, not a runtime change.
- Guard scope minimality is promoted from an economy finding (AX15) to
  a compatibility property: the DSL should keep deriving the smallest
  binding scope from predicate roots, because it directly widens what
  survives evolution.

## Open edge, deliberately not explored here

In-flight occurrences across evolution (an activity begun under the
narrow net, resumed under the full one) — the resume door re-validates
binding shapes against the new net's arcs, and no experiment scenario
left an occurrence in flight across the seam. Worth a dedicated
variation if activity-heavy fragments become the norm.
