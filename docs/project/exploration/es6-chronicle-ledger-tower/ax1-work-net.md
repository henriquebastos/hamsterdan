# AX1 — The V2 work net: the domain under one fixed authority

**Question.** If the work net exists for exactly one authority (one
epoch, one head) and is abandoned wholesale when authority moves —
how simple does Hamsterdan's domain topology get?

**Method.** Greenfield from the ES-005
[chapter 17 contract](../es5-design-primer/17-hamsterdan-rebuild-brief.md);
production `topology.py` not opened (quarantine rule). Shipped spec
DSL only. Every claim below is asserted by
[test_ax1_work_net.py](test_ax1_work_net.py) against the built net —
9 tests, all passing.

## What the net contains — and what it doesn't

The topology holds **only the effect pipelines**. Admission, the
per-concern folds over settled exits, and `decide(snapshot)` are pure
control-layer functions (chapter 17's target shape); `decide` seeds
entry places with identity-carrying work tokens. Pure computations
(failure classification, dashboard rendering) are `decide`'s
business, not transitions — only *effects* earn a transition.

Three shapes cover all eleven concerns:

```text
review    head ─▶ agent ─▶ output ─▶ validate ─▶ findings | discarded
observe   run ─▶ assess ─▶ assessed | fault
gate      request ─▶ attempt ─▶ done | gone(discarded) | fault        (rerun)
shape M   request ─▶ agent ─▶ output ─▶ validate ─▶ valid | discarded
          valid ─▶ commit[git CAS] ─▶ committed | moved(discarded) | fault
                                                     (repair · change ·
                                                      update_base ·
                                                      resolve_conflict)
shape P   request ─▶ publish[comment gate] ─▶ published | blocked | fault
                                                     (dashboard · findings ·
                                                      reply · reminder ·
                                                      readiness)
```

The whole net is authored by **three shape functions and two
for-loops** (~40 source lines for 80 nodes). `moved` and `gone` are
outcomes colored `Discarded` — "preconditions changed" is a normal
exit, never an error (attempt-first doctrine, ES-004 AX1/AX3).

## Measured shape

| variant | P | T | A | arcs/(P+T) | read | inhibit | filters | guards | fragments | cycles |
|---|---|---|---|---|---|---|---|---|---|---|
| explicit (kind = topology) | 59 | 21 | 68 | **0.850** | **0** | 0 | **0** | **0** | 12 | 0 |
| collapsed (kind = data) | 22 | 8 | 25 | **0.833** | **0** | 0 | **0** | **0** | 5 | 0 |

Structural facts asserted, both variants:

1. **Fan-in nowhere.** Every transition has exactly one input arc.
   Joins live in the fold, not the net.
2. **No place-level choice.** Every place feeds at most one
   transition. All branching is typed fan-out at transitions — the
   handler's outcome type selects the exit.
3. **Acyclic.** Zero loops. Iteration is provider-owned (GitHub
   run/attempt data) and "the next iteration" is the next generation
   arriving at the meta net.
4. **Staleness unexpressible.** No node even *names* epoch, stale,
   drain, dormant, fence, seed, or in-flight — asserted lexically.

## The explicit/collapsed tension (Navigator decision surfaced)

The four mutation kinds and five publication kinds have *identical
shapes*. Kind can be topology (a scope each: 12 fragments, 80 nodes,
place names like `publish.readiness.blocked` appear in History) or
data (5 fragments, 30 nodes, kind lives in the token and History
shows `publish.blocked` for everything).

This is the ES-003 named-ports lesson at net scale: **types define
compatibility; names resolve identity**. The trade is pure
observability-vs-size — behavior is identical. A middle course
exists (collapse mutations, keep publications explicit, or vice
versa). Not ruled here; AX4 carries both variants into the
comparison.

## Construct census (feeds the primitive re-derivation, AX4)

The work net needed exactly: typed places, handler transitions,
consume arcs, colored fan-out exits, scopes for naming. It did
**not** need: read arcs, inhibit arcs, CEL filters, guards, weights,
timers, multi-input transitions, or cycles.

## What this experiment does not show

- Whether lifecycle/epoch machinery really fits one small meta net —
  that's AX2, and its cost must be counted before celebrating.
- Runtime behavior (dispatch, replay) — this is a shape experiment;
  handlers are symbolic strings.
- Whether one net *instance* per epoch is operationally acceptable
  (instance churn, GC) — meta-layer residue, AX2/AX5.

## Verdict

**Promising; continue.** The domain under one fixed authority is
eleven isolated linear pipelines built from three shapes — zero read
arcs against production's 94 (ES-004 AX5 count; precise side-by-side
in AX4), zero guards, zero filters, zero cycles, no fan-in. The
braid was never domain complexity.
