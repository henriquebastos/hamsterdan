# Petrus speculation ledger

Potential Petrus runtime changes suggested by ES-003 authoring-model
experiments. Petrus stays frozen at
`3b41f19aa68ed228e68324f7c6888371f805b560` throughout the series; entries
here are analysis outputs for possible future Petrus-lane work, each tied to
the experiment evidence that motivated it. Nothing here is a commitment, and
no experiment may depend on a speculated change.

Ruling (Navigator, 2026-08-11): Petrus is considered frozen for the
experiments, but speculation about runtime changes is welcome as a dependent
result of the explorations.

## Entries

### SP-1 — Bind real types instead of nominal color strings

- Raised by: Navigator, 2026-08-11 (series setup).
- Today: `type Color = str`; the authoring DSL accepts a Python class but
  stores only `cls.__name__`. No registry maps colors back to classes;
  replay yields generic `Token(color, data)` and hydration is the
  application converter's job. Arc admission is nominal string equality
  (`Arc.admits`), so subclassing, unions, and generics are invisible to
  the runtime.
- Speculation: places/arcs could carry type objects (or a color registry)
  so admission, hydration, and validation share one authority; subtype and
  union admission would become runtime semantics instead of authoring-layer
  convention.
- Watch in: AX3 (inference over annotations), AX5 (union/subtype routing),
  AX7 (type + guard hybrid). These experiments will show precisely where
  nominal string identity forces the authoring layer to compensate.
- Constraints any proposal must respect: the net definition stays
  language-neutral and serializable (`NetDefinitionV3` carries portable
  names, never implementation objects); history replay must not require
  importable domain classes.
- AX3 evidence (2026-08-11): nominal identity held up better than
  expected for inputs — the typed derivation already refuses same-color
  fan-in loudly, and place-bound ports resolve it entirely above the
  runtime. The genuine nominal-string casualties observed: unions have
  no color (`Approved | Rejected` must be exploded by the compiler,
  AX5), and generics erase (`list[Decision]` → `"list"`), forcing
  wrapper dataclasses.
- AX5 evidence (2026-08-11): unions confirmed as the sharpest casualty.
  Variant identity does not survive the Motus worker boundary at all —
  `DataclassPayloadConverter.encode` on a union annotation falls to raw
  JSON encoding and raises. The authoring layer must both explode the
  union into typed arcs *and* stamp a `$variant` discriminator into the
  frozen result via a custom converter. Subclass routing is
  unrepresentable under nominal colors (refused loudly at the worker
  boundary instead). Real type binding would make subtype admission a
  runtime semantic; today it simply does not exist.

### SP-2 — First-class sinks (no-output activities)

- Raised by: AX3 probe, 2026-08-11.
- Today: `DerivedActivityHandler` requires the result annotation to match
  at least one output arc color, so `-> None` activities fail derivation
  (`return type NoneType matches no output arc`). A place explicitly
  colored `"NoneType"` satisfies it mechanically — workable but it leaks
  a Python spelling into the language-neutral net and creates a
  token-per-completion place the author never wanted.
- Speculation: either the derivation layer accepts a declared "no
  projection" sink, or a canonical completion color exists. Until then
  the AX compiler can emit the `NoneType` completion place and hide the
  ugliness above the runtime.
- Watch in: AX4 (join branches whose sides produce nothing), AX8
  (retry exits), AX11 (real fragment).
- AX4 evidence (2026-08-11): a `-> None` branch works as a terminal
  side-effect branch (the compiler emits the `NoneType` exit place and
  the workflow ends with multiple exits) but can never feed a join —
  no activity parameter can consume `NoneType`, so the shape is
  rejected at lowering. A canonical completion color would make such
  branches joinable; today they are compile-time errors.

### SP-3 — Case correlation at generated joins

- Raised by: AX4 proof, 2026-08-11.
- Today: a compiled AND-join is an ordinary multi-input transition;
  place FIFO pairs whatever tokens arrive first. AX4 seeded two cases
  into one Engine instance and crossed the completion order: the join
  paired one case's Reservation with the other case's TaxQuote. Neither
  nominal colors nor topology carry case identity.
- Speculation: none needed at the runtime layer for Hamsterdan — the
  production discipline is one Engine instance per PR, which removes
  the hazard structurally. If multi-case instances ever matter, the
  existing `SelectionPolicy` seam (a public Engine extension point)
  could filter candidate bindings by a correlation key the compiler
  stamps into token data; that is above-runtime work, not a Petrus
  change.
- Watch in: AX8 (loop iterations create repeated tokens in one case —
  the same pairing question intra-case), AX11 (real fragment).

### SP-4 — Opt-in strict output routing

- Raised by: AX5 native-routing probes, 2026-08-11.
- Today: `route` (pure handlers) and `complete_firing` (activity
  projections) deposit each produced token on every output arc that
  admits it and **silently drop** tokens no arc admits. AX5 proved both
  behaviors with mini-nets: a `"Mystery"` token fires the transition and
  vanishes without error or parking; a token admitted by a typed and an
  untyped arc duplicates onto both targets.
- Consequence for authoring layers: exhaustiveness must be guaranteed at
  compile time and every projection must fail loudly before the drop can
  occur — the AX5 spike does both, but nothing protects hand-written
  nets or future compilers from the same footgun.
- Speculation: an opt-in per-net or per-transition strict mode where a
  produced token admitted by no output arc fails the firing instead of
  dropping. Silent drop stays the compatible default (some nets use it
  deliberately as filtering); strict mode turns exhaustiveness bugs into
  loud faults at the exact firing that produced the orphan.
- Watch in: AX7 (guards narrow admission further — more drop surface),
  AX11 (real fragment).
- AX6 evidence (2026-08-11): the input side has the mirror behavior —
  a token admitted by no filtered input arc **parks** in its place,
  silently when every filter evaluates cleanly to false, with a
  `FilterEvaluationWarning` only when a filter raises. Parking is
  recoverable (the token stays visible in the marking) but produces no
  fault or diagnostic in the clean-false case. Any strict-mode design
  should consider both surfaces: unroutable-produced (drop) and
  unadmittable-parked (stall). The AX6 combinator closes the stall
  authoring-side with a mandatory `otherwise` compiled to the
  conjunction of all case negations.

### SP-5 — Durable timers and delays

- Raised by: AX8 loop/retry spike, 2026-08-11.
- Today: no timer, delay, deadline, or scheduling primitive exists
  anywhere in the frozen Petrus package (verified by case-insensitive
  search across the pinned checkout). "Wait, then retry" — the canonical
  retry-with-backoff shape — is representable only as a worker-side
  sleep inside an activity (blocking a worker, invisible to the net) or
  as external driving-policy pacing (invisible to history).
- Consequence for authoring layers: AX8's `retry` combinator expresses
  bounded re-attempts durably (counter in token data, guard in CEL) but
  cannot express *when* the next attempt may fire. Any backoff policy
  would today be smuggled into an activity's implementation.
- Speculation: a durable timer as a first-class enabledness input — for
  example an arc or transition inscription "not before T", with T a
  durable fact and firing eligibility re-evaluated by the driving loop.
  The event-sourced shape suggests recording a timer-set fact and
  treating expiry as an external completion, like activity completion by
  occurrence ID.
- Watch in: AX11 (the real fragment has operational recovery flows where
  pacing matters).

### SP-6 — Heartbeat details as the de-facto durable checkpoint channel

- Raised by: AX9 effect-authoring spike, 2026-08-12.
- Today: the only durable, per-occurrence, cross-attempt state a worker
  can write mid-activity is the heartbeat details slot.
  `LocalWorkerDispatch.claim` hands the previous attempt's persisted
  details to the successor — AX9 proved a journaled effect interpreter
  resumes a crashed activity mid-program on the frozen runtime with no
  Petrus change.
- Load-bearing constraints found: one exclusive slot per occurrence (an
  effect journal collides with any other details use), a 65,536-byte
  encoded cap (long programs with fat results will not fit), and
  `InlineDispatch` resetting `latest_details=None` per inline retry
  (journal resume is real only under persistent providers). Also,
  `DerivedActivityHandler.prepare` hard-codes the default
  `ExecutionPolicy()` (attempts=1), so multi-attempt resume cannot be
  reached from a net-bound activity without policy plumbing.
- Speculation: if effect-style activities become common, Petrus could
  offer (a) per-activity `ExecutionPolicy` on the binding/declaration
  surface, and (b) a first-class named checkpoint channel (or size-
  accounted journal) distinct from liveness heartbeats, so progress
  reporting and checkpointing stop competing for one slot.
- Watch in: AX11/AX12 (whether the recommendation admits effect
  activities at all determines this entry's weight).
- AX12 outcome (2026-08-12): the recommendation admits effect activities
  as an optional authoring convenience inside activities only
  (Interpretation A) — never as workflow structure. This entry therefore
  keeps moderate weight: it becomes relevant only if effect-style
  activities are actually adopted, and the policy-plumbing gap
  (`DerivedActivityHandler`'s hard-coded `ExecutionPolicy()`) is the
  part that gates any real use.
