"""ES-004 AX5 — the divergence sweep, as an executable inventory.

Every read arc in the production net (`readiness/net/topology.py`,
via ``build_net()``) is assigned to exactly one category; each
category names the experiment whose evidence displaces it — or the
honest classification when nothing does. The test suite asserts the
inventory is COMPLETE (no read arc unaccounted for) and that the
category populations match the tables in the experiment document, so
the document's numbers cannot drift from the net.

Categories:

    C1_STALENESS   fences that detect "this token belongs to a dead
                   generation / superseded operation" — the accept_*
                   currency guards, the result-envelope retirements,
                   the basis retirements, and the admission
                   retirements. Displaced by AX3 (attempt-first: the
                   operation is the fence) + AX6 (epoch+1 on resume
                   makes drained tokens inert). ACCIDENTAL.

    C2_AUTHORIZE   in-flight serialization and work authorization —
                   change_in_flight, first-failure rerun, repairable.
                   Structure displaced by AX4 (control-state
                   consequence) and typed classify outcomes; the
                   DOMAIN RULES inside the guards are preserved as
                   classification logic. ACCIDENTAL (structure),
                   rules kept.

    C3_CONVERSATION authority/cohort coupling of the conversation
                   concern — classification start reads the whole
                   cohort, intents carry epoch/head, replies and
                   recovery re-check authority. Displaced by AX7
                   (effect grades; only head_bound work enters the
                   machine). ACCIDENTAL.

    C4_PROJECTION  relational joins that compute derived state —
                   dashboard request, readiness announcement, and
                   reminder due-ness each read 8-9 concern places.
                   The PROJECTION IS A REAL REQUIREMENT (the product
                   core); the marking-join is one mechanism, a
                   control-layer fold over subnet exits is another.
                   OPEN — and the reminder/timer concern was never
                   spiked (MISSED in the ES-004 series).

    C5_ADMISSION   the same-head basis-delta refresh reading
                   review_state. Displaced by AX6 (in-generation
                   deltas fold at the control layer). ACCIDENTAL.
"""

from __future__ import annotations

C1_STALENESS = "C1_STALENESS"
C2_AUTHORIZE = "C2_AUTHORIZE"
C3_CONVERSATION = "C3_CONVERSATION"
C4_PROJECTION = "C4_PROJECTION"
C5_ADMISSION = "C5_ADMISSION"

# transition name (as built) -> category owning ALL of its read arcs
CATEGORY: dict[str, str] = {
    # -- C1: currency fences on accepted results/observations --------------------
    "accept_actions": C1_STALENESS,
    "accept_change": C1_STALENESS,
    "accept_conversation": C1_STALENESS,
    "accept_dashboard": C1_STALENESS,
    "accept_finding": C1_STALENESS,
    "accept_human": C1_STALENESS,
    "accept_readiness": C1_STALENESS,
    "accept_reminder": C1_STALENESS,
    "accept_repair": C1_STALENESS,
    "accept_review": C1_STALENESS,
    # -- C1: result envelopes retired against dead operations --------------------
    "retire.actions_operation": C1_STALENESS,
    "retire.change_operation": C1_STALENESS,
    "retire.conversation_operation": C1_STALENESS,
    "retire.dashboard_operation": C1_STALENESS,
    "retire.finding_operation": C1_STALENESS,
    "retire.readiness_operation": C1_STALENESS,
    "retire.repair_operation": C1_STALENESS,
    "retire.review_operation": C1_STALENESS,
    # -- C1: queued bases retired when stale --------------------------------------
    "retire.actions_basis": C1_STALENESS,
    "retire.change_basis": C1_STALENESS,
    "retire.conversation_basis": C1_STALENESS,
    "retire.reply_basis": C1_STALENESS,
    "retire.recovery_basis": C1_STALENESS,
    # -- C1: admissions retired against lifecycle owners --------------------------
    "retire.seed_admission": C1_STALENESS,
    "retire.dormant_admission": C1_STALENESS,
    "retire.active_admission": C1_STALENESS,
    "retire.terminal_admission": C1_STALENESS,
    # -- C2: serialization flags and work authorization ---------------------------
    "authorize_change": C2_AUTHORIZE,
    "authorize_rerun": C2_AUTHORIZE,
    "authorize_repair": C2_AUTHORIZE,
    # -- C3: the conversation concern's authority coupling ------------------------
    "start_conversation": C3_CONVERSATION,
    "accept_finding_intent": C3_CONVERSATION,
    "accept_reminder_intent": C3_CONVERSATION,
    "authorize_reply": C3_CONVERSATION,
    "recover_publication.conversation": C3_CONVERSATION,
    "recover_publication.dashboard": C3_CONVERSATION,
    "recover_publication.readiness": C3_CONVERSATION,
    # -- C4: derived-state projections over the cohort ----------------------------
    "request_dashboard": C4_PROJECTION,
    "authorize_readiness": C4_PROJECTION,
    "reminder_due": C4_PROJECTION,
    # -- C5: same-head basis refresh ----------------------------------------------
    "refresh_admission": C5_ADMISSION,
}

# the classification each category carries in the AX5 tables
CLASSIFICATION: dict[str, str] = {
    C1_STALENESS: "ACCIDENTAL (AX3 attempt-first + AX6 epoch drain)",
    C2_AUTHORIZE: "ACCIDENTAL structure (AX4); domain rules preserved as classify steps",
    C3_CONVERSATION: "ACCIDENTAL (AX7 effect grades)",
    C4_PROJECTION: "OPEN mechanism; the projection requirement is real — timers unspiked (MISSED in series)",
    C5_ADMISSION: "ACCIDENTAL (AX6 in-generation delta fold)",
}

# expected read-arc population per category, asserted against build_net()
EXPECTED_READS = {
    C1_STALENESS: 42,
    C2_AUTHORIZE: 5,
    C3_CONVERSATION: 21,
    C4_PROJECTION: 25,
    C5_ADMISSION: 1,
}
