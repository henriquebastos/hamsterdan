# AX1 — The complete cohabited V5 Hamsterdan

**Status:** done, oracle-approved (six rounds), 2026-08-14.
**Question:** can the ENTIRE chapter-17 Hamsterdan contract — all nine
concern loops from the AX0 census — run as one cohabited Petrus
instance per PR, authored greenfield on the shipped spec DSL, with
every A1–A5 obligation executable and pinned by timeline tests?

**Answer: yes.** One instance, nine loops, 47 executed timelines, all
green on the frozen engine. The prototype is one self-contained file:

- [test_ax1_complete_v5.py](test_ax1_complete_v5.py) — types, pure
  folds, topology builder, fake-world gates, 47 tests
- [conftest.py](conftest.py) — path wiring only

## 1. The shape

```text
85 places · 77 transitions · 312 arcs
0 guards · 0 read arcs · 0 CEL filters · 0 inhibitor arcs
arc ratio = 312 / 162 nodes = 1.926
```

Production (untouched, for AX4): 115 nodes / 309 arcs / 94 reads /
48 guards / CEL filters throughout. The V5 net is bigger in arcs than
the AX0 estimate (~110) because **every fence became explicit routing**
— six oracle-driven amendments each added places/transitions instead
of guards. The instruments that vanished entirely: guards, read arcs,
filters, inhibitors. Every decision is a pure fold on token data.

Structural invariants are themselves pinned as tests, not prose:

- `test_every_cycle_is_serialized_by_a_baton` — every cycle in the
  net passes through exactly one baton place (the AX7 anti-braid
  invariant, now machine-checked).
- `test_loops_touch_only_at_declared_seams` +
  `test_batons_are_private` — cross-loop arcs equal the declared seam
  list EXACTLY (stale declarations fail), and no loop reads another's
  baton.

## 2. What each loop looks like (authoring sample)

A concern loop is a baton place, a mailbox place, and pure folds:

```python
esc = block("esc")
esc.p.ladder(Ladder)            # the baton: rerun/repair budgets
esc.p.failures(ChecksFailure)   # the mailbox (seam from CI)
esc.p.rerun_req(RerunReq)       # gate request
...
(esc.p.failures & esc.p.ladder) >> esc.t.decide(handler=petri_handler(_esc_decide))
esc.p.rerun_moved >> esc.t.fold_rerun_moved(handler=petri_handler(_esc_fold_rerun_moved))
```

All world contact is four motus activity gates (`publish_gate`,
`git_gate`, `rerun_gate`, `announce_gate`) plus three
authority-orthogonal ones (`reply_gate`, `reminder_gate`,
`dash_gate`). Gates classify their own outcome into typed terminals
(`Pushed | MovedM | FaultM`); folds route on the type, never inspect
the world.

## 3. The authority architecture that survived the oracle

Six oracle rounds hammered one theme: **when is a claimed authority
stale, and who can tell?** The surviving design:

1. **The grant is host-owned.** `world["authority"]` (phase +
   incarnation + head/base/policy) is folded by the HOST before the
   net observes anything (`see_head`/`see_draft`/`see_resume`/
   `see_close` move the world first). Gates fresh-read it.
2. **Requests carry the full claim** (head, base, policy,
   incarnation) captured at creation from the authority owner;
   **gates compare at execution** — never in between.
3. **Incarnation is the only fence for the draft→resume race.** A
   resume mints a new incarnation even when head/base/policy are
   byte-identical; a held i1 effect executing after resume classifies
   `moved` although every provider field matches
   (`TestFourthVerdictBlockers::test_stale_*`, four gates covered).
   The push CAS cannot catch this — the head never moved.
4. **Moved ≠ faulted ≠ landed.** Moved burns no budget and refunds
   custody; faulted retains the EXACT request for recovery; landed is
   recorded on acknowledgment (announce-once per incarnation).
5. **Two custody styles, declared per loop** (A5): held baton
   (review, rerun, mutation, dashboard) vs recorded pending
   (readiness, reminder, conversation — deliberately concurrent).

## 4. The six oracle rounds (what each rejected)

| Round | Verdict | Blocker | Resolution |
|---|---|---|---|
| 1 | reject | announce could land under a stale incarnation | per-incarnation announce recording on acknowledgment |
| 2 | reject | close-during-in-flight publications double-settled; dashboard unknown terminal lost the effect | close settles exactly once per custody; dashboard Faulted retains exact effect |
| 3 | reject | ladder budget survived genuinely new code; rerun crash-after-success duplicated; failure/refresh order divergence | budget per fingerprint PER LINEAGE; lookup-first before failure branches; park-and-reissue vs immediate-reissue convergence |
| 4 | reject | identical-tuple draft→resume fencing missing; rerun fault rung not fail-closed; dashboard recovery not exact | host grant + incarnation in every sensitive gate; `rerun_faults` retention + `esc.recover` door; exact-request retention + `dash.heal` self-heal |
| 5 | reject | faulted repair rung stored as bare string `"fault"` — a moved settle after exact recovery crashed the fold and stranded custody | rung retains `{**entry, "state": "fault"}`; pinned by `test_faulted_repair_recovery_after_base_move_refunds_and_relands` |
| 6 | **approve** | none | — |

Round 5 is the exemplary V5 lesson: because custody is DATA in a
baton token, "stranded custody" is a reachable-state bug you can pin
with one timeline test — repair faults → base refreshes → exact
recovery reissues the old request → gate says moved → the settle
refunds the rung and echoes a recheck → CI reissues under the fresh
base → exactly one repair ever lands.

## 5. Executed contract coverage

47 tests, all timeline-style against the frozen engine with a fake
world (fake GitHub, fake agent, held dispatcher for interleavings):

- **Shape** (4): inventory, baton serialization, seam exactness,
  baton privacy.
- **Happy path** (2): webhook→review→CI→human→announce, once.
- **A4 timelines** (14): draft/resume re-announce, dormancy leaves
  batons untouched, stale-incarnation facts inert, provisional-head
  confirm/decline, blocked/faulted publication recovery with the same
  effect identity, crash-after-push reconciles without a second push,
  terminal-as-responder, base movement fences without a round.
- **Ladder & reminders** (2): rerun→repair→human; snooze suppresses
  the decision never the fact.
- **Fences & custody** (6): moved base/policy per gate, single-flight
  vs concurrent custody, dashboard accumulation under blockage.
- **Oracle blockers, rounds 1–5** (15): every rejected race pinned.
- **Replay** (1): the resurrected instance holds the final marking.
- **Scheduler** (in conftest/spawn): cohabited loops require
  `choose_throughput`; `choose_conservative` blocks all firing while
  any activity is in flight — the one engine-behavior finding that
  matters for cohabitation (sharded instances get isolation free).

Validation at approval: `47 passed` (AX1 file), `584 passed`
(production suite, untouched), `scripts/check quick` clean.

## 6. Census amendment produced here

A5 (authority-sensitivity classification) was written back into
[ax0-contract-census.md](ax0-contract-census.md): which effects are
authority-sensitive (findings, announce, git, rerun) vs
authority-orthogonal by design (reply, reminder, dashboard), plus the
two custody styles. AX3 must reuse this table unchanged — the loops
are the constant, the assembly is the variable.

## 7. Limitations (honest)

- Fake world, fake agent, in-memory host grant; no webhook custody,
  no real dispatch, no observability — scope rule 4.
- The host grant fold duplicates the lifecycle fold's rules
  (deliberately, host-before-net); in a real host this is one code
  path, not two.
- One instance per PR is assumed; epoch/instance economics were
  settled in ES-006 and not re-litigated here.
- Arc count (312) is decision-grade input for AX4, not a verdict:
  V5 trades arcs for zero guards/reads/filters. Whether that trade
  reads better is exactly the AX4 comparison.

## 8. Next

AX2: the generic courier primitive (outbox place, identified
delivery, crash-and-redeliver dedup) — Hamsterdan-independent,
two toy instances, no production changes.
