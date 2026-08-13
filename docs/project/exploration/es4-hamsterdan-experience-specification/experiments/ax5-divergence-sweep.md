# AX5 — The divergence sweep: 94 read arcs, classified

## Question

The exploration's capstone, planned since AX0: where does the
independent model (AX1–AX4, AX6, AX7) diverge from production's
`readiness/net/topology.py`, and is each divergence **ACCIDENTAL**
complexity, a **MISSED** requirement, or an **OPEN** choice? And is
the Navigator's hunch — "Hamsterdan is too complex for what it should
be" — measurable?

Spike: [ax5-divergence-sweep/](ax5-divergence-sweep/) — 5 tests, all
passing. The sweep is executable: every number below is derived from
`build_net()` and asserted, and the category inventory is proven
complete (every read arc belongs to exactly one category; populations
pinned). The document cannot drift from the net.

## The production shape, measured

```text
                      production net        measured spike fragments
                      (build_net())         AX2 review     AX4 composed
places                46                    10             12
transitions           69                    5              5
arcs                  309                   16             17
reads among them      94  (30%)             1 (the fence   0
                                             AX3 retired)
arcs/(P+T)            2.69                  1.07           ~1.1
ambient state places  9-12                  0-1            0
```

`authority` alone: degree 46, read by 37 arcs across more than half of
all transitions — a global hub. The next five hubs are the other
cohort places (`mutation_state` 20, `review_state` 19,
`conversation_publication_state` 19, `dashboard_publication_state` 18,
`readiness_publication_state` 18). This is the "spreaded net" made
countable: nearly a third of all arcs exist to let distant transitions
peek at shared state.

## The sweep: five categories cover all 94 reads

| Category | Reads | What they do | Classification |
| --- | --- | --- | --- |
| C1 staleness fencing | 42 | accept_* currency guards (11), result-envelope retirement (16), queued-basis retirement (11), admission retirement (4) | **ACCIDENTAL** — AX3 + AX6 |
| C2 authorization/serialization | 5 | authorize_change, authorize_rerun, authorize_repair | **ACCIDENTAL structure** — AX4; domain rules preserved |
| C3 conversation coupling | 21 | start_conversation reads the whole cohort (9), intent acceptance, reply, recovery routing | **ACCIDENTAL** — AX7 |
| C4 projection joins | 25 | request_dashboard (8), authorize_readiness (8), reminder_due (9) | **OPEN** mechanism; requirement real |
| C5 admission refresh | 1 | refresh_admission reads review_state | **ACCIDENTAL** — AX6 |

**69 of 94 reads (73%) are classified ACCIDENTAL** with experiment
evidence behind each classification. The remaining 25 serve the one
genuinely relational thing the product does: deriving readiness.

### C1 — staleness fencing (42 reads): the largest single displacement

```python
# production idiom, ×27 transitions: peek at authority to decide
# whether a result/basis/admission still belongs to the living world
tr = getattr(retire.t, name)(guards=_guard(predicate))
(p.authority, owner) >> arc.read() >> tr        # topology.py:1660
p.authority >> arc.read() >> accept_review       # topology.py:1400

# unified model: no peek exists to write.
# AX3 — the operation is the fence (CAS classifies itself);
# AX6 — resume is ALWAYS epoch+1, so a drained token's stamp is
#       self-evidently dead:
case Quiescent(epoch, head), ObservedOpen(seen):
    return Running(epoch + 1, seen), (Resume(...),)   # stale work: inert, unrouted
```

Production spends 42 read arcs asking "is this stale?"; the unified
model makes staleness *unexpressible* — a stale completion carries an
old epoch and no transition wants it.

### C2 — authorization (5 reads): flags become consequences, rules stay

```python
# production: a flag in a shared place, read-arced into the authorizer
p.authority >> arc.read() >> authorize_change            # :1426
(p.authority, p.mutation_state) >> arc.read() >> rerun   # :1488

# unified: serialization falls out of control state (AX4-tested) —
service(Quiescent(3, "h1", expected="commit-…"), "change")
== Decline("change", "a just-pushed commit awaits observation; …")
```

The guard *predicates* (`_first_failure`, `_repairable`) are real
domain rules; they survive as typed classify outcomes inside the
actions subnet. Only the ambient-read structure is accidental.

### C3 — conversation coupling (21 reads): the stamp did it

`start_conversation` reads all nine cohort places before classifying a
comment. AX7 showed classification is spendable, read-only work
needing no authority; the epoch/head stamp on all 12 intent kinds is
what dragged the concern into the marking. Three effect grades detach
it: 21 reads → one typed port (`Execute`).

### C4 — projection joins (25 reads): the honest keeper

`ready(snapshot)` folds nine concern states into the readiness
verdict — the product core. The requirement is untouchable; the
*mechanism* is a choice:

```text
production        9 cohort places + 25 read arcs + relational join
                  guards at three transitions
alternative       concern subnets emit typed exits; the control layer
                  folds them into a ReadinessSnapshot value and owns
                  the three derived decisions (dashboard, announce,
                  remind)
```

OPEN — with a lean: everything else in the unified model already
made the control layer the owner of derived rules (AX1's "all DERIVED
rules live here"). But **the ES-004 series never spiked the
projection, the announcement gate, or the reminder timers** — see
MISSED below.

## Control places, classified

| Place | Production role | Classification |
| --- | --- | --- |
| `seed` | admitted-but-never-ran bootstrap | ACCIDENTAL — AX6 `admit()` |
| `dormant` | draft parking | ACCIDENTAL — AX6 `Quiescent` |
| `terminal` | closed/merged absorber | kept as control **value** (AX6 `Terminal`); the place form accidental |
| `authority` | ambient current-generation basis | ACCIDENTAL as ambient place — the data lives in `Running(epoch, head, …)` |
| `mutation_state` | provisional + in-flight flags + repair lineage | flags ACCIDENTAL (AX4/AX6); **repair lineage OPEN — unspiked** |
| `review_state`, `actions_state`, `human_state` | per-concern folds | subnet-owned state is fine; their *cross-concern readability* is the accidental part |
| 4 publication states | operation identity for in-flight effects + recovery | largely ACCIDENTAL under attempt-first (operation identity travels in the work token; lookup-first recovery reads history); recovery routing OPEN |

## MISSED — what the independent model has not earned

The sweep must cut both ways. Requirements production meets that no
ES-004 spike has demonstrated:

1. **The readiness projection and announcement gate** (C4) — the
   product core. Named in AX1 as shape P's upstream, never built.
2. **Timers and reminders** — `reminder_due` + `rearm` with real
   `Delay` timers; no experiment touched time at all.
3. **The actions repair flow** — observe failure → rerun once →
   repair → re-observe: the richest control loop in production
   (`_first_failure`, `_repairable`, `_basis_done`). Rules verified
   real; unified expression untested.
4. **Repair lineage across confirmed generations**
   (`repair_used`, `repair_fingerprint` surviving `confirmed`
   resumes) — AX6 carries the relation but no spike carries the data.
5. **Payload shape contracts** — AX4's finding; missed in production
   AND the spike algebra (colors are not fields). Feeds ES-003's
   typed-binding direction.
6. **Finding lineage across quiescence** — AX7 flagged: production
   drops findings on dormant resume; the unified model implies they
   survive. A product decision nobody has made.
7. **Human observation folding** (approvals, dismissals, capability
   blocks) — structurally like actions, but never spiked.

None of these contradicts the unified model; all of them are work the
model has not yet done. The 73% ACCIDENTAL figure stands on what WAS
tested: staleness, serialization, conversations, quiescence,
composition.

## The Navigator's heuristic, quantified

> "There's a proportion regarding arcs and places and transitions. If
> I have a lot more arcs, then I probably have state spread."

Measured: production 2.69 arcs/node with 30% reads; every measured
linear fragment ≈1.1 with zero reads (the one read in AX2 is the
fence AX3 retired). The excess above ~1 is almost exactly the
read-arc population — state spread is not a metaphor here, it is the
94 arcs the sweep classified.

## Verdict

**Promising; the exploration's question is answered.** Hamsterdan's
complexity is measurably concentrated in one idiom — ambient state
consulted through read arcs — and 73% of that idiom is displaced by
already-executed experiments: attempt-first gates (AX3), epoch-scoped
quiescence (AX6), effect-graded conversations (AX7), and typed-port
composition (AX4). What remains is one honest OPEN (where the
readiness projection lives) and a concrete MISSED list dominated by
the never-spiked concerns: projection/announcement, timers, and the
repair loop. Those three are the natural next experiments if the
Navigator wants the unified model to earn the rest of its claim —
otherwise ES-004 is ready for synthesis.
