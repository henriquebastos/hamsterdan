# AX2 — Linearizing review production as an ES-003 block chain

## Question

Can the AX1 review-production contract — a mostly pure/disposable
concern ending at the comment gate — be expressed as one linear ES-003
block chain, with the shared exit vocabulary appearing as real typed
exits and both idempotency kinds observable in behavior?

Spike: [ax2-linear-review/](ax2-linear-review/) — reuses ES-003 AX23
blocks + AX25 rail **unchanged** (no new primitives), 8 focused tests,
all passing; the combined exploration suite stays green (435).

## The authoring code

```python
def review_subnet(world) -> Block:
    interior = rail_then(rail_then(prepare_basis(), run_agent(world)), draft_publication())
    fenced   = then(interior, fence_authority(), on="out")
    return then(fenced, publish_findings(world), on="current")
```

Five leaves in AX1-contract order: `prepare_basis` (pure) →
`run_agent` (disposable effect, retryable `AgentOutage`) →
`draft_publication` (pure) → `fence_authority` (`classify` with
`reads=(("authority", "Authority"),)` — the AX20 fence as data-driven
classification) → `publish_findings` (comment gate: lookup-first by
`(kind, operation, head)`).

## The compiled net

```diagram
ReviewRequest        Authority (context, read arc)
     │                    ┆
     ▼                    ┆
[prepare_basis]──────┐    ┆
     ▼               │    ┆
[run_agent]────────┐ │    ┆
     ▼             │ │    ┆
[draft_publication]│ │    ┆
     ▼             ▼ ▼    ┆
[fence_authority]◀┄┄┄┄┄┄┄┄┘     failed (Failure rail,
     │        │                  one merged place)
     │        └────▶ stale (StaleAuthority)
     ▼
[publish_findings]
     │        └────▶ blocked (RecoverableFault)
     ▼
acknowledged (FindingPublicationResult)
```

Measured: **10 places, 5 transitions, 16 arcs — 1.07 arcs per node.**
Every transition consumes exactly one token (asserted in tests); the
only extra arcs are the declared context read and the exit fan. The
Navigator's linearity hunch ("arcs ≈ half of total nodes in a simple
net" — i.e., no combinatorial wiring) holds: fan-in exists nowhere,
and the two rails from `prepare`/`run_agent` merge into **one**
visible failure place via an ordinary AX23 `merge`.

## Exits = the AX1 vocabulary, exactly

```python
assert set(block.exits) == {"acknowledged", "stale", "failed", "blocked"}
# acknowledged : FindingPublicationResult   (completed)
# stale        : StaleAuthority             (discarded)
# failed       : Failure envelope           (retryable — rail)
# blocked      : RecoverableFault           (awaits recover_publication)
```

No exit had to be invented and none was left over — the contract
vocabulary and the algebra's exit model are the same shape.

## Behavior evidence (all from executed tests)

```text
happy path      → acknowledged {comment_id: 1, reused: False};
                  world: 1 agent run, 1 comment
stale authority → the agent ran (money spent), fence caught the moved
                  head, exit stale {basis: [3,h2,b1], authority:
                  [4,h3,b1]}, world.comments == [] — work discarded
                  BEFORE the gate, exactly the discard doctrine
kind-1 idem.    → pre-existing marker (finding, op-review-3, h2) →
                  acknowledged {comment_id: 7, reused: True}, no dup
kind-2 shape    → github down → classified exit blocked {kind:
                  capability, retryable: true} — an exit, not an
                  exception
agent outage    → rail envelope {kind: AgentOutage, source:
                  run_agent, retryable: true}; nothing published
```

## The shaped gap: `pure` cannot say "disposable effect"

AX1's taxonomy has four effect classes; the ES-003 algebra has two:

```text
AX1:  pure | read-only effect | DISPOSABLE EFFECT | gate (committed)
AX23: pure | effectful
```

So `disposable(prepare >> run_agent)` is refused (`CompositionError:
… not pure`) even though the interior mutates nothing observable —
the agent call only *spends*. Captured in a test, not patched. The
fix direction (for a later experiment, not here): purity becomes a
three-valued effect grade — `pure < spendable < committing` — with
`disposable` admitting everything below `committing`. That grade is
also exactly what the two-gate finding needs: gates are the only
`committing` leaves.

## What stayed explicit vs inferred

```text
explicit: exit names, colors, the authority context (declared read),
          the operation identity in the request, the lookup marker
inferred: nothing — no type-based place matching, no hidden merge
ambiguous: nothing observed at this scale
```

## Conclusion

**Promising; continue.** The contract → chain translation was
mechanical: every AX1 clause landed on exactly one existing primitive,
the compiled net is measurably linear (1.07 arcs/node), and the
discard-before-gate story is directly observable in the marking. One
shaped gap recorded (the `spendable` effect grade). AX3 should now
attach the *hard* fencing semantics — shape M's git gate, where
kind-2 idempotency (CAS loss → `discarded`, collision → `fault`) and
provisional authority live.
