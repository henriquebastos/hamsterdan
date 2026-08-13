# AX12 — Human observation folding: snapshots, notes, and a collision production hides

## Question

AX5 MISSED #7, the last unspiked concern: approvals, dismissals, and
capability blocks. AX5 guessed it was "structurally like actions".
Is it — or is the human concern a different shape entirely?

Spike: [ax12-human-fold/](ax12-human-fold/) — 12 tests, all passing;
production rules mirrored verbatim from `fold_human`
(`topology.py:347-362`) and `fold_intent` (`topology.py:324-342`);
no production code touched.

## Answer: not a ladder — a mirror plus notes

AX10's actions concern is a bounded escalation ladder with a loop
variable. The human concern has no ladder at all: it is two much
simpler fold shapes that production interleaves in one place.

```text
actions (AX10)                      human (AX12)
──────────────────────────          ─────────────────────────────────
phase machine, loop variable,       MIRROR: each HumanObservation is a
budget fences                       full snapshot — last-write-wins
                                    NOTES: snooze / resume / reassign —
                                    field-level deltas layered on top
                                    DISPOSITIONS: acknowledge / dismiss /
                                    defer rewrite findings (review concern)
```

```python
# fold_human, mirrored verbatim: replace everything the observation owns
case HumanObserved() as value:
    return replace(human,
        observation_sequence=human.observation_sequence + 1,
        approved=value.approved, changes_requested=value.changes_requested, …,
        reviewer=value.reviewer,   # ← clobbers a prior reassign note
        capability_blocking=not value.capability_available,
        # snoozed untouched: the one note that survives observations
    )
case Noted("snooze"):            return replace(human, snoozed=True)
case Noted("reassign", assignee): return replace(human, reviewer=assignee)
```

## Finding 1: within a concern, order is load-bearing — and that is fine

AX8 claimed fold commutativity *across* independent concerns and
parenthetically noted that a concern orders its own exits. The human
concern is where that caveat earns its keep: two snapshots folded in
opposite orders yield different states **by design** (last-write-wins
mirrors of GitHub). Tested explicitly: `folded(APPROVED, CHANGES) !=
folded(CHANGES, APPROVED)`, while refolding the same log is
deterministic. The event log's order IS the concern's order; replay
is untouched. Production's `observation_sequence` counter is the
same fact kept as a number.

## Finding 2: notes and snapshots collide, and production resolves it inconsistently

Two durable notes write into the same state the snapshots mirror:

| Note | Field | Next observation arrives… |
| --- | --- | --- |
| snooze/resume | `reminder_snoozed` | note **survives** — `fold_human` never touches it |
| reassign | `reminder_recipient` | note **clobbered** — `fold_human` writes `value.reviewer` (topology.py:359) |

A maintainer's reassignment silently lasts only until GitHub next
reports the PR — any push, review, or comment refreshes the
observation and reverts the recipient. The spike mirrors this
exactly (tested) and flags it as **OPEN (product)**: either the
asymmetry is intended (the observation's reviewer is authoritative)
or reassign should live where snooze lives (note-owned, observation
never writes it). AX7's grading vocabulary already distinguishes
durable notes from mirrors; this is the one place production blends
them mid-field.

## Finding 3: dispositions are review-concern folds, verbatim

`acknowledge`/`dismiss`/`defer` rewrite finding dispositions and
recompute blocking (`fold_intent`, topology.py:324-335), with the
production subtleties kept and tested: dismissing the only blocking
finding clears the review; an `unable` review is never upgraded by
dispositions; unauthorized intents are inert; duplicates are
idempotent. Nothing here needed places or read arcs — it is a pure
fold on the review concern's own state, exiting into AX8 as
`ReviewSettled(status, blocking_count)`.

## Failure modes

| Mode | Behavior |
| --- | --- |
| out-of-order snapshots | last-write-wins by log order — the concern's own ordering (tested) |
| duplicate snapshot | idempotent surface; sequence increments (production parity) |
| capability outage | folds as a fact; clears on next available observation (tested) |
| unauthorized intent | inert (tested) |
| unknown note kind | inert (tested) |
| disposition on unknown finding id | untouched findings, status recomputed (fold semantics) |
| replay | refold of the log; values only (tested via determinism) |

## Divergence classification

```text
full-snapshot mirror + notes        REQUIREMENT — kept verbatim
observation_sequence counter        ACCIDENTAL as a place-field; the log order
                                     carries it (kept as a number, harmless)
reassign clobbered by observation   OPEN (product) — mirrored, flagged, not fixed
dispositions as review folds        REQUIREMENT — kept verbatim
capability flags                    fold-shaped facts (AX8's classification confirmed)
```

## Verdict

**Promising; continue — and AX5's guess was wrong in an instructive
way.** The human concern is not "structurally like actions": it has
no ladder, no loop variable, no budget. It is the simplest concern
shape yet — a mirror plus notes — and spiking it surfaced a real
product question (the reassign clobber) that the divergence sweep's
static reading missed. AX5's MISSED list is now fully worked
(#1-5, #7); the remaining opens are both product choices: finding
lineage through quiescence (#6) and the reassign/observation
collision (new).
