# AX2 — The V2 case net: the meta cell

**Question.** Can PR lifecycle + epoch management — everything the
tower removed from the work net — fit one small net where killing an
instance is an ordinary activity? What does the coordination actually
cost?

**Method.** Same rules as AX1: greenfield from the ch. 17 contract,
shipped DSL, production topology unopened. All claims asserted by
[test_ax2_case_net.py](test_ax2_case_net.py) — 8 tests, all passing
against the built nets.

## Design facts that shaped the net

1. **Ingress is an observation, not an action.** The contract says
   live PR state is read on every webhook. So ingress classifies
   *statelessly* into `ObservedOpen(head)` / `ObservedDraft` /
   `ObservedClosed` — no case state needed at admission, no guards or
   CEL filters needed for routing.
2. **Birth is the initial marking.** Host admission seeds the state
   token (and a spawn request when active). A birth *transition*
   would compete with reconciliation for observation tokens; a birth
   *marking* can't. (Covers born-draft cases for free: seed
   `dormant`, no spawn.)
3. **Head comparison is data.** `head_check` always returns `active`;
   its pure handler emits `abandon_request` + `spawn_request`
   (epoch+1) only when the observed head differs. Cross-token
   comparisons live in handlers, not arc filters.
4. **Spawn and abandon are ordinary pipelines** — same linear shape
   as AX1's work-net pipelines. `synthesize_seed` reads the dead
   instance's ledger and produces the typed birth payload (the union
   of the concerns' `resume()` outputs — the God-token guard).

## The grid variant — the state machine IS the topology

```text
                 observed_open        observed_draft       observed_closed
   active   ──▶  head_check           suspend              close
                 → active             → dormant            → terminal
                 (+abandon+spawn        (+abandon)           (+abandon)
                  when head moved)
   dormant  ──▶  resume               note_draft           close_dormant
                 → active (+spawn,    → dormant            → terminal
                   epoch = last+1)
   terminal      (absorbing — admission drops provably-closed ingress)
```

Every lifecycle transition consumes exactly one live state token and
returns exactly one — the `holding` pattern; state is never read,
only held. An observation place feeds up to three transitions, and
that competition is disambiguated purely by which state token exists.

## Measured shape

| variant | P | T | A | arcs/(P+T) | read | filters | guards | cycles |
|---|---|---|---|---|---|---|---|---|
| grid (state × observation) | 13 | 9 | 31 | **1.409** | 0 | 0 | 0 | state-confined |
| reconcile (1 transition/state) | 11 | 5 | 21 | **1.312** | 0 | 0 | 0 | state-confined |
| AX1 work net (for contrast) | 22–59 | 8–21 | 25–68 | **0.83–0.85** | 0 | 0 | 0 | none |

Asserted structural facts:

1. **Coordination pays in arc density, never in constructs.** Both
   variants exceed ratio 1 — and still use zero read arcs, zero
   filters, zero guards, zero inhibitors.
2. **Cyclicity is confined to the state cell.** Deleting the three
   state places makes the whole net acyclic; effect pipelines never
   touch state.
3. **Terminal is absorbing** — no transition consumes it.

## The two-idiom finding

Across AX1 + AX2, the entire V2 system uses exactly **two net
idioms**:

```text
PIPELINE    entry ─▶ effect steps ─▶ typed settled exits
            acyclic · fan-in nowhere · ratio < 1 · does the work
STATE CELL  state places + (state, fact) transitions returning state
            cyclic · fan-in exactly 2 · ratio > 1 · routes the work
```

The old intuition "many arcs per node = state spread" refines to:
ratio < 1 is the signature of *work*, ratio > 1 is the signature of
*coordination* — and health means confining the second to one small
net (25 nodes here) instead of braiding it through the domain.

## Grid vs reconcile (Navigator decision surfaced)

Same trade as AX1's explicit/collapsed, now for control: the grid
puts the state-machine *table* in topology (History names `suspend`,
`resume`, `close`; dead observations visible per cell); reconcile
puts rows into two pure handlers (smallest net, but History only says
`reconcile_active` and routing hides in code). ES-004 AX6 proved the
pure-`step()` handler works; the grid is its topology-readable dual.
Both are guard-free. Not ruled here; AX4 carries both.

## Residues honestly held (not modeled in shape)

- Ingress targeting terminal cases: acknowledged and dropped at
  admission (control layer), quarantined when uncertain.
- Late completions from killed instances: absorbed by the dead
  instance's own history (AX5 probes this).
- Timer ownership across instances (reminder armed in epoch N,
  maturing in N+2): open product choice, deliberately unmodeled.
- Instance GC / churn economics: operational, outside shape.

## Verdict

**Promising; continue.** Everything the tower removed from the work
net fits in a 22-node net with zero guards, zero filters, zero read
arcs — and the whole V2 system needs exactly two idioms: acyclic
pipelines that work, and one cyclic state cell that routes.
