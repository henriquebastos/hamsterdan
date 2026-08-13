"""Capture one pull request's life through the ES-004 unified model —
admission, CI failure, the escalation ladder, a real repair on the
frozen Petrus engine, quiescence and confirmed resume, the green path
to readiness, a reminder timer, the human concern, terminal, replay —
using the real spike code from AX3/AX4/AX6/AX7/AX8/AX9/AX10/AX12.

Run from the repo root:

    .venv/bin/python docs/project/exploration/es4-hamsterdan-experience-specification/synthesis/capture_walkthrough.py

The output is deterministic (the script re-execs itself with
PYTHONHASHSEED=0 because AX8's projection digest uses hash()). The
committed copy lives in walkthrough-capture.txt and is quoted
throughout 04-one-pr-walkthrough.md. If spike code changes, re-run
and re-commit.

Fidelity note: each stage runs one spike's real code. The spikes were
built independently, so AX8, AX9, AX10, and AX12 each carry their own
snapshot dataclass restricted to their concern; the unified spec
(05-unified-experience-spec.md) merges them. Stage 4 runs the real
Petrus engine via the ES-003 block algebra.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":  # AX8 projection digests use hash()
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, *sys.argv])

HERE = Path(__file__).resolve().parent
ES4 = HERE.parent / "experiments"
ES3 = HERE.parents[1] / "es3-workflow-ast-authoring-model" / "experiments"

for sibling in (
    ES3 / "ax11-real-fragment",
    ES3 / "ax19-kernel-boundary",
    ES3 / "ax23-completed-algebra",
    ES3 / "ax25-failure-rail",
    ES4 / "ax2-linear-review",
    ES4 / "ax3-attempt-first",
    ES4 / "ax4-typed-port-composition",
    ES4 / "ax6-unified-quiescence",
    ES4 / "ax7-orthogonal-conversations",
    ES4 / "ax8-projection-fold",
    ES4 / "ax9-timer-ingress",
    ES4 / "ax10-actions-repair-loop",
    ES4 / "ax12-human-fold",
):
    sys.path.insert(0, str(sibling))

import ax8_projection as ax8
import ax9_timer as ax9
import ax10_repair as ax10
import ax12_human as ax12
from ax4_composition import fresh_world, mutation_with_announcement
from ax6_quiescence import (
    CommitGateFired,
    ObservedClosed,
    ObservedOpen,
    admit,
    step,
)
from ax7_conversations import service
from ax23_blocks import BoundaryTransition, compile_block
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def show(label: str, value: object) -> None:
    print(f"  {label:<26} {value}")


def run_block(block, seed_color, seed_data):
    lowered = compile_block("es4-walkthrough-net", block)
    engine = Engine.create(
        lowered.built.net,
        "es4-walkthrough",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(block.entry.place): (Token(seed_color, dict(seed_data)),)}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine, lowered


def main() -> None:
    # ------------------------------------------------------------- stage 1
    banner("STAGE 1 — ingress and admission (AX6): every PR enters one machine")
    print("  webhook: pull_request opened, head=h1, not draft")
    state, actions = admit(ObservedOpen("h1"))
    show("control state", state)
    show("actions", actions)
    print()
    print("  (variant) born as a draft — an instance, stopped, no seed place:")
    draft_state, draft_actions = admit(ObservedOpen("h9", draft=True))
    show("control state", draft_state)
    show("actions", draft_actions)

    # ------------------------------------------------------------- stage 2
    banner("STAGE 2 — the generation snapshot is born (AX8): decisions derive")
    snap = ax8.Snapshot(epoch=state.epoch, head=state.head)
    show("snapshot", snap)
    print()
    print("  decide(snapshot) — nothing is settled yet, but the dashboard")
    print("  projection has drifted from '' (nothing published):")
    for work in ax8.decide(snap):
        show("work", work)
    print("  the operation string IS the dedup — no dashboard_requested flag.")

    # ------------------------------------------------------------- stage 3
    banner("STAGE 3 — CI fails; the escalation ladder climbs (AX10)")
    acts = ax10.Actions(epoch=state.epoch, head=state.head)
    show("actions concern", acts)
    print()
    print("  GitHub reports: run-9 attempt 1 concluded failure, fingerprint fp-A")
    acts = ax10.fold(acts, ax10.ActionsObserved(state.epoch, state.head, "run-9", 1, "failure", "fp-A"))
    show("after fold", acts)
    for work in ax10.decide(acts):
        show("decide →", work)
    print()
    print("  the same observation is delivered AGAIN (webhook duplicate):")
    dup = ax10.fold(acts, ax10.ActionsObserved(state.epoch, state.head, "run-9", 1, "failure", "fp-A"))
    show("after fold", f"unchanged: {dup == acts}  (monotonic fence — no basis place)")
    print()
    print("  the rerun happened; attempt 2 fails with the SAME fingerprint:")
    acts = ax10.fold(acts, ax10.ActionsObserved(state.epoch, state.head, "run-9", 2, "failure", "fp-A"))
    show("after fold", acts)
    repair_work = ax10.decide(acts)[0]
    show("decide →", repair_work)
    print("  GitHub's attempt counter is the loop variable; no rerun_requested flag.")

    # ------------------------------------------------------------- stage 4
    banner("STAGE 4 — the repair runs on the real Petrus engine (AX3+AX4 blocks)")
    world = fresh_world(head=state.head)
    block = mutation_with_announcement(world)
    lowered = compile_block("es4-walkthrough-net", block)
    transitions = [n.name for n in block.nodes if isinstance(n, BoundaryTransition)]
    print("  the composed block: shape M (prepare → agent → CAS gate)")
    print("  ── committed port ─▶ announce adapter ─▶ comment gate")
    show("entry port", f"{block.entry.place} ({block.entry.color})")
    show("exit ports", {name: p.color for name, p in sorted(block.exits.items())})
    show("context places", dict(block.contexts) or "{} — nothing ambient")
    show("transitions", transitions)
    show("compiled net", f"{len(list(lowered.built.net.places))} places")
    print()
    print(f"  seeding ChangeRequest {{operation: {repair_work.operation!r}, expected_head: 'h1'}}")
    engine, _ = run_block(block, "ChangeRequest", {"operation": repair_work.operation, "expected_head": "h1"})
    [ack] = place_data(engine, block.exits["acknowledged"].place)
    show("exit 'acknowledged'", ack)
    show("branch head now", world["branch"]["head"])
    show("comment marker", world["comments"][0]["marker"])
    new_head = world["branch"]["head"]
    print()
    print("  (variant) someone pushed first — the CAS gate classifies itself:")
    raced = fresh_world(head="h2-someone-pushed")
    rblock = mutation_with_announcement(raced)
    rengine, _ = run_block(rblock, "ChangeRequest", {"operation": repair_work.operation, "expected_head": "h1"})
    [moved] = place_data(rengine, rblock.exits["moved"].place)
    show("exit 'moved'", moved)
    show("comments posted", raced["comments"])
    show("branch touched by us", "no")

    # ------------------------------------------------------------- stage 5
    banner("STAGE 5 — the control loop closes as data (AX6+AX7), lineage carried (AX10)")
    acts = ax10.fold(
        acts,
        ax10.RepairSettled(
            state.epoch, state.head, repair_work.operation, ok=True, provisional_head=new_head, fingerprint="fp-A"
        ),
    )
    show("actions concern", acts)
    show("control_move", ax10.control_move(acts))
    state, actions = step(state, CommitGateFired(new_head))
    show("control state", state)
    print()
    print("  while quiescent, a human asks for another change — and a question:")
    show("service('change')", service(state, "change"))
    show("service('reply')", service(state, "reply"))
    print()
    print(f"  the webhook arrives: head is {new_head!r} — our own push, confirmed:")
    state, actions = step(state, ObservedOpen(new_head))
    show("control state", state)
    show("actions", actions)
    acts = ax10.resume(acts, state.epoch, state.head)
    show("actions after resume", acts)
    print()
    print("  next generation: CI fails AGAIN with the same fingerprint fp-A —")
    print("  the lineage fence sends it to the human rung, not another repair:")
    acts = ax10.fold(acts, ax10.ActionsObserved(state.epoch, state.head, "run-12", 1, "failure", "fp-A"))
    acts = ax10.fold(acts, ax10.ActionsObserved(state.epoch, state.head, "run-12", 2, "failure", "fp-A"))
    show("after folds", acts)
    show("decide →", ax10.decide(acts))
    show("needs_human", ax10.needs_human(acts))

    # ------------------------------------------------------------- stage 6
    banner("STAGE 6 — the green path to readiness (AX8): fold, decide, gate, fold")
    print("  suppose instead the repair fixed it. The concerns settle one by")
    print("  one; each exit folds; decide() runs after every fold:")
    snap = ax8.Snapshot(epoch=state.epoch, head=state.head)
    exits = [
        ax8.ActionsSettled("flaky_green"),
        ax8.ReviewSettled("clear", 0),
        ax8.FindingsPublished(),
        ax8.HumanSettled(approved=True, changes_requested=False, unresolved_conversations=0),
    ]
    for exit_value in exits:
        snap = ax8.fold(snap, exit_value)
        show(f"fold {type(exit_value).__name__:<24}", f"gates_ready={ax8.gates_ready(snap)}  decide={ax8.decide(snap)}")
    print()
    print("  gates are ready but the dashboard is stale → dashboard first,")
    print("  announce only after its acknowledgment folds:")
    [dashboard_work] = ax8.decide(snap)
    show("emitted", dashboard_work)
    snap = ax8.fold(snap, ax8.DashboardAcknowledged(dashboard_work.projection))
    show("fold DashboardAcknowledged", f"is_ready={ax8.is_ready(snap)}  decide={ax8.decide(snap)}")
    [_announce_work] = ax8.decide(snap)
    snap = ax8.fold(snap, ax8.AnnouncementAcknowledged())
    show("fold AnnouncementAck…", f"decide={ax8.decide(snap)}  — settled; announce-once = snapshot lifetime")
    print()
    print("  commutativity across independent concerns (same four exits,")
    print("  reversed arrival order):")
    reversed_snap = ax8.Snapshot(epoch=state.epoch, head=state.head)
    for exit_value in reversed(exits):
        reversed_snap = ax8.fold(reversed_snap, exit_value)
    forward_snap = ax8.Snapshot(epoch=state.epoch, head=state.head)
    for exit_value in exits:
        forward_snap = ax8.fold(forward_snap, exit_value)
    show("same snapshot", reversed_snap == forward_snap)

    # ------------------------------------------------------------- stage 7
    banner("STAGE 7 — time as typed ingress (AX9): the scheduler is a provider")
    tsnap = ax9.Snapshot(
        epoch=state.epoch,
        head=state.head,
        started_at=1_000.0,
        actions="flaky_green",
        review="clear",
        dashboard_current=True,
    )
    show("decide →", ax9.decide(tsnap))
    print()
    print("  the scheduler delivers TimerDue — early (its fault), then on time:")
    early = ax9.fold(tsnap, ax9.TimerDue(state.epoch, state.head, 0, at=2_000.0))
    show("early delivery", f"unchanged: {early == tsnap}  (at < due_at — our truth, not the scheduler's)")
    tsnap = ax9.fold(tsnap, ax9.TimerDue(state.epoch, state.head, 0, at=1_000.0 + ax9.DELAY))
    show("on-time delivery", f"timer_matured={tsnap.timer_matured}")
    show("decide →", ax9.decide(tsnap))
    print()
    print("  the reviewer snoozes (AX7 durable note): the DECISION is off,")
    print("  the maturity FACT keeps — resume fires immediately:")
    snoozed = replace(tsnap, reminder_snoozed=True)
    show("snoozed decide", ax9.decide(snoozed))
    show("resumed decide", ax9.decide(replace(snoozed, reminder_snoozed=False)))
    print()
    print("  the reminder publishes; the ack re-arms sequence 1 from the")
    print("  instant the reviewer actually saw:")
    tsnap = ax9.fold(tsnap, ax9.ReminderAcknowledged(0, at=1_500.0 + ax9.DELAY))
    show("after ack", f"sequence={tsnap.timer_sequence} matured={tsnap.timer_matured}")
    show("decide →", ax9.decide(tsnap))

    # ------------------------------------------------------------- stage 8
    banner("STAGE 8 — the human concern is a mirror plus notes (AX12)")
    human = ax12.Human()
    human = ax12.fold_human(human, ax12.HumanObserved(approved=False, reviewer="alice", mergeable=True))
    show("after observation 1", f"reviewer={human.reviewer!r} seq={human.observation_sequence}")
    human = ax12.fold_human(human, ax12.Noted("reassign", assignee="bob"))
    show("after reassign note", f"reviewer={human.reviewer!r}")
    human = ax12.fold_human(human, ax12.HumanObserved(approved=True, reviewer="alice", mergeable=True))
    show("after observation 2", f"reviewer={human.reviewer!r} approved={human.approved}  ← the reassign was CLOBBERED")
    print("  (production parity, flagged OPEN: snooze survives observations,")
    print("  reassign does not — a field-ownership collision, not a spec choice)")
    print()
    print("  dispositions rewrite findings; blocking is recomputed:")
    review = ax12.Review(status="blocking", findings=(ax12.Finding("F1", blocking=True),))
    show("review", review)
    review = ax12.fold_disposition(review, ax12.Disposed("dismiss", frozenset({"F1"})))
    show("after dismiss F1", f"status={review.status!r}  → ReviewSettled{ax12.review_settled(review)}")

    # ------------------------------------------------------------- stage 9
    banner("STAGE 9 — terminal, conversations that outlive it, and replay")
    state, actions = step(state, ObservedClosed(merged=True))
    show("control state", state)
    show("service('reply')", service(state, "reply"))
    show("service('change')", service(state, "change"))
    print()
    print("  replay is a refold — the same exit events rebuild the same")
    print("  snapshot; no live object was ever durable state:")
    replayed = ax8.Snapshot(epoch=forward_snap.epoch, head=forward_snap.head)
    for exit_value in exits:
        replayed = ax8.fold(replayed, exit_value)
    show("refold == original", replayed == forward_snap)
    print()
    print("  one PR, one walkthrough: admission → ladder → real CAS gate →")
    print("  quiescence → confirmed resume → folds → readiness → timer →")
    print("  human → terminal. Zero ambient places, zero flags, zero reads.")


if __name__ == "__main__":
    main()
