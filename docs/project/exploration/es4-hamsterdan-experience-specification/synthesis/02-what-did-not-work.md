# Lens 2 — What did not work, and why

Each entry: what we tried (or inherited as an assumption), the code as
it stood, the evidence that killed it, and what replaced it. "Killed"
here is a good outcome — every rejection below is load-bearing in the
final spec.

---

## 1. Authority pre-checks as correctness (AX1 → killed by AX3)

AX1's first subnet contracts mirrored production: fence authority
before the agent works, fence again before the gate.

```python
# AX1 shape M, first draft — fences drawn as structure:
work=[
    fence(authority),                # (epoch, head, base_head, policy_digest)
    agent_coding(isolated),
    validate_patch(),
    git_gate(cas_ref_advance(...)),
]

# AX3, verified against provider semantics — the fences deleted:
work=[
    agent_patch(),                   # no authority context at all
    commit_gate(),                   # the CAS classifies itself:
]                                    # committed | moved | fault
```

**The evidence:** GitHub's git ref advance is an exact compare-and-swap
(production's own `git_publish.py:249-258` uses GraphQL
`expected_head`) — the operation *is* the fence, so a pre-check adds
no correctness. And a PR comment **cannot be refused**: a stale
`commit_id` is accepted and rendered "outdated", so no pre-check can
close that race either — production's own fence re-reads the PR
immediately before POST and still leaves a milliseconds window.
Pre-checks are never correctness anywhere: redundant at the git gate,
insufficient at the comment gate. They survive only as an optional
**economy dial** (don't dispatch provably-stale work), chosen per
publication kind by noise economics.

**Measured consequence:** shape M dropped from 5 transitions + 1
context + 1 read arc to 3 transitions, zero ambient anything.

## 2. Parking conversations during quiescence (AX6's Hold → dissolved by AX7)

AX6's machine had one case it could not decide:

```python
# AX6 — the machine only sees an opaque event, so it must park:
case Quiescent(), ConversationArrived():
    return state, (Hold(),)   # open question: replay on resume? expire?
```

**The evidence:** the coupling was in the *data*, not the domain.
Production stamps all 12 intent kinds with `epoch`/`head`
(`contracts/readiness.py:417-421`) — so a pure question "inherits" a
head and goes stale with it. Grading intents by effect shows 8 of 12
kinds never needed the stamp:

```python
# AX7 — classify by grade FIRST; the head machine never sees questions:
service(Quiescent(3, "h2"), "reply")   == Answer("reply")     # any state, even Terminal
service(Quiescent(3, "h2"), "dismiss") == Apply("dismiss")    # lineage, not head
service(Quiescent(3, "h2"), "change")  == Decline("change",
    "the pull request is draft or its head was superseded; re-ask when it is active")
```

Nothing is parked, so *replay vs expire* is not answered — it has no
subject. The `Hold` case remains in the AX6 spike as the recorded
seam: exactly what classification-before-routing supersedes.

## 3. Two-valued purity (`pure`/`effectful`) — too coarse (AX2)

The ES-003 algebra's `disposable(...)` combinator refused AX2's
review interior even though it mutates nothing observable:

```python
disposable(prepare_basis() >> run_agent(world))
# CompositionError: … not pure       — but the agent call only SPENDS
```

**The evidence:** AX1's effect taxonomy has four classes (pure /
read-only / disposable effect / gate) and the algebra could only say
two. Captured in a failing-shape test, not patched. The fix direction
adopted by the spec: a three-valued effect grade —
`pure < spendable < committing` — where gates are the only
`committing` leaves and `disposable` admits everything below
`committing`. (Also exactly the vocabulary AX7 needed: intent
classification is *spendable*, so it runs in any control state.)

## 4. Color-string ports as the whole contract (inherited from ES-003 → broken by AX4, fixed by AX11)

AX4's composition fused — and should not have fused silently:

```python
# the port fused because the COLOR strings matched…
then(mutation_subnet(world), announce_commit(), on="committed")  # ok
# …but ProvisionalHead carries {provisional_head, reused} and NO
# `operation`, while the comment marker wants (kind, operation, head).
# The adapter silently invented its marker from the head alone.
```

**The evidence:** a composition succeeded that lost information the
consumer's idempotency depended on. AX11 closed it:
`Port(name, payload_type)` — fusion stays nominal, but a refusal now
lists exactly the missing/mistyped fields, adapters derive their
contracts from signatures, and guard field paths are validated against
the payload type. The engine keeps its string colors; they become a
derived projection.

## 5. Structural shape fusion — the obvious rule is wrong (AX11)

Once ports carry payload types, the tempting rule is "fuse whenever
shapes are structurally compatible". Production itself is the
counterexample:

```python
# contracts/readiness.py:546-570 — IDENTICAL field lists:
class ChangeResult(WorkflowModel):
    epoch: int; head: str; ok: bool; provisional_head: str = ""; …
class RepairResult(WorkflowModel):
    epoch: int; head: str; ok: bool; provisional_head: str = ""; …
```

**The evidence:** a structural rule would happily route a change
result into the repair acceptor — and corrupt repair lineage
(`repair_used`, `repair_fingerprint`, the AX10 budget fence). Same
shape is not same meaning. The adopted rule: **nominal fusion, shape
as the diagnostic, explicit adapters to cross types.**

```python
fuse(Port("change.settled", ChangeResult), Port("accept.repair", RepairResult))
# ShapeError: … same shape is not same meaning — adapt explicitly
```

## 6. Flags and basis places as loop state (production idiom → displaced by AX10)

Production implements the rerun→repair loop with eight flags and a
basis place, read-arced into three authorization transitions:

```python
# topology.py:877-900 — _repairable, abridged:
return (_current(a, value) and value.conclusion == "failure"
    and s.rerun_requested                      # flag
    and value.attempt > s.rerun_attempt        # flag re-deriving the event
    and not m.repair_used                      # lineage
    and not m.provisional and not m.change_in_flight and not m.repair_in_flight
    and s.actions == "reproduced"
    and value.fingerprint != m.repair_fingerprint)
```

**The evidence:** GitHub's own `attempt` counter already numbers the
loop — `rerun_requested`/`rerun_attempt` re-derive what the next
observation says on its face. A monotonic fence over
`(run_id, attempt, conclusion)` makes duplicates inert without the
`actions_basis` place, its `basis_retire` transition, or their three
read arcs. The in-flight flags are unfolded exits (AX8's finding). The
two *lineage* facts — `repair_used`, `repair_fingerprint` — are real
and kept: they are the ladder's budget, carried through confirmed
resumes.

## 7. "The human concern is structurally like actions" (AX5's guess → corrected by AX12)

AX5's MISSED list predicted the unspiked human concern would be
another AX10-style ladder. It is not:

```text
actions (AX10)                      human (AX12)
──────────────────────────          ─────────────────────────────────
phase machine, loop variable,       MIRROR: each observation is a full
budget fences                       last-write-wins snapshot
                                    NOTES: snooze/resume/reassign —
                                    field-level deltas layered on top
                                    DISPOSITIONS: pure review folds
```

**The evidence:** production's `fold_human` (`topology.py:346-362`)
replaces *everything the observation owns* on each `HumanObservation`.
There is no phase, no budget, no escalation. The correction mattered
twice: it kept the spec honest (concern shapes differ; don't force one
mold), and mirroring production exactly exposed a field-ownership
collision nobody had seen — `reminder_snoozed` survives the next
observation, a `reassign` note is silently clobbered by it. Left OPEN
for the Navigator, not silently fixed.

## 8. Four seed premises about the boundary (corrected by AX0)

The exploration's own scaffold started wrong four times; the blackout
method caught each before any design leaned on it:

| Seed premise | Corrected to |
| --- | --- |
| "synchronize → authority advances" | epoch moves **only** on head change or dormant resume; a base-only move emits a same-epoch `verified_admission` yet still participates in the effect fence |
| "closed/merged → no further effects" | too strong: published effects remain, late terminals are collected/quarantined; correct claim: no NEW provider effect passes the fence |
| "intents execute under authority" | 3 of 12 kinds are mutations; `mutation=True` does NOT bump epoch; `status` normalizes to `reply` |
| (draft PRs absent from the scaffold) | draft → `GenerationStop` to Dormant; reopen non-draft → resume at `epoch+1`; Terminal has no reactivation route |

**The lesson the spec keeps:** derive from evidence, then verify
against the boundary — the experience map marks every claim VERIFIED,
DERIVED, or NET-DECIDED, and AX5 tested the DERIVED ones against
topology instead of trusting them.
