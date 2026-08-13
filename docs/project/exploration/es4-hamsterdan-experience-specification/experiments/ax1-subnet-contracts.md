# AX1 — Candidate subnets and secure entry/exit contracts

## Question

Does the verified experience map decompose into subnets with secure
entry/exit contracts — one typed entry, linear work, explicit
domain-outcome exits — with a thin control layer owning all routing?

## Method

Decomposition derived only from [experience-map.md](../experience-map.md)
and boundary evidence. Everywhere a decision was NET-DECIDED in AX0, this
record **re-derives the rule from product intent** and labels it
`DERIVED` — a hypothesis for AX5 to compare against what the topology
actually decided, never a fact.

## Finding 1 — the system has exactly two world-mutation gates

Classifying every activity by disposability collapses the effect surface:

| Class | Members | Discardable? |
| --- | --- | --- |
| Pure | gate predicate, snapshot derivation, digest, intent declarations | always |
| Read-only effect | `actions_discovery`, all lookup-first reads | always |
| Disposable effect | agent invocations (`review`, `conversation` classify, coding agents — no GitHub credential ever reaches them) | until a gate |
| **Comment gate** | `conversation_publish`, `finding_publish`, `dashboard_publish`, `reminder_publish`, `readiness_publish` | committed |
| **Git gate** | CAS ref advance inside `repair`/`change` | committed |

Everything before a gate can be thrown away; everything at a gate shares
one discipline: operation identity + double authority fence +
lookup-first recovery. So a "secure exit" means precisely: *the only way
work becomes world-visible is through one of two gate types.* This is the
formal version of the Navigator's "we can do the work and discard later."

## Finding 2 — two fractal subnet shapes cover most of the system

### Shape P — publication (5 instantiations)

```python
# Investigative pseudocode — ES-004 contract notation.
shape Publication[Req, Res](
    entry=Port("request", Req),          # carries immutable `operation`
    work=[
        fence(authority),                # (epoch, head, base_head, policy_digest)
        lookup_first(marker=(kind, operation, head)),
        post_or_update(),
        fence(authority),                # second read: authority didn't move
    ],
    exits={
        "acknowledged": Port(Res),
        "discarded":    Port(StaleAuthority),      # fence refused
        "blocked":      Port(RecoverableFault),    # 3 retries exhausted, capability failure
        "fault":        Port(NonrecoverableFault), # unknown terminal failure
    },
    retry="internal, bounded (3), classified",
)

conversation_reply = Publication[ConversationPublicationRequest, ...](immutable)
finding_publish    = Publication[FindingPublicationRequest, ...](immutable)
readiness_publish  = Publication[ReadinessCommand, ...](immutable)
reminder_publish   = Publication[ReminderPublicationRequest, ...](immutable)
dashboard_publish  = Publication[DashboardPublicationRequest, ...](mutable_singleton)
```

One contract, five instances, two variants (immutable vs mutable
singleton). `blocked` waits for an explicit `recover_publication` intent —
recovery is a control-layer event entering a fresh occurrence with the
*same* provider-effect identity.

### Shape M — agent mutation (4 instantiations)

```python
shape AgentMutation(
    entry=Port("request", ChangeRequest | RepairRequest),
    work=[
        fence(authority),
        agent_coding(isolated, no_credentials),   # disposable
        validate_patch(host_owned),               # disposable
        git_gate(                                  # THE commit fence
            commit_trailers=(operation, payload_digest),
            cas_ref_advance(fresh_pr_read_before_and_after),
        ),
    ],
    exits={
        "committed":     Port(ProvisionalHead),   # → control layer awaits verification
        "discarded":     Port(BranchMoved),       # CAS lost — not an error
        "not_repairable":Port(ClassifiedFailure),
        "fault":         Port(NonrecoverableFault),
    },
)

repair           = AgentMutation(entry=RepairRequest)                 # from CI failure
change           = AgentMutation(entry=ChangeRequest)                 # human intent
update_base      = AgentMutation(entry=ChangeRequest, merge_base=True)  # activities.py:468
resolve_conflict = AgentMutation(entry=ChangeRequest, merge_base=True)
```

> **Amended by [AX3](ax3-attempt-first.md):** the `fence(authority)`
> steps drawn above are economy, not correctness. The git gate's exact
> CAS is itself the fence — attempt-first shape M needs no authority
> context at all, and `moved` is the gate's own classified outcome.

`committed` is special: its payload is **provisional authority**. The
subnet does not continue past the gate — control freezes effects until
admission verifies the head (`relation="confirmed"` preserves lineage).

> **Amended by [AX6](ax6-unified-quiescence.md):** "provisional
> authority" is not a distinct mechanism the control layer must carry.
> The `committed` payload becomes `Quiescent(expected=head)` — the same
> stopped state as draft dormancy, with one optional field; `confirmed`
> is a pattern match on the next observation, not a fence-checked flag.

## Finding 3 — the full decomposition

```diagram
 webhooks   timers   activity   sweep      CLI
    │          │     terminals    │          │
    ▼          ▼         ▼        ▼          ▼
┌────────────────────────────────────────────────────┐
│ CONTROL LAYER — not a subnet                        │
│ authority & epochs · generation start/stop/commit   │
│ quarantine · discard/restart · routing decisions    │
│ (all DERIVED rules live here)                       │
└──┬───────┬─────────┬──────────┬──────────┬────────┘
   ▼       ▼         ▼          ▼          ▼
 REVIEW   CI-OBS   CONVERSATION  AgentMutation   TIMER/
 subnet   subnet   subnet        (shape M ×4)    REMINDER
   │        │        │ classify──┬── mutation ──▶ shape M
   │        │        │ (1 intent)├── disposition (ack/dismiss/
   │        │        │           │    defer → durable state)
   │        │        │           ├── schedule (snooze/defer→timer)
   │        │        │           └── recover_publication ──▶ P.blocked
   ▼        ▼        ▼                          │
┌────────────────────────────────────────┐      ▼
│ Publication (shape P ×5) — COMMENT GATE │   GIT GATE
└────────────────┬───────────────────────┘      │
                 ▼                               ▼
            acknowledged                  provisional authority
                                          (back to control)
```

### Work subnet contracts (non-fractal ones)

```python
review_production = subnet(
    entry=Port("basis", ReviewRequest),      # authority + diff + lineage + priors
    work=[agent_review(isolated)],           # disposable throughout
    exits={
        "findings":  Port(ReviewResult),     # → finding_publish (shape P)
        "discarded": Port(StaleAuthority),
        "unable":    Port(ClassifiedFailure),# → retry basis in next admission
    },
)

ci_observation = subnet(
    entry=Port("head", Authority),
    work=[actions_discovery()],              # read-only; never trusts webhook status
    exits={"observed": Port(ActionsObservation)},   # green | failed(fingerprint) | pending
)

ci_rerun = subnet(
    entry=Port("failed", ActionsObservation),
    work=[post_rerun_marker(exact_run)],     # comment-gate variant
    exits={"requested": Port(...), "discarded": Port(StaleAuthority)},
)

conversation_classify = subnet(
    entry=Port("admitted", ConversationObservation),
    work=[agent_classify(exactly_one_intent)],       # disposable
    exits={
        "intent":     Port(Intent),                  # 12-way control fan-out
        "unclassified": Port(SafeReply),             # → shape P ("no workflow change")
    },
)
```

### Intent fan-out (control-layer routing table)

| Kind | Routes to | Durable effect |
| --- | --- | --- |
| `reply`, `status` | shape P (reply; status pre-renders gates — boundary-computable, `activities.py:668-700`) | comment |
| `acknowledge`, `dismiss`, `defer` | finding-disposition state change (args: `findings`) | none directly; dashboard digest moves |
| `snooze`, `resume` | timer schedule/cancel | timer |
| `reassign` | human-state change (arg: `assignee`) | none directly |
| `change`, `update_base`, `resolve_conflict` | shape M | git gate |
| `recover_publication` | fresh occurrence of a `blocked` shape-P instance (args: `target`, `operation`) | comment gate |

## Finding 4 — shared exit vocabulary

Answering workbench Q4: five exits are universal vocabulary; everything
else is concern-specific payload.

```text
completed(T)              domain result; control routes onward
discarded(StaleAuthority) authority moved; work dropped; control MAY restart
retryable                 INTERNAL to subnets (bounded, classified) — never
                          crosses a subnet boundary
blocked(RecoverableFault) retries exhausted, capability failure; waits for
                          explicit human recovery
fault(NonrecoverableFault) classified terminal; projected, not retried
```

The Navigator's two idempotency kinds map onto the gates (workbench Q3):

```text
Kind 1 (did it before → skip):    lookup-first at BOTH gates — comment
      markers (kind, operation, head); git head-commit trailers.
Kind 2 (doing it again fails → classify): CAS failure at the git gate =
      "preconditions changed" → discarded (NOT an error). Comment-marker
      payload collision = same identity, different content → fault
      (fails closed). Failure classification converts provider failures
      into domain exits.
```

## Finding 5 — control layer answers (workbench Q1, Q2)

**Q1: admission/generation lifecycle is the control layer itself**, not a
subnet. Evidence: it has no provider effects of its own (generation
start/stop/commit are history events), it owns every DERIVED decision,
and every subnet's `discarded` exit returns to it. Its size is a design
budget: everything in it is routing, so a fat control layer = spread
control state, which is the exact smell that motivated ES-004.

**Q2: the dashboard derives from a snapshot, it does not subscribe to
exits.** Boundary evidence decides this: dashboard currency is relational
— current concern digest must equal the acknowledged projection
(`contracts/readiness.py:675-714`). So the contract is:

```python
dashboard_projection = subnet(
    entry=Port("digest_moved", ReadinessSnapshot),  # DERIVED trigger: digest ≠ acknowledged
    work=[render(snapshot)],                         # pure
    exits={"publish": Port(DashboardPublicationRequest)},  # → shape P (singleton)
)
```

## DERIVED decision rules (hypotheses for AX5)

Product-intent re-derivations of AX0's NET-DECIDED list. Each is a
falsifiable claim to compare against topology in AX5:

| # | Rule (DERIVED) | Rationale |
| --- | --- | --- |
| D1 | Review is requested on every generation start (`new`, `resumed`, `superseded`) and on `confirmed` only with preserved lineage | review binds to exact head archive; a new head invalidates prior evidence |
| D2 | Discard-then-restart: every `discarded` exit at generation supersession re-enters the subnet under new authority, except conversation replies (stale question ≠ current question) | simplicity-over-saved-work doctrine |
| D3 | Failed CI → rerun first if fingerprint suggests flake (same fingerprint twice → repair); repair is policy-gated | rerun is cheap and advisory; repair mutates the branch |
| D4 | `ReadinessCommand` is emitted by the control layer on the gate predicate's false→true transition, at most once per epoch | predicate is pure and boundary-computable; once-per-epoch preserves immutable-publication semantics |
| D5 | Dashboard publication is requested whenever concern digest ≠ acknowledged projection and no request is outstanding | directly encoded in relational currency |
| D6 | Reminder timers are created by `defer`/`snooze` and by a policy cadence for idle human review; maturation emits exactly one request per (operation, sequence) | boundary evidence: sequence field in `ReminderPublicationRequest` |

## Conclusion

**Promising; continue.** The experience decomposes into a thin control
layer plus ~7 subnet shapes, two of which (P ×5, M ×4) cover 9 of the 11
activities — strong fractality. Every subnet is linear inside; all
branching lives at control-layer fan-outs and at classified exits. The
two-gate finding gives "secure exit" a precise meaning.

Next: AX2 linearizes **review production → finding publication** (mostly
disposable, one comment gate, clean discard story) as an ES-003 block
chain; AX3 then attaches fencing/discard semantics to shape M where the
git gate makes them hardest.
