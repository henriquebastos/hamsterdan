# AX6 — Unified quiescence: one stopped state, one resume move

## Question

Navigator hunch: *dormant-for-draft is a special case of a general
control state.* Draft PRs, superseded authority, and our own
just-pushed commits all mean the same thing — stop the machines,
finalize or discard in-flight work, wait for ingress to announce the
next authority, resume as a fresh generation. Can one state with one
optional refinement replace today's three separate mechanisms, and
does it eliminate special cases rather than relabel them?

This experiment jumped ahead of the planned AX4/AX5 because it fell
directly out of AX3's conclusion plus Navigator direction: once the
operation is the fence (AX3), what is `provisional` still *for*?

Spike: [ax6-unified-quiescence/](ax6-unified-quiescence/) — 18 tests,
all passing; no production code touched.

## Production today: three mechanisms for one meaning

| Mechanism | What it protects against | Where |
| --- | --- | --- |
| `Dormant` place (last_epoch, head) | acting on a draft PR | `contracts/readiness.py:297-302`; entered via `_stop_generation("draft", ...)` `host/application.py:139-143` |
| `MutationState.provisional` flag + fence checks | publishing between our push and observing it | `contracts/readiness.py:157-166`; `is_current`/`fence` raise `"provisional authority cannot publish additional effects"` `host/runtime.py:224-250` |
| Inline supersession drain | acting on a replaced head | `_start_generation`: `relation = "confirmed" if admission.head == prior.provisional_head else "superseded"` + `host.drain()` `host/application.py:323-353` |

Plus two adjacent special cases:

- **Born-draft refusal.** A draft PR with no existing host is never
  instantiated (`host/application.py:139-143` requires host/seed), so
  "born draft" and "went draft" are different code paths.
- **`seed` bootstrap place.** A third pseudo-lifecycle state existing
  only to mark "admitted but never ran" (`host/application.py:151,
  380-386`).

The provisional mechanism is the most expensive: production models
"we pushed, awaiting confirmation" as *Running-but-fenced* — a boolean
that every effect path must remember to check (`is_current`, `fence`,
`publisher_fence` in `host/runtime.py:224-267`). Forgetting one check
is a latent bug class.

## The model: three states, one transition function

```python
Running(epoch, head)
Quiescent(last_epoch, last_head, expected=None)   # the ONE stopped state
Terminal(status, last_epoch, last_head)

# expected is the single optional refinement:
#   None            → draft dormancy, post-CAS-loss idling
#   head_we_pushed  → today's MutationState.provisional
```

```text
today                          proposed
─────────────────────────      ───────────────────────────────
Dormant (draft only)           Quiescent(expected=None)
MutationState.provisional      Quiescent(expected=head_we_pushed)
supersession drain (inline)    quiesce → resume in one step
seed bootstrap place           gone: admit() puts every PR in
                               Running or Quiescent from birth
(impossible: early discard     Quiescent on a CAS 'moved' exit,
 on known-stale authority)      before any webhook arrives
```

Full transition table (the spike's `step` is exactly this — no cases
outside it):

| State | Event | Next state | Actions |
| --- | --- | --- | --- |
| Terminal | anything | Terminal | Ignore |
| Running/Quiescent | ObservedClosed | Terminal(merged/closed) | Drain |
| Running(e,h) | ObservedOpen(h) same head | Running(e,h) | Ignore — base/policy deltas stay in-generation (AX0) |
| Running(e,h) | ObservedOpen(h′) | Running(e+1,h′) | Drain, Resume(superseded) |
| Running(e,h) | ObservedOpen(draft) | Quiescent(e,h) | Drain |
| Running(e,h) | CommitGateFired(x) | Quiescent(e,h,expected=x) | Drain |
| Running(e,h) | StaleSignal (CAS moved) | Quiescent(e,h) | Drain |
| Quiescent(e,h,x) | ObservedOpen(x) | Running(e+1,x) | Resume(**confirmed**) |
| Quiescent(e,h,x≠None) | ObservedOpen(h) | unchanged | Ignore — stale-ordered webhook; our push not yet visible |
| Quiescent(e,h) | ObservedOpen(h) | Running(e+1,h) | Resume(resumed) |
| Quiescent(e,h,·) | ObservedOpen(h″) | Running(e+1,h″) | Resume(superseded) |
| Quiescent | ObservedOpen(draft) | unchanged | Ignore |
| Quiescent | CommitGateFired/StaleSignal | unchanged | Ignore — late terminals of drained work |
| Quiescent | ConversationArrived | unchanged | **Hold** — parked, never reinterpreted |

Admission (the born-draft unification):

```python
admit(ObservedOpen(h, draft=True))   → Quiescent(0, h)              # born draft: an instance, stopped
admit(ObservedOpen(h, draft=False))  → Running(1, h) + Resume("new")
admit(ObservedClosed(...))           → None                          # never remembered
```

`new` then means exactly "born ready"; a draft-born PR marked ready
resumes as `resumed` — honest, because the instance did exist. The
generation-relation vocabulary (`new | resumed | confirmed |
superseded`) survives unchanged; `confirmed` becomes a pure pattern
match (`seen == expected`) instead of a flag consulted by fences.

## Before/after: provisional stops being a fence problem

```python
# today — Running-but-fenced; every effect path must check:
def fence(self, epoch, head, operation, base_head, policy_digest):
    ...
    if mutation.provisional:
        raise StaleAuthorityError("provisional authority cannot publish additional effects")
    # (+ is_current, publisher_fence — each repeats the check)

# proposed — stopped, so there is nothing to check:
case Running(epoch, head), CommitGateFired(expected):
    return Quiescent(epoch, head, expected), (Drain(),)
    # no effects can start; no fence needs to remember why
```

The freeze moves from *a flag consulted everywhere* to *a state in
which nothing runs*. Same observable behaviour (no effects between
push and confirmation), zero scattered checks.

## Executed evidence

```text
18 tests, all passing:

AX0 scenarios unchanged   draft → Quiescent; ready → Running(e+1,
                          "resumed"); supersession = Drain + Resume in
                          ONE step; same-head → in-generation Ignore;
                          close/merge terminal from any live state;
                          Terminal absorbs everything
provisional = expectation CommitGateFired → Quiescent(expected=x);
                          observing x → Resume "confirmed" (lineage
                          preserved); rival head during expectation →
                          "superseded" (lineage NOT preserved);
                          stale-ordered webhook still reporting the
                          pre-push head → Ignore (cannot resume onto
                          our own past)
early discard             StaleSignal (CAS 'moved') quiesces BEFORE
                          any webhook — impossible in today's model;
                          the eventual webhook resumes normally
quiescent discipline      conversations Held, never reinterpreted;
                          late terminals of drained work inert; draft
                          observations inert
born-draft admission      admit(draft) → Quiescent(0, h); later ready
                          → Running(1, h, "resumed"); admit(ready) →
                          "new"; closed → never admitted
liveness                  supersession resumes in the same step (no
                          waiting); only StaleSignal waits — because
                          the next authority is genuinely unknown
```

## Findings

1. **The unification holds with one refinement, not zero.** Draft
   dormancy and provisional waiting are not literally the same state —
   the latter carries an expectation that changes how the *next*
   observation is classified (`confirmed` vs `resumed`). But that is
   one optional field, not a separate mechanism, and the drain ritual
   on entry is identical for all three paths.

2. **`epoch+1` on every resume is load-bearing, not an inherited
   rule.** Production already does this (`_target_epoch` gives
   dormant-resume `last_epoch + 1` even for the same head,
   `host/application.py:312-321`). The spike shows *why* it must stay:
   stale completions of drained work carry the old epoch and are
   therefore inert without any bookkeeping — the drain can be lazy.

3. **Liveness is preserved by distinguishing what we know, not by a
   policy choice.** "Failed authority goes dormant" splits cleanly:
   when the newer authority arrived with the same event (supersession)
   we resume in the same step; only when we know the world changed but
   not to what (CAS `moved`) do we wait. Waiting is never a choice —
   it happens exactly when there is nothing to resume onto.

4. **Early discard is new capability, not just relabeling.** Today a
   CAS loss surfaces wherever the mutation subnet handles it, and the
   instance stays nominally active until the webhook arrives. Here
   `StaleSignal` quiesces immediately: no new work starts during the
   gap, at zero correctness cost (AX3: the operation is the fence).

5. **Universal admission deletes the `seed` special case.** Every
   observed PR is Running or Quiescent from its first observation;
   `seed` and the born-draft refusal both disappear. Terminal remains
   deliberately distinct: AX0 confirmed no boundary route reactivates
   a closed/merged PR, so it stays an absorbing state rather than a
   fourth quiescence flavor.

6. **Open question — held conversations.** `Hold` parks an admitted
   `@app` comment that arrives while quiescent (AX0 quarantine
   doctrine: never reinterpreted later). Whether held conversations
   replay on resume or expire is a product decision, not a control
   question; deferred.

   > **Dissolved by [AX7](ax7-orthogonal-conversations.md):**
   > conversations never reach this machine. Classification by effect
   > grade answers read-only intents in any state, applies durable
   > notes without head currency, and declines head-bound requests
   > with an immediate explanatory reply — nothing is parked, so
   > replay-vs-expire has no subject. The `Hold` case remains in the
   > spike as the recorded seam.

## For AX5 (divergence classification)

| Divergence from production | Provisional classification |
| --- | --- |
| `MutationState.provisional` + fence checks → `Quiescent(expected=...)` | ACCIDENTAL — same behaviour, fewer moving parts |
| `Dormant` place + `seed` place → one `Quiescent` state | ACCIDENTAL |
| Born-draft refusal → universal admission | OPEN — costs storage per draft PR; Navigator hunch favors admission |
| No early-discard path today | MISSED (in production) — the unified model gets it for free |
| Held-conversation replay vs expiry | OPEN |

## Verdict

**Promising; continue.** The Navigator hunch survives contact with the
production evidence: one stopped state with an optional expectation,
one drain ritual, one resume move at `last_epoch + 1`, and the
generation-relation vocabulary intact. `MutationState` shrinks to
repair-lineage bookkeeping; the fence's provisional clause and the
seed/dormant split disappear. Feeds AX5 directly.
