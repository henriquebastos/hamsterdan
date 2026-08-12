# Composable Functions — external comparison and what it teaches ES-003

**Source:** <https://github.com/seasonedcc/composable-functions> —
TypeScript, Seasoned (successor to their `domain-functions`), inspected
at repository version 5.0.0 on 2026-08-12 via deep source inspection.
**Why it is here:** the Navigator's intuition that this library
overlaps our investigation. It does — and the overlap is *diagnostic*:
where the two designs independently agree, the ideas are probably
right; where the library stops, our hard problems begin; and where it
has something we lack, the gap is a candidate experiment.

## What it is, in one paragraph

A small, eager, in-process function-composition library. `composable`
wraps any function so it returns `Promise<Result<T>>` where
`Result<T> = Success<T> | Failure{errors: Error[]}` — exceptions are
absorbed into data at every boundary. Combinators (`pipe`, `sequence`,
`all`, `collect`, `map`, `mapErrors`, `catchFailure`, `branch`,
`withContext.*`) compose these wrapped functions, and a type-level
machinery (`CanComposeInSequence`, `CanComposeInParallel`,
`FailToCompose<A, B>`) rejects incompatible wiring **in the IDE,
before anything runs**. There is no graph, no persistence, no replay,
no retry, no loop, no waiting state — a composition executes
immediately and its only state is local variables.

## Independent convergences (the reassuring part)

Both designs arrived separately at the same judgments:

1. **Errors are data, not control flow.** Their every function returns
   `Success | Failure`; our AX21 made effect outcomes typed places
   (`Applied | AlreadyApplied | Stale | Transient`) and AX22 made
   `classify` the leaf that returns outcomes instead of throwing.
   Ours is the finer instrument: n-ary, domain-typed outcomes instead
   of a binary success/failure — their `branch` resolver returning a
   union of next functions is the closest they get to our typed exits.
2. **Composition is checked before execution, and the error names both
   sides.** Their `FailToCompose<A, B>` carries the two mismatched
   types into the compiler message; our `CompositionError` names both
   blocks, both ports, and both colors at authoring time. Same
   doctrine, different phase (their static typing vs our
   authoring-runtime) — see candidate AX26 below.
3. **Ambient state is a separate channel, not part of the data flow.**
   Their `withContext` threads a second argument to every step without
   it ever becoming a step's output; our AX23 context ports declare
   read and held places outside the entry→exit flow. Ours answers what
   theirs cannot: durability, visibility in the net, and mutual
   exclusion (`holding`).
4. **Merge-by-override is a hazard.** They *removed* their `merge`
   combinator because it "was not a total function" and later keys
   silently overrode earlier ones. Our `merge` requires explicitly
   named same-colored exits and refuses double-produce — the same
   lesson, enforced rather than retreated from.
5. **Race over effects is dangerous.** They removed `first` (run all,
   return first success) because losing branches' side effects still
   happen. Our purity discipline says exactly when a race *would* be
   admissible: only over `disposable` interiors. Their removal is our
   admission rule.
6. **Validate at boundaries, once.** Their `applySchema` is
   recommended only at untrusted edges, one validation per chain — the
   AX16 posture (validation over absorption) and the AX20 boundary
   discipline.

## What the library has that our algebra lacks

1. **Totality.** A `Composable` *always* returns exactly one `Result`
   — success or failure, never an unhandled exception, never nothing.
   Our blocks have named typed exits, but nothing forces a leaf to
   route every possible outcome somewhere: a Petri handler that throws
   today is an engine concern, not a declared exit. Their totality is
   what makes their combinators lawful; ours would make AND-joins
   sound (see below).
2. **A parallel combinator.** `all` (positional) and `collect` (named
   record) run branches concurrently and — the sharp part — **always
   let every branch finish, then aggregate all failures** rather than
   collapsing to the first. Our completed algebra (AX22/AX23) has
   `then`, `rename_exit`, `merge`, `loop`, `holding`, `disposable` —
   **no parallel split/join at all**. AND-parallelism exists only back
   in AX4's earlier AST, outside the block algebra. This is the one
   genuinely open structural gap the comparison exposes.
3. **The join-over-results insight.** In a Petri net an AND-join
   waits for one token per branch; if a branch fails into a failure
   place instead, the join dangles forever. Their design dissolves the
   problem: because every branch is total, the join never waits on a
   token that cannot come — it joins *Results*, then classifies the
   aggregate. Totalized branches are what make an AND-join sound in
   the presence of failure.
4. **IDE-phase wiring errors.** Their type machinery rejects a bad
   `pipe` while the author is typing. Our color checks fire when the
   composition expression *runs* (still before lowering, but after
   authoring). Python generics + a strict type checker might close
   part of that phase gap.
5. **`sequence` vs `pipe` as a data-retention distinction.** Same
   execution, different result shape: `sequence` keeps every
   intermediate output, `pipe` only the last. We currently always
   discard intermediates unless a transform carries them forward by
   hand. A cheap, worthwhile distinction to name in the authoring
   layer rather than solve ad hoc.

## What we have that the library cannot express

Durability, replay, event sourcing, suspension and timers, operation
identity and idempotency (AX21), structural mutual exclusion (AX20/
AX23 `holding`), loops with data-driven bounds, an inspectable
compiled artifact, and source mapping from authoring to runtime. Their
compositions are opaque closures — precisely the fate our AST-first
rule (AX1) and kernel lowering (AX18/AX19) were designed to avoid.
The library is a *phase-one* system (compose and run now); ours is a
*two-phase* system (compose a value, lower it, run it durably). The
lesson is not to adopt their execution model but to steal what
survives the phase change: totality, failure algebra, join policy,
context channel typing.

## Serialization caveat worth remembering

Their `SerializableError` still carries a live `exception: Error`
object; only `message`/`name`/`path` survive JSON. A durable failure
token needs a deliberately wire-safe envelope — stable kind
identifiers, cause chain as data, retryability — designed once, not
inherited from an exception object. Directly relevant to what AX21
outcome tokens should carry.

## Candidate experiments raised by this comparison

- **AX24 — Parallel in the block algebra (split, total branches,
  join policies).** Add an AND-split/join combinator to the completed
  algebra where every branch is *total* (always emits exactly one
  token, success- or failure-colored), so the join is sound by
  construction. Make the join policy explicit and visible in the net:
  `all` (wait for every branch, aggregate failures — their only
  policy), `fail_fast` (first failure wins, remaining tokens routed
  to a declared drain — never cancelled invisibly), and quorum as a
  possible third. Test the AX4 hazards again at this level: one branch
  fails, duplicate tokens, cross-instance mixing.
- **AX25 — The failure rail: uniform failure exits as sugar, not
  semantics.** Their binary `Result` is railway-oriented programming;
  ours refuses hidden topology. Test whether a standard `failed` exit
  convention (every leaf gets one; `then` auto-propagates it by fusing
  failure exits into a declared rail) can be *authoring sugar that
  expands into visible net structure* — named places, inspectable,
  mergeable — without becoming an invisible second channel. Includes
  the wire-safe failure-token envelope.
- **AX26 — Phase-shifting composition errors into the type checker.**
  Probe how far Python's typing (generic `Block[EntryColor, ExitMap]`,
  `Literal` port names, pyright strict) can reject a bad `then`/
  `merge` at edit time, keeping the authoring-runtime
  `CompositionError` as the authoritative check. Their `FailToCompose`
  is the existence proof that edge-local, both-sides-named diagnostics
  are achievable in a structural type system; the experiment measures
  how much of that Python can honestly deliver.

Not proposed: adopting their eager execution, closure-threaded
context, or binary result type — each dissolves under the two-phase
requirement stated above.

## Verdict

The Navigator's intuition was right, and specifically right: the
library independently validates five doctrines we reached by
experiment (errors as data, checked wiring, separate context channel,
explicit merge, race-needs-purity) and exposes one true structural gap
in the completed algebra — **no parallel combinator, and with it the
totality + join-policy question**. That is the highest-value next
experiment; the failure rail and typing phase-shift follow from it.
