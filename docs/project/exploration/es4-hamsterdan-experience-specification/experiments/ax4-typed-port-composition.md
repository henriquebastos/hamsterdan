# AX4 — Two subnets compose through typed named ports; control never becomes a place

## Question

The AX1 plan's composition test: do independently authored subnets
compose at their contract boundary **without a shared control place**?
And — now that AX6/AX7 made the control layer a pure function — does
the loop back through control (`committed → provisional head →
verified admission`) close as data crossing ports rather than as
marking state?

Spike: [ax4-typed-port-composition/](ax4-typed-port-composition/) —
8 tests, all passing; every piece reused from earlier spikes unchanged
(AX23 algebra, AX25 rail, AX2 leaves, AX3 subnets, AX6/AX7 functions).

## The baseline being displaced

Production's concerns meet in the marking. `readiness/net/topology.py`
holds **28 read arcs**, ~19 of them reading `p.authority`, the rest
`p.mutation_state`, `p.actions_state`, `p.review_state`, finding
owners, `p.terminal` — every concern leans on ambient places to know
whether it may act:

```python
# topology.py — the shared-place idiom, everywhere:
p.authority >> arc.read() >> accept_review          # :1400
p.authority >> arc.read() >> authorize_change        # :1426
(p.authority, p.mutation_state) >> arc.read() >> rerun          # :1488
(p.authority, p.mutation_state) >> arc.read() >> change_retire  # :1672
```

This is the "spreaded net" the Navigator diagnosed: places as global
state influencing whether distant transitions can occur.

## The composition

Two independently authored subnets fuse through **one named typed
port** plus a pure adapter — a function, not a place:

```python
# ax4_composition.py — the whole seam:
announced = then(mutation_subnet(world), announce_commit(), on="committed")
composed  = then(announced, publish_comment(world), on="out")

# announce_commit: ProvisionalHead → FindingPublicationRequest (pure transform)
```

```diagram
┌─ shape M (AX3) ────────────────────┐        ┌─ comment gate (AX3) ─┐
│ prepare → agent → CAS gate         │        │                      │
│                     ├─ committed ──┼──▶ announce ──▶ post ─ ack ───┼─▶ acknowledged
│                     ├─ moved ──────┼───────────────────────────────┼─▶ moved
│                     └─ fault ──────┼───────────────────────────────┼─▶ fault
│ (rail) ─────────────── failed ─────┼───────────────────────────────┼─▶ failed
└────────────────────────────────────┘        └──────────────────────┘
         contexts == {}  — nothing ambient anywhere
```

Composition consumes exactly one port; `moved`, `fault`, and `failed`
survive untouched. 5 transitions total (3 + adapter + gate), sound,
zero context places.

## The loop through control is data, not marking

```python
state = Running(epoch=3, head="h1")
service(state, "change")                     == Execute("change", 3, "h1")   # AX7: port IN
# … run the composed net; CAS commits "commit-of-op-change-7" …
step(state, CommitGateFired(new_head))       == Quiescent(3, "h1", expected=new_head)  # port OUT
step(…,     ObservedOpen(new_head))          == Running(4, new_head)         # Resume "confirmed"
```

Executed against the real Petrus engine: the compiled net's place set
contains **no** authority, state, or control place — verified by
assertion, not inspection.

And a guarantee production buys with a flag falls out for free:

```python
# production: MutationState.change_in_flight, read-arced into
# authorize_change (topology.py:1426, 1672) — a flag in a shared place

# here: while our commit awaits observation, control simply declines
service(Quiescent(3, "h1", expected="commit-of-…"), "change")
== Decline("change", "a just-pushed commit awaits observation; re-ask once the head updates")
```

Mutation serialization is a *consequence of control state*, not a
place to maintain, read, and reset.

## The static seam: typed ports replace shared-place discipline

```python
# forgetting the adapter — caught at COMPOSITION time, naming both ports:
then(mutation_subnet(world), publish_comment(world), on="committed")
# CompositionError: cannot fuse 'committed' (ProvisionalHead) into
#                   'publish_comment' entry (FindingPublicationRequest)

# protocol drift — AX2's fence-era publisher refuses attempt-first company:
then(draft_publication(), publish_findings(world), on="out")
# CompositionError: … (FindingPublicationRequest) into … (FencedPublication)
```

The second refusal is the more interesting one: AX2's publisher entry
color still *encodes the fence protocol* AX3 retired. The port system
caught a design anachronism statically — the kind of drift a shared
place would have absorbed silently until runtime.

## Executed evidence

```text
8 tests, all passing:

structure      composed block: exits {acknowledged, moved, fault,
               failed}, contexts == {}, 5 transitions, sound
static seam    missing adapter → CompositionError naming both colors;
               fence-era publisher → CompositionError (protocol drift)
engine         committed → announced → acknowledged; comment marker
               carries the new head; branch advanced exactly once
               moved → the announcement subnet NEVER FIRES; zero
               comments; branch untouched
control loop   Execute in → net → CommitGateFired out → Quiescent
               (expected) → ObservedOpen → Running(4) "confirmed";
               compiled net has zero authority/state/control places
serialization  second change while awaiting observation → Decline —
               change_in_flight without the flag
payload gap    the adapter fused despite ProvisionalHead lacking
               `operation` — recorded as a limitation (below)
```

## Findings

1. **Typed named ports are a sufficient seam.** Two subnets authored
   in different experiments, against different worlds, fused with one
   `then(…, on=…)` and one pure adapter. Nothing ambient was needed —
   the composed net is context-free end to end, on the real engine.

2. **The control loop closes as values.** `Execute` is the only door
   in (AX7); exit payloads mapped to control events (`CommitGateFired`)
   are the only door out (AX6). Between them, the net is an ordinary
   function-like block: enter, run to exits, evaluate at the boundary —
   the linearity the Navigator asked for in ES-004's framing.

3. **Shared-place guarantees become control-state consequences.**
   `change_in_flight` is the worked example: production maintains,
   reads, and resets a flag; the unified model gets the same
   serialization from `Quiescent(expected=…)` + Decline. Candidate
   generalization for AX5: *every* `p.authority` read arc (~19) is a
   fence that attempt-first (AX3) or control-state routing (AX6/AX7)
   makes unnecessary.

4. **Color compatibility does not promise field compatibility.** The
   genuine gap this experiment surfaced: `ProvisionalHead` carries
   `{provisional_head, reused}` but no `operation`, while the comment
   marker wants `(kind, operation, head)`. The port fused anyway —
   colors matched — and the adapter had to derive its marker from the
   head alone. Port contracts need payload *shape*, not just color:
   exactly the ES-003 typed-payload direction (binding types instead
   of strings), now motivated by a composition failure rather than
   aesthetics. Recorded as a design requirement for AX5/ES-003 rather
   than patched here.

5. **Static composition errors read like type errors, not runtime
   mysteries.** Both refusals name the two ports and their colors at
   authoring time. The fence-era refusal shows the mechanism catching
   real protocol evolution, which is where shared places fail
   silently.

## For AX5 (divergence classification)

| Divergence from production | Provisional classification |
| --- | --- |
| 28 read arcs / ambient places → context-free port fusion | ACCIDENTAL (pending AX5 sweep of all 28, some may be MISSED requirements) |
| `MutationState.change_in_flight` → Decline while `Quiescent(expected)` | ACCIDENTAL |
| String colors as the only port contract → payload shape unchecked | MISSED (in both production AND the spike algebra) — feeds ES-003 typed-binding direction |

## Verdict

**Promising; continue.** Composition through typed named ports works
on the real engine with zero shared control places, the control loop
closes as data, and the one gap found (payload shape) sharpens the
ES-003 typed-binding case with concrete evidence. AX5 can now run the
divergence sweep: the independent model (AX1–AX4, AX6, AX7) against
`topology.py`, classifying each of the 28 read arcs and every control
place as ACCIDENTAL, MISSED, or OPEN.
