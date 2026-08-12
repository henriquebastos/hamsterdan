# Subnet candidates — entry/exit contract drafts

Candidate concerns that might each be one secure subnet: a single typed
entry, linear work, explicit domain-outcome exits, authority at the entry
or commit fence. All entries are **hypotheses** pending AX1; contracts use
the investigative pseudocode from [index.md](index.md).

## Candidate inventory (seed)

| # | Concern | Effects used | Purity guess | Discard-safe? |
| --- | --- | --- | --- | --- |
| 1 | Review generation & finding publication | `review`, `finding_publish` | agent call effectful, result disposable | yes — recompute on new head |
| 2 | CI observation & rerun | `actions_discovery`, `actions_rerun` | read + marker post | yes |
| 3 | CI repair | `repair` (+ git publish) | effectful at commit fence only | yes until fence |
| 4 | Conversation handling | `conversation`, `conversation_publish` | classify pure-ish; reply effectful | classify yes; reply no |
| 5 | Intent execution (`change`, `update_base`, …) | `change` (+ git publish) | effectful at commit fence | yes until fence |
| 6 | Dashboard projection | `dashboard_publish` | derive pure; publish idempotent singleton | derive yes |
| 7 | Reminders | `reminder_publish` | timer-driven, effectful | n/a |
| 8 | Readiness advisory | `readiness_publish` | decision pure; publish immutable | decision yes |
| 9 | Admission / generation lifecycle | none (pure routing?) | control layer, maybe not a subnet | — |

## Contract drafts

### Candidate 1 — review generation (draft)

```python
subnet(
    name="review_generation",
    entry=Port("admitted_head", Authority),        # enter with authority
    exits={
        "published": Port("findings", FindingPublicationResult),
        "discarded": Port("stale", Authority),     # head moved; drop work
        "failed": Port("error", ClassifiedFailure),
    },
    authority="checked at entry AND at finding_publish fence",
    purity="agent call effectful but disposable until publish",
    effects=("review", "finding_publish"),
)
```

### Candidate 3 — CI repair (draft)

```python
subnet(
    name="ci_repair",
    entry=Port("failed_checks", ActionsObservation),
    exits={
        "committed": Port("advanced", ChangeResult),
        "discarded": Port("branch_moved", Authority),   # CAS lost → restart
        "not_repairable": Port("terminal", ClassifiedFailure),
    },
    authority="commit fence: CAS ref advance + trailer lookup-first",
    purity="everything before the commit fence is disposable",
    effects=("repair",),  # git publish inside repair activity
)
```

## Workbench — decomposition questions

| # | Question | Status |
| --- | --- | --- |
| 1 | Is admission/generation lifecycle a subnet or the control layer itself? | open |
| 2 | Does dashboard projection subscribe to every other subnet's exits, or derive from a snapshot? | open |
| 3 | Where do the two idempotency kinds (skip vs classify-failure-as-done) each appear? | open |
| 4 | Which exits are shared vocabulary (`discarded`, `retryable`, `terminal`) vs concern-specific? | open |
| 5 | | |
