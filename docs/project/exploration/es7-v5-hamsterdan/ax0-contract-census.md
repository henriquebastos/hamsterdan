# AX0 — Contract census: chapter 17 translated into V5 actor vocabulary

**Status:** done, 2026-08-14. Doc-only experiment; the census is the
deliverable. Source contract:
[ES-005 ch.17](../es5-design-primer/17-hamsterdan-rebuild-brief.md),
whose per-clause evidence lives in ES-004's
[experience-map.md](../es4-hamsterdan-experience-specification/experience-map.md).

## The question

Which chapter-17 obligations are **boundary-observable behavior**
(must be honored exactly), and which are **tower-era mechanisms**
(epochs, generations, fences, drains) that V5 replaces with actor
mechanisms? Then: what is the complete loop census for AX1?

## 1. The translation table — mechanism, not behavior

Chapter 17 was written against the generation/epoch model. V5 keeps
every *observable* clause and replaces the mechanisms:

| Tower-era mechanism (contract wording) | V5 replacement | Observable behavior preserved |
|---|---|---|
| "superseding generation: drain, epoch+1, scope reset" | New head is a mailbox token. The in-flight round *completes*; its gate classifies `moved`; the fold discards or keeps findings as provisional. No epoch *machinery* (drains, fences, scope resets) exists — but a durable **incarnation** identity survives in the lifecycle baton and on generation-scoped facts (see amendment A1). | In-flight H1 effects cannot land after H2 |
| "in-flight effects cannot pass the fence" | Attempt-first gates: git push is true server-side CAS; comment effects do lookup-first + a fresh PR read *inside the one gate activity*, classifying `moved` | Late work discarded, never forced |
| "stale completions carry an old epoch and are inert" | A late worker completion returns to a *living* instance and folds normally; its round's gate verdict already decided its fate. After close, known Activity terminals still settle into their owning loop (Terminal batons remain collectors, A3); the host quarantines a terminal whose ownership can no longer be proved | Nothing stale changes the world |
| "ingress targeting a closed generation → drop; uncertain → quarantine" | Three distinct fates, per amendment A3: provably-closed ingress is acknowledged and dropped at the host *before* `Engine.deliver`; generation-**uncertain** ingress is retained in host quarantine and never delivered; dead-letter mailboxes inside the marking are only for safely identified, deliberately unconsumable deliveries | Acknowledged, never reinterpreted |
| "dormancy: drain + dormant place + seed on resume" | The lifecycle loop simply *stops emitting work facts* while its baton says Quiescent. Every concern baton survives untouched — nothing to seed on resume | Stop on draft; resume on ready |
| "base_head participates in every effect fence" | Every provider-effect request carries `(incarnation, head, base, policy, operation)` and its gate compares **all** current authority fields (amendment A1.5). Base movement alone still starts no round (ES-006 ruling 1) — the fence is checked at effect time, not used to churn work | Base moves don't churn work; no effect authorized under an old base lands |

**Honesty note (comment gate):** git push is genuine compare-and-swap;
comment posting is not — the gate is lookup-first plus a fresh read
with an unavoidable small race window. Production has the same window;
the Navigator has ruled outdated comments acceptable.

## 2. The loop census — nine actors, one instance

Every loop = mailbox(es) + private baton + round pipeline + fold;
publications use one shared component shape (ES-006 ruling 2:
render → gate → classify → fold, per-kind explicit) whose owning baton
carries the A2 publication state (Idle/Pending/Blocked/Faulted).
Emitted facts are plain arcs into sibling mailboxes (AX7 anti-braid
invariant).

| # | Loop | Baton holds | Consumes (mailbox) | Emits (facts) | Owns contract clauses |
|---|---|---|---|---|---|
| 1 | **lifecycle** (admission hub) | Running(incarnation, head, base, policy) / Quiescent(last_incarnation, last_head, expected?) / Terminal(last_incarnation, last_head) — ch.17's 3-state machine as baton data, plus the incarnation counter and the provisional-head handshake (A1) | all admitted PR observations | HeadWork(incarnation, relation) → review, ci; StateFact(incarnation, lifecycle, head, base, policy, mergeability) → readiness, dashboard; HumanFact(approval, changes_requested, unresolved) → readiness, dashboard; Close → everyone; comment forwarding in **all** states (A3) | whole Lifecycle block; provisional-head verification and lineage custody; late terminals; no reactivation |
| 2 | **review** | reviewed heads, provisional findings, dismissals | HeadWork; RecoverFact; DismissFact (from conversation) | FindingsFact → readiness, dashboard | agent credential-less; findings publication (immutable, announce-once); dismissing-only-blocking-finding clears |
| 3 | **ci** | newest (run_id, attempt, conclusion) per head | HeadWork; ActionsObserved | ChecksFact → escalation, readiness, dashboard | "payload status not trusted": newest exact-head run, required jobs |
| 4 | **escalation** | ladder position: rerun budget, repair budget per fingerprint per lineage | ChecksFact (failures) | RerunRequest gate (own tail); RepairRequest → mutation; HumanNeeded → dashboard | rerun once → repair once per fingerprint → human |
| 5 | **conversation** | reply identities served | IntentFact (admitted @app comments, forwarded by lifecycle in every state) | explicit outcome for **all 12 intents** (A3): ReplyFact publication (own tail); MutationRequest → mutation; RecoverFact → owning loop; DismissFact → review; SnoozeFact / timer request → reminder; safe no-op/decline | 12 intent kinds, exactly-one else safe reply; grades by state: read-only replies in ANY state incl. Terminal, durable notes only in live states, committing work only from Running |
| 6 | **mutation** | one-at-a-time serialization (the baton!), repair lineage, Idle/Pending/Faulted state (A2) | MutationRequest (repair, change, update_base, resolve_conflict — kind-explicit pipelines, shared git CAS gate) | MutationPending(operation, incarnation) → readiness; ProvisionalHead(expected, operation, lineage) → lifecycle; MutationSettled(operation, outcome, incarnation) → readiness, escalation, dashboard; FaultFact on unknown terminal | host-validated patch, trailers, server-side CAS, moved = discard; baton returned on **every** exit including fault (A2) |
| 7 | **dashboard** | last digest | FindingsFact, ChecksFact, HumanFact, StateFact | — (own upsert tail) | drift = digest inequality; mutable singleton |
| 8 | **reminder** | matured facts (durable), snoozes | TimerDue (host scheduler); SnoozeFact | ReminderFact publication (own tail) | maturity durable; snooze suppresses decision, never fact |
| 9 | **readiness** | gate snapshot (checks, findings, approval, conversations, base currency, mergeable, pending mutations, faults) — sole writer; incarnation-mismatched facts inert; announce-once recorded per incarnation on **AnnouncementAcknowledged**, not on issuance (A1.6) | ChecksFact, FindingsFact, HumanFact, StateFact, MutationPending, MutationSettled, FaultFact | ReadinessFact publication (own tail) on the not-ready→ready edge | all-gates advisory; never merges; `unable` never upgraded; announce again after draft-resume (new incarnation) |

Estimated size: ~85–95 nodes, ~105–115 arcs, ratio ≈ 1.15, zero
reads/guards/filters — versus production's 115 nodes / 309 arcs /
94 reads / 48 guards.

## 3. The dormancy decision (explored, as ruled)

Two shapes were considered:

- **A. Direct broadcast + per-loop pause states** — every loop learns
  about draft/ready. Rejected: pause states in nine loops is the braid
  regrowing.
- **B. Lifecycle as admission actor (chosen for AX1).** External
  observations enter *one* mailbox; the lifecycle loop's pure fold
  (`petri_handler`, ch.17's `step`) decides what work facts to emit.
  Dormancy = it stops emitting head work. Conversation facts keep
  flowing in any state (pure intents are head-indifferent, per
  contract). Concern loops never know dormancy exists; their batons
  persist, so ES-006's seed question stays dissolved — *findings
  trivially survive dormancy* (one of spec §13's open product
  choices, now answered structurally).

This makes lifecycle a domain hub — admission is real domain logic
(the boundary's fail-closed rules), not routing machinery. The
anti-braid invariant still holds: lifecycle touches siblings only
mailbox-to-mailbox.

## 4. Oracle amendments (checkpoint passed with conditions)

The AX0 oracle review returned **"start AX1 with named amendments"** —
the nine-loop shape stands, but three contracts were under-specified
and would have been redesigned mid-AX1. Folded in above and pinned
here:

### A1 — Incarnation identity (an epoch surrogate, minus the machinery)

"No epoch stored anywhere" was too strong. Head alone cannot
distinguish two *lifetimes* at the same head: draft-resume at the same
head is a fresh generation that must announce readiness again, and
readiness receiving an H1 fact *after* H2 admission must not fold
stale data. So the lifecycle baton keeps a durable **incarnation**
counter — identity only; no drains, fences, scope resets, or
stale-completion machinery return.

1. Incarnation increments on new, resumed, superseded, and confirmed
   admission; **not** on base-only refresh.
2. `ProvisionalHead` carries expected head, operation, and repair
   lineage; lifecycle stores them before admitting further head-bound
   work.
3. Exact-head admission emits `HeadWork(relation=confirmed,
   incarnation, lineage)` and clears `expected`; a different observed
   head supersedes without silently adopting the lineage.
4. Generation-scoped facts carry the incarnation; readiness ignores
   mismatches in its pure fold.
5. Every provider-effect request carries `(incarnation, head, base,
   policy, operation)`; its gate compares all current authority
   fields. The accepted comment race remains only the post-read window.
6. Announce-once is recorded on `AnnouncementAcknowledged`, not on
   publication issuance.

### A2 — Publication ownership: every round returns its baton

AX6/AX7's "fault swallows the baton" cannot survive contact with the
full contract (a swallowed baton can never fold Close). Every
publication-owning baton gets explicit state:

```text
Idle | Pending(exact request) | Blocked(exact request, effect_identity) | Faulted(operation, reason)
```

- Classified retry stays inside one occurrence, bounded to three.
- A recoverable terminal folds `Blocked` **and returns the baton**.
- Only an authorized `RecoverFact(target, exact_operation)` emits one
  fresh occurrence, reusing the retained request and the **same
  provider-effect identity** (the contract's blocked-publication
  clause). Other events never reopen it.
- Unknown terminals fold `Faulted`, emit a blocking `FaultFact`, and
  return the baton.
- A `Faulted` mutation baton may reject further mutations fail-closed,
  but still consumes Close and exposes the fault. Escalation and
  conversation sharing the mutation baton therefore cannot deadlock;
  the only dangerous case (baton loss) is now structurally excluded.

### A3 — Ingress fates and the complete fact producer table

- Provably-closed ingress: acknowledged and dropped at the host,
  before `Engine.deliver`. Generation-**uncertain** ingress: host
  quarantine, never delivered. In-marking dead letters only for
  safely identified, deliberately unconsumable deliveries.
- Lifecycle forwards admitted comments in Running, Quiescent, *and*
  Terminal — it never parks them. Conversation grades by state:
  read-only replies anywhere (incl. Terminal), durable notes in live
  states, committing work only from Running. Lifecycle and
  conversation batons are never permanently consumed on Close; they
  remain collectors/responders in Terminal with no route back to
  Running.
- Every consumed fact now has a named producer (see the census table):
  `StateFact` and `HumanFact` from lifecycle; `MutationPending` /
  `MutationSettled` from mutation (closing the hole where readiness
  could announce during an in-flight explicit mutation); `SnoozeFact`
  from conversation; `FaultFact` from any gated tail; kind-specific
  acknowledgment facts from publication successes.
- Readiness folding many streams is a **projection, not a braid**,
  under six conditions: sole writer of its snapshot; commuting
  independent folds; monotonic/sequenced same-concern facts;
  incarnation-mismatched facts inert; no upstream loop reads the
  readiness baton; dashboard fed by declared arcs only.

### A4 — Minimum acceptance timelines for AX1

1. Draft → resume at same head → exactly one new readiness
   announcement, under the new incarnation.
2. H1 fact arrives after H2 admission → inert in readiness.
3. Repair lands provisional H2 → second mutation declined without
   effect → exact admission confirms H2, lineage preserved.
4. Publication exhausts three retries → unrelated events do not reopen
   it → exact `RecoverFact` creates one fresh occurrence with the same
   effect identity.
5. Mutation starts while otherwise ready → readiness stays false until
   `MutationSettled`.
6. Mutation faults → other loops continue; readiness records a
   blocker; Close remains collectable.
7. Close → read-only comment answered; late known terminal collected;
   committing effects refused.
8. Base-only movement → no review round, but every effect authorized
   under the old base is rejected at its gate.

## 5. NET-DECIDED rulings proposed for AX1 (Navigator may veto any)

1. Review triggers on every Running head, sequential rounds (AX6).
2. Non-mutation intents: fresh read-only answers, any lifecycle state.
3. Readiness advisory on the not-ready→ready edge only.
4. Failed checks: ladder as contract orders it; `moved` mutation does
   **not** burn budget (no world change happened); landed attempts do.
5. Dashboard republish on digest drift only.
6. After a discard, the next head's round starts automatically
   (mailbox semantics) — no restart policy needed.
7. Host scheduler arms timers; `TimerDue` is an ordinary ingress fact;
   the reminder loop owns maturity (PR-scoped, per ES-006 ruling 5).

## 6. Instruments pinned for AX1/AX3/AX4

- Shape: ES-006 metrics (P/T/A/ratio/reads/guards/filters), cycle
  confinement to batons, seam census (components after removing
  ingress + declared fact arcs = loop count).
- Behavior: executed timelines with a **trace** = (ordered world
  effects, chronicle identities). AX3's sharded assembly must produce
  trace-equivalent runs (same world effects; chronicle identities
  partitioned by shard).
- Machinery bill: host-side responsibilities counted in lines
  (spawn/archive, scheduler stub, and — sharded only — the courier).
- Replay: `Engine.load` reproduces final markings and re-fires
  nothing, per instance.

## 7. Sharding cuts for AX3 (decided when the courier exists)

- **B1 — trust boundaries (default):** {lifecycle, conversation} ·
  {review, escalation, mutation} · {ci} · {dashboard, reminder,
  readiness}. Realistic: admission, agent territory, observation,
  publication.
- **B2 — per-loop (stress):** nine shards; run only if B1 is cheap.

## Verdict

**Promising; continue to AX1** — oracle checkpoint passed with
amendments A1–A3 (folded in above), acceptance timelines A4 pinned.
The contract translates without losing a single observable clause;
epoch *machinery* (drains, fences, scope resets, seeds) disappears
while its guarantees reappear as baton conservation, attempt-first
gates, admission folding, and quarantine/dead letters. What survives
of the epoch is exactly one thing: a durable **incarnation identity**
for fold isolation and announce-once — data in one baton, not
topology. Dormancy costs one state value in one baton instead of
drain/seed machinery. One §13 product question (findings across
dormancy) is answered structurally rather than by policy.

Open for the Navigator (non-blocking, defaults above): the seven
NET-DECIDED rulings, and whether `moved` burns repair budget.
