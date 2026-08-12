# AX25 — The failure rail: railway-oriented programming as visible sugar

**Status:** complete — Promising; continue (with the scope rule stated
below treated as doctrine, not preference).
**Question:** Composable Functions threads a binary Result — success
track, failure track — through every combinator, making every function
total. Can that railway be authoring *sugar* over the completed AX23
algebra — named failure places, ordinary merges, ordinary routing —
with zero new kernel or algebra concepts, and without collapsing the
typed outcomes AX21 fought for into one undifferentiated error channel?

**Hypothesis:** The rail is a place, not a channel. `attempt` totalizes
a leaf by turning exceptions into wire-safe envelopes on a `failed`
exit; `rail_then` fuses two rails through an ordinary `merge`;
`recover` routes the rail into a total handler and merges back into
the success track. All three expand into structure an author can see
in the serialized net.

## What was built

[ax25_rail.py](ax25_rail.py) — three pieces, built from AX23
primitives alone (`classify`, `then`, `merge`, `rename_exit`), engine
frozen, algebra unmodified:

- `failure_data` — the durable envelope: kind, message, source (the
  block that failed), retryable, cause chain. Every field a JSON
  scalar or nested plain structure. This answers the caveat recorded
  in the Composable Functions comparison: their `SerializableError`
  still carries a live JavaScript `Error` whose useful fields
  evaporate under `JSON.stringify`; a durable failure token cannot
  afford that. Tested by exact round-trip: `json.loads(json.dumps(e))
  == e`.
- `attempt(name, fn, accepts=, returns=, retryable=, pure=)` — their
  `composable()`: the total leaf. `fn` returns → ok exit; `fn` raises
  → envelope on the `failed` exit. Expands to a plain `classify` with
  outcomes `{out: returns, failed: "Failure"}`. The `retryable`
  exception tuple sets the envelope flag where the exception is
  freshest — the AX21 transient/terminal distinction decided at the
  leaf, carried as data.
- `rail_then(a, b)` / `recover(block, handler)` — their `pipe` and
  `catchFailure`. `rail_then` composes on the ok exit and merges the
  two `failed` exits into **one** rail place; a side without a rail
  passes the other side's rail through. `recover` demands a *total*
  handler (exactly one exit) that accepts the `Failure` envelope and
  returns the success track's color — recovery means rejoining the
  track, not inventing a third one.

[test_ax25_rail.py](test_ax25_rail.py), seventeen tests on the frozen
engine: a three-step parse → enrich → store chain where the middle
step raises.

## Findings

- **The rail is sugar, completely.** Zero new kernel concepts, zero
  algebra changes, zero runtime changes. `attempt` is a `classify`;
  `rail_then` is `rename_exit + then + merge`; `recover` is
  `rename_exit + then + merge`. The whole railway is ~60 lines of
  arrangement over existing combinators — exactly what "authoring
  sugar" should mean.
- **One chain, one rail place — structurally.** After
  `rail_then(rail_then(parse, enrich), store)`, exactly one
  `Failure`-colored place exists in the node set (asserted by
  counting, not by convention): AX23's `merge` physically absorbs the
  redundant places. The rail is on-path, inspectable, and satisfies
  `check_sound` — a failure token sitting in it is ordinary marking,
  not a hidden channel. A mid-chain failure leaves the envelope there
  with `source: "enrich"`, and the store step's world is untouched.
- **The scope rule is the finding: the rail carries what nobody
  modeled; classify carries what somebody did.** The sharpest test
  refuses to fuse a *domain* exit named `failed` (color
  `DomainRefusal`) into the rail — colors must both be `Failure` to
  merge, and the error message says where the domain outcome belongs
  (a typed exit, AX21). Without this rule the railway would erase
  exactly the type information the algebra exists to keep: Applied /
  AlreadyApplied / Stale / Exhausted collapse into "error" and the
  downstream net can no longer route on meaning. The binary rail is
  for **unexpected exceptions** — the leftover category — never a
  replacement for typed outcomes.
- **Recovery is composition, not a catch block.** `recover` receives
  the envelope as ordinary token data (the fallback in the test reads
  `envelope["kind"]`), and its admission rules are all composition
  errors with remedies: a handler with two exits is refused ("a
  recovery that can itself fail composes as attempt + recover,
  explicitly"); a handler returning some third color is refused
  ("recovery rejoins the success track"). After recovery the `failed`
  exit is *gone* — consumed by the merge — so an unrecovered rail is
  terminal by construction, visible as an exit the parent must route.
- **Purity propagates through the sugar** (`disposable(rail_then(pure,
  pure))` works), and lowering stays deterministic byte-for-byte.
- **Distinctions kept explicit.** Workflow/domain failure is envelope
  data on the rail; a worker/runtime crash is *not* modeled here (the
  transition never fired — that is the dispatcher's at-least-once
  story, AX21); AX21's typed outcomes stay typed exits. One binary
  rail per net does not lose outcome information *because* the scope
  rule forbids putting outcome information on it.

## Limits

- `retryable` is a flag on the envelope, not a retry loop: composing
  the flag with AX21's bounded transient loop (route retryable
  envelopes back through `loop`, terminal ones onward) is authoring
  work the pieces already support but this spike did not exercise.
- The rail color is one global `"Failure"` by design (so any recover
  handler can serve any upstream); per-domain envelope colors would
  trade that universality for routing on failure kind — deliberately
  not explored.
- `attempt` absorbs `Exception`, not `BaseException` — a worker crash
  mid-handler still surfaces as a dispatcher concern, which is the
  correct boundary but worth restating.

## Verdict

Promising; continue. Railway-oriented failure handling costs nothing —
no kernel, no algebra, no runtime change — and buys totalized leaves
with durable, JSON-clean failure envelopes. Its admission into the
design carries one non-negotiable rule: the rail is for unexpected
exceptions only; typed domain outcomes never ride it.
