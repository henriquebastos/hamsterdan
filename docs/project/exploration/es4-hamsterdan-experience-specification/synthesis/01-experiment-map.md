# Lens 1 — What we did: the experiment map

One entry per experiment: the question, the verdict, the takeaway, and
what to read (in order) if you dig in. Model snippets are quoted
verbatim from the spike code so you can see the shape without opening
the files.

All paths are relative to
[`../experiments/`](../experiments/index.md), where the series rules
and status table also live. Every spike is pure-Python dataclasses and
functions plus focused tests — except AX2/AX3/AX4, which also compile
and run real nets on the frozen Petrus engine via the ES-003 block
algebra.

---

## Arc 1 — Blackout derivation (AX0–AX3): specify Hamsterdan from its boundary alone

### AX0 — Boundary inventory and topology-independent experience map

**Question:** can the Hamsterdan experience be specified from boundary
evidence alone — product docs, contracts, host/github_app code — with
the 1,684-line net topology deliberately never opened?
**Verdict:** promising; continue.
**Takeaway:** the boundary fully specifies *how* effects happen safely
(fencing, CAS, lookup-first, operation identity) but almost never
*when* work is chosen — six major experience decisions (when review
fires, when readiness publishes, rerun vs repair, dashboard refresh,
intent semantics, discard-restart) are **NET-DECIDED**: they exist
only as topology, with no independent specification and 29 recorded
documentation gaps. Four seed premises were corrected (epoch moves
only on head change or dormant resume, base moves are fence-relevant
but not generation-relevant; "no further effects after close" is too
strong; mutation intents don't bump epoch; draft PRs were unmodeled).
Six boundary concepts the scaffold missed were recovered, including
provisional authority and generation relations
(`new | resumed | confirmed | superseded`).

**Read:** [ax0-experience-map.md](../experiments/ax0-experience-map.md),
then the promoted [experience-map.md](../experience-map.md) it feeds.
No spike code; it points into production sources.

### AX1 — Candidate subnets and secure entry/exit contracts

**Question:** does the verified experience map decompose into subnets
with one typed entry, linear work, and explicit domain-outcome exits —
with a thin control layer owning all routing?
**Verdict:** promising; continue (later amended by AX3 and AX6).
**Takeaway:** the system has exactly **two world-mutation gates** —
the comment gate (5 publication activities) and the git gate (CAS ref
advance inside repair/change) — and everything before a gate is
discardable. Two fractal shapes cover 9 of 11 activities: shape P
(publication ×5) and shape M (agent mutation ×4). Five exits are
universal vocabulary (`completed`, `discarded`, `blocked`, `fault`,
with `retryable` internal-only). The Navigator's two idempotency kinds
map onto the gates: lookup-first ("did it before → skip") and
CAS-loss-as-classified-outcome ("doing it again fails → preconditions
changed, not an error"). Six DERIVED decision rules (D1–D6) re-derive
the NET-DECIDED layer from product intent as falsifiable hypotheses.

**Read:** [ax1-subnet-contracts.md](../experiments/ax1-subnet-contracts.md).
The contract notation there is investigative pseudocode; the shapes
became real code in AX2/AX3.

### AX2 — Linearizing review production as a block chain

**Question:** can the AX1 review-production contract be expressed as
one linear ES-003 block chain with the shared exit vocabulary as real
typed exits?
**Verdict:** promising; continue.
**Takeaway:** the contract → chain translation was mechanical — five
leaves, and the compiled net measures **10 places, 5 transitions,
16 arcs = 1.07 arcs/node** with fan-in nowhere. The discard doctrine
is directly observable: on stale authority the agent ran (money
spent), the fence caught it, and zero comments were posted. One shaped
gap: the algebra's two-valued purity (`pure`/`effectful`) cannot say
"disposable effect" — the fix direction is a three-valued grade,
`pure < spendable < committing`.

```python
def review_subnet(world) -> Block:
    interior = rail_then(rail_then(prepare_basis(), run_agent(world)), draft_publication())
    fenced   = then(interior, fence_authority(), on="out")
    return then(fenced, publish_findings(world), on="current")
# exits: {acknowledged, stale, failed, blocked} — exactly the AX1 vocabulary
```

**Read:** [ax2-linear-review.md](../experiments/ax2-linear-review.md),
then [ax2-linear-review/ax2_linear_review.py](../experiments/ax2-linear-review/ax2_linear_review.py)
(the leaves and chain) and its tests. 8 tests.

### AX3 — Attempt-first gates: the operation is the fence

**Question:** Navigator doctrine — *don't pre-check authority; just do
the operation, classify the failure, discard, wait for the webhook.*
Does this hold against real GitHub semantics?
**Verdict:** promising; continue — **AX1 amended**.
**Takeaway:** verified against provider docs and production's own
`git_publish.py`: the git gate is provider-atomic (GraphQL exact
compare-and-swap — a pre-check adds no correctness), and the comment
gate is provider-unfenced (a stale comment **cannot fail**; it lands
rendered "outdated" — no pre-check can close that race either, so
toleration + supersession is mandatory in every design). Authority
pre-checks are therefore never correctness anywhere: at most economy.
Shape M dropped from 5 transitions + 1 context to 3 transitions + 0
contexts, with staleness as the gate's own classified outcome:

```python
outcomes={"committed": "ProvisionalHead",   # → control verifies the head
          "moved":     "BranchMoved",       # preconditions changed — NOT an error
          "fault":     "NonrecoverableFault"}
```

**Read:** [ax3-attempt-first.md](../experiments/ax3-attempt-first.md),
then [ax3-attempt-first/ax3_attempt_first.py](../experiments/ax3-attempt-first/ax3_attempt_first.py)
(shape M and the comment gate used by everything downstream). 7 tests.

---

## Arc 2 — Control as a function (AX6, AX7, AX4): three states, typed ports, nothing ambient

(These ran out of numeric order: AX6 fell directly out of AX3's
conclusion — once the operation is the fence, what is `provisional`
still *for*? — and AX7 out of AX6's one open question. AX4 then
composed the settled pieces.)

### AX6 — Unified quiescence: one stopped state, one resume move

**Question:** are draft dormancy, provisional authority, and
supersession one general quiescent state with one resume move?
**Verdict:** promising; continue.
**Takeaway:** three mechanisms (the `Dormant` place, the
`MutationState.provisional` flag checked by every effect path, the
inline supersession drain) plus two special cases (born-draft refusal,
the `seed` bootstrap place) collapse into:

```python
Running(epoch, head)
Quiescent(last_epoch, last_head, expected=None)  # expected = the head we pushed
Terminal(status, last_epoch, last_head)
```

`confirmed` becomes a pattern match (`seen == expected`) instead of a
fence-checked flag; **resume is always `epoch+1`**, which makes stale
completions of drained work inert without bookkeeping; early discard
on a CAS loss (quiesce before any webhook) is new capability for free.
One open question left — held conversations — dissolved by AX7.

**Read:** [ax6-unified-quiescence.md](../experiments/ax6-unified-quiescence.md)
(the full transition table), then
[ax6-unified-quiescence/ax6_quiescence.py](../experiments/ax6-unified-quiescence/ax6_quiescence.py)
(`admit` + `step`, the whole machine). 18 tests.

### AX7 — Conversations are orthogonal to the head machine

**Question:** why would quiescence hold a conversation at all? Any
message to the agent can look at the repo *now* and answer.
**Verdict:** promising; continue — AX6's Hold **dissolved**.
**Takeaway:** production stamps every classified intent with
epoch/head — including pure questions — and that one data choice is
why parking existed. Grading the 12 intent kinds by effect
(`read_only` → answer in any state, Terminal included;
`durable_note` → apply to lineage, head-indifferent;
`head_bound` → the only grade entering the head machine) makes the
whole conversation concern one pure function with immediate
Answer/Apply/Execute/Decline outcomes. Nothing is parked, so
replay-vs-expire has no subject. The read-only conversation agent
scope (Navigator choice) is what makes "answer even after merge" safe.

**Read:** [ax7-orthogonal-conversations.md](../experiments/ax7-orthogonal-conversations.md),
then [ax7-orthogonal-conversations/ax7_conversations.py](../experiments/ax7-orthogonal-conversations/ax7_conversations.py)
(`GRADE` + `service`, ~40 lines of substance). 10 tests.

### AX4 — Two subnets compose through typed named ports

**Question:** do independently authored subnets compose at their
contract boundary **without a shared control place** — and does the
control loop (`committed → provisional head → verified admission`)
close as data crossing ports?
**Verdict:** promising; continue.
**Takeaway:** shape M and the comment gate fused through one
`then(…, on="committed")` plus a pure adapter, on the real engine,
with `contexts == {}` asserted — and the loop closed as values:
`Execute` in, `CommitGateFired` out, `Quiescent(expected)`, confirmed
resume. Production's `change_in_flight` flag fell out for free as
"Decline while `Quiescent(expected=…)`". Composition errors read like
type errors, naming both ports — and caught a real protocol
anachronism (AX2's fence-era publisher) statically. The one genuine
gap: **colors are not fields** — `ProvisionalHead` fused despite
lacking the `operation` field the consumer needed. That became AX11.

**Read:** [ax4-typed-port-composition.md](../experiments/ax4-typed-port-composition.md),
then [ax4-typed-port-composition/ax4_composition.py](../experiments/ax4-typed-port-composition/ax4_composition.py)
(the whole seam is ~15 lines) and its tests (the zero-control-places
assertion). 8 tests.

---

## Arc 3 — The sweep and the debt (AX5, AX8–AX12): measure, then earn it

### AX5 — The divergence sweep: 94 read arcs, classified

**Question:** where does the independent model diverge from
production's `topology.py`, and is each divergence ACCIDENTAL
complexity, a MISSED requirement, or an OPEN choice?
**Verdict:** question answered.
**Takeaway:** the sweep is *executable* — every number derives from
`build_net()` and is asserted, so the document cannot drift. Measured:
**46 places, 69 transitions, 309 arcs, 94 of them reads (30%),
2.69 arcs/node**; `authority` alone has degree 46. Five categories
cover all 94 reads; **69 (73%) are ACCIDENTAL** with executed
experiments behind each classification (staleness fencing 42,
authorization flags 5, conversation coupling 21, admission refresh 1);
the remaining 25 serve the readiness projection — requirement real,
mechanism OPEN (closed by AX8). The sweep cut both ways: a 7-item
MISSED list of things production does that no spike had demonstrated —
which became AX8–AX12. The Navigator's arcs/nodes heuristic was
quantified: the excess above ~1 arcs/node is almost exactly the
read-arc population.

**Read:** [ax5-divergence-sweep.md](../experiments/ax5-divergence-sweep.md),
then [ax5-divergence-sweep/ax5_inventory.py](../experiments/ax5-divergence-sweep/ax5_inventory.py)
(the category inventory the tests pin against the real net). 5 tests.

### AX8 — The readiness projection as a fold, not a join

**Question:** production derives dashboard/readiness/reminders by
joining nine cohort places through 25 read arcs. Is the *join* the
requirement, or only the *mechanism*?
**Verdict:** promising; continue — AX5's last OPEN closed.
**Takeaway:** concern subnets emit typed exits; the control layer
folds them into one immutable `Snapshot` per generation; dashboard and
announcement become pure `decide(snapshot)` functions. Every
production rule survives verbatim (`workflow_gates_ready`, dashboard
drift, announce-once). Two structural findings: **in-flight guard
flags have nothing left to guard** (an in-flight repair is just an
unfolded exit), and **operation identity replaces dedup flags**
(`dashboard:{epoch}:{head}:{digest}` — same state, same operation, the
gate absorbs replays). The fold is commutative across independent
concerns (tested over all 24 permutations) and replay is a refold.

**Read:** [ax8-projection-fold.md](../experiments/ax8-projection-fold.md),
then [ax8-projection-fold/ax8_projection.py](../experiments/ax8-projection-fold/ax8_projection.py)
(`Snapshot`, `fold`, `decide` — the pattern every later spike reuses).
8 tests.

### AX9 — Time as typed ingress: the reminder without nine read arcs

**Question:** is time a special citizen requiring marking-wide reads,
or one more provider whose facts fold into the snapshot?
**Verdict:** promising; continue.
**Takeaway:** the scheduler is a provider like GitHub: `ArmTimer` is
emitted work, `TimerDue(epoch, head, sequence, at)` is typed ingress,
and maturity is a durable folded fact — which preserves production's
load-bearing semantic that a matured-but-suppressed reminder fires the
moment conditions return. The instant lives *in the event*, so replay
never consults a clock — the same discipline Petrus's own `Delay`
watermark provides (kept as requirement-grade design, not displaced).
Sequence + epoch + head fence duplicate, early, and stale deliveries
inert at the fold boundary. One named divergence: re-arm anchored at
acknowledgment (what the reviewer saw) instead of at firing.

**Read:** [ax9-timer-ingress.md](../experiments/ax9-timer-ingress.md),
then [ax9-timer-ingress/ax9_timer.py](../experiments/ax9-timer-ingress/ax9_timer.py). 13 tests.

### AX10 — The rerun → repair loop is a bounded escalation ladder

**Question:** is the one real cycle in production — observe failure →
rerun → repair → re-observe — genuine domain structure, and can it be
expressed without the eight flags, the basis place, and seven read
arcs that implement it today?
**Verdict:** promising; continue — AX5's executable MISSED list closed
here (with AX8/AX9).
**Takeaway:** the ladder is REQUIREMENT; its mechanism is ACCIDENTAL.
**GitHub's own attempt counter is the loop variable**
(`failure@attempt=1` = first failure, `failure@attempt>1` =
reproduced, `success@attempt>1` = flaky-green), so
`rerun_requested`/`rerun_attempt` re-derive what the event already
says. A monotonic fence over `(run_id, attempt, conclusion)` replaces
the basis place. Boundedness is structural: one rerun, one repair per
fingerprint and per PR lineage (`repair_used`,
`repair_fingerprint` carried through confirmed resumes), human last —
the worst case emits exactly two operations. Repair outcomes route the
*control layer*: ok → `Quiesce(expected)`, CAS moved → discard, agent
failure → the human rung with the generation still running.

**Read:** [ax10-actions-repair-loop.md](../experiments/ax10-actions-repair-loop.md),
then [ax10-actions-repair-loop/ax10_repair.py](../experiments/ax10-actions-repair-loop/ax10_repair.py). 16 tests.

### AX11 — Payload shape contracts: ports carry types, not color strings

**Question:** AX4 showed colors are not fields. What does a port
contract carrying payload *shape* look like, what is the fusion rule,
and how much do pyright and ty enforce at edit time?
**Verdict:** promising; continue.
**Takeaway:** the fusion rule must be **nominal** — production's own
`ChangeResult`/`RepairResult` have *identical field lists* but
different meanings (a structural rule would corrupt repair lineage).
Shape is the *diagnostic*: a refusal lists exactly the missing or
mistyped fields. Adapters get their contracts *inferred from
signatures* (a single source cannot lie); guard field paths are
validated against the payload type, nested. And the static twins of
every composition mistake are caught **today** by both pyright 1.1.411
and ty 0.0.63 — shape errors are structural, exactly ty's
no-false-positives sweet spot, unlike the generic-parameter gaps found
in ES-003. The Petrus speculation lands measured: the engine keeps
nominal string colors; the authoring layer holds
`Port(name, payload_type)` and *derives* the color.

**Read:** [ax11-payload-shape.md](../experiments/ax11-payload-shape.md),
then [ax11-payload-shape/ax11_shape.py](../experiments/ax11-payload-shape/ax11_shape.py)
and the checker fixtures (`shape_cases_good.py` / `shape_cases_bad.py`).
15 tests (11 runtime + 4 checker-harness).

### AX12 — Human observation folding: a mirror plus notes

**Question:** AX5 guessed the human concern (approvals, dismissals,
capability blocks) was "structurally like actions". Is it?
**Verdict:** promising; continue — and the guess was wrong in an
instructive way.
**Takeaway:** no ladder, no loop variable, no budget. The human
concern is the simplest shape yet: a **last-write-wins full snapshot
mirror** of GitHub's review surface (order within the concern is
load-bearing by design — the event log's order IS the concern's
order), plus **field-level notes** (snooze/resume/reassign), plus
**finding dispositions** (acknowledge/dismiss/defer as pure review
folds — dismissing the only blocking finding clears the review; an
`unable` review is never upgraded). Spiking it surfaced a real product
collision the static sweep missed: `reminder_snoozed` survives the
next observation but a `reassign` is silently clobbered by it —
flagged OPEN, not fixed.

**Read:** [ax12-human-fold.md](../experiments/ax12-human-fold.md),
then [ax12-human-fold/ax12_human.py](../experiments/ax12-human-fold/ax12_human.py). 12 tests.

---

## Where the numbers live

Every quantitative claim in this synthesis (46/69/309/94, 73%,
1.07 arcs/node, degree 46) is asserted by a test that runs against the
real production `build_net()` or a real compiled spike net — see
[ax5-divergence-sweep/test_ax5_sweep.py](../experiments/ax5-divergence-sweep/test_ax5_sweep.py)
and [ax2-linear-review/test_ax2_linear_review.py](../experiments/ax2-linear-review/test_ax2_linear_review.py).
The full exploration suite is 547 tests.
