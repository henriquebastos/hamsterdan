# Experiment 7 — Bounded-step contract

Session S7. Durable inputs: the ES-010 index and the ruled Phase B records,
[`03-workflow-shape.md`](03-workflow-shape.md),
[`04-ports-adapters.md`](04-ports-adapters.md),
[`05-readiness-tree.md`](05-readiness-tree.md), and
[`06-host-narrowing.md`](06-host-narrowing.md). Source and targeted tests were
inspected at `88ada99`; that commit is both local `main` and `origin/main` and
records the R2 ruling. The installed Petrus revision inspected through the
project pin is `44cac5ff48ac371ebae56323941983f30db13c0d`.

Method: inventory every current loop that can advance semantic state or hide a
recovery boundary; name the smallest durable, external-effect, and read-only
reconstruction cuts; map maintained crash/recovery evidence in the ruled
workflow/readiness/host route to those cuts; and derive bounded production
drivers and fairness obligations from the same public steps. The R2 workflow,
ports/adapters, readiness, and host trees are inputs, not questions reopened
here. the engineering style contract is not an input.

## Verdict

The replacement architecture needs one result vocabulary and three nested
drivers:

```text
workflow runtime step   one Petrus action or one bounded reconstruction action
          ▲
          │
readiness step          one ingress, workflow, timer, Activity, wake, or route cut
          ▲
          │
host step               one scheduler/custody cut or one delegated readiness step
```

A **bounded step** advances at most one PR subject across exactly one named
semantic cut. It also has explicit limits for rows, bytes, external calls, and
elapsed execution. A call that performs one logical action by scanning
unbounded History is not bounded. A call that caps an outer loop while invoking
an inner drain is not bounded either.

`Progressed` always identifies the cut just crossed. `Waiting` identifies the
outside condition that can make retained work eligible. `Quiescent` means no
retained work is eligible and no retained obligation has a known wake; it is
not workflow completion. `Terminal` means the workflow lifecycle is terminal
and readiness has no local terminal settlement left. `Unavailable` reports a
closed, secret-free inability to take a step; it never fabricates a workflow
terminal.

The contract deliberately exposes effect return before Activity terminal
recording. This is the cut currently reached only with custom Dispatch objects
or method replacement: an effect may have landed while its Motus terminal was
lost. The returned value is observation, not authority. On process loss,
reconstruction repeats the same operation lookup-first from durable Dispatch,
provider/agent operation ledgers, and readiness custody. No generator frame or
Python object is required for recovery.

S7 does **not** choose an explicit loop, trampoline, or generator. S8 must prove
which mechanism realizes these cuts without making a continuation frame
authoritative. R3 remains unruled.

## Current drain and hidden-loop inventory

The current caps are useful failure detectors, but they do not define one step.
Several multiply one another or wrap unbounded scans.

| Current path | Work hidden in one call | Bound today | Contract consequence |
|---|---|---:|---|
| Petrus `Engine.advance()` after load | Before its normal `AcceptResult`, `AcceptDelivery`, `BeginCandidate`, `AdvanceTime`, `Wait`, or `Stop` action, `_reconcile()` can inspect every in-flight occurrence, redispatch every unresolved Activity, project frozen outcomes, finish pure occurrences, and repair cancellation | retained in-flight set, not a caller budget | Opening/reconstruction must page History and repair at most one occurrence per returned step before normal workflow stepping |
| Petrus normal `Engine.advance()` | One policy action; a pure `BeginCandidate` begins and completes one firing, while an impure candidate records and dispatches one request | one coordinator action | This remains the atomic workflow action. Readiness must report its action kind and occurrence instead of hiding it in a drain |
| Petrus `InlineDispatch` | Executes the effect synchronously inside impure `BeginCandidate`; its execution policy may retry internally | `ExecutionPolicy.attempts` | Production effects cannot remain hidden in workflow advancement. Request, effect return/interruption, and terminal recording are separate readiness cuts |
| `V5Runtime.drain()` | Calls `_settle_agent_routes()`, then advances and rescans all History after every action until `ready` is false | 500 actions | Replace with one workflow action or one route settlement. Current shape is up to 500 full-history scans per call |
| `V5Runtime._settle_agent_routes()` and runtime projections | Rebuild requested/terminal maps by scanning all records; timer and wake validation also scans retained History | all History records | Replace with incremental posture and paged reconstruction bounded by records and bytes |
| `PrReadinessV5Application._deliver_manifest()` | Delivers and lifecycle-folds every manifest entry | manifest length | Stage has an admission limit; each entry acceptance and fold is a separate step in canonical order |
| `PrReadinessV5Application.settle()` | Up to 500 iterations; each first calls the 500-action runtime drain, then may deliver both deferred wakes, or process an ack, command, maturity, or due timer | nominally 500 × 500 workflow actions | Worst-case shape is 250,000 workflow actions plus other work. Replace with one readiness cut per call |
| `_wake_deferred()` | Can deliver review and announcement wakes in one call; each validation scans History | two deliveries plus History | Select and accept at most one wake identity per step; fold it through the ordinary ingress step |
| `V5TimerStore.apply/pending_ack/pending_maturity/claim_due` | Live mutations are one transaction and pending/claim queries select one row; opening and rebuild iterate accepted timer History and retained rows | one live row; reconstruction unpaged | Preserve one-row live cuts; page and byte-bound reconstruction. History acceptance and local delivered markers stay separate |
| Petrus `Worker.run_available()` | Claims and executes until the requested limit; each `_execute()` combines claim, effect call, serialization, and terminal report | caller limit | `limit=1` is still three crash-relevant cuts. Expose claim, effect return/interruption, and terminal report |
| `LocalWorkerDispatch.claim()` | Before one claim it terminalizes every exhausted eligible row | eligible exhausted rows | Exhaustion repair must page or terminalize one occurrence per step |
| `HostService.project_pending()` | Scans and projects pending custody | 1,000 rows | Make custody projection one row, or one explicitly paged read-only batch with no readiness progress |
| `HostService._activate_instance()` | Loads up to 1,000 rows, processes the batch, then repeatedly picks up newly arrived rows; each row can process a whole manifest; activation also settles | initial pages capped; arrival loop unbounded | One host service turn invokes one readiness step for one selected subject. Newly arrived custody joins a later turn |
| `HostService.run_due()` | Claims up to 100 subjects and activates each; a failed subject is immediately re-woken | 100 subjects, but each activation unbounded | A turn has a distinct-subject budget and one readiness call per subject. Failure/re-wake goes behind already-due work |
| `HostService.pump()` | Projects custody, runs due subjects, executes up to 20 Activities, settles after terminals, then scans every loaded instance for publication repair | 1,000 custody + 100 subjects + 20 Activities; nested drains and loaded-instance scans | Express as bounded host steps. No pump stage gets a private whole-system drain |
| `HostService.sweep()` and `work_state()` | Glob every retained History path and sometimes open/activate each | all retained paths | S6's catalog is paged. Inspection and reconstruction have count and byte budgets |
| `process_one()` / `run_one_activity()` | Publicly say “one,” but call `_activate_instance()` or post-Activity `settle()` | one outer item only | They do not satisfy S7. The inner readiness call must itself return after one cut |
| worker loop and shutdown settlement | Poll forever; shutdown iterates every loaded application and calls `settle()` | process lifetime / loaded set | The process loop remains long-lived, but every occurrence is a bounded turn. Shutdown is paged and budgeted, with abort preserving semantic state |
| current deterministic `advance_time()` / `converge()` | Step until target time or until no pending action | DST global budget only; no local call budget | Convenience methods must accept a local budget and use the production step result; exhaustion is an explicit outcome |

The timer store's quarantine-name search is finite in practical stores but also
needs a directory-entry bound. It is startup storage hygiene, not semantic
scheduler progress. Likewise SQL statements inside one atomic transaction do
not become separate semantic cuts merely because there are several statements.

## Boundedness rules

Every target step satisfies all of these rules:

1. **One owner and subject.** It is owned by workflow runtime, one readiness
   lifecycle, or host supervision, and affects at most one PR subject. Host-only
   catalog and custody steps may select a subject but do not advance another.
2. **One semantic cut.** It crosses at most one named durable or external-effect
   boundary. Read-only reconstruction may consume one named page and returns
   that page cut.
3. **Finite resources.** Input bytes, output bytes, rows examined, records
   decoded, operation identities returned, external calls, and wall-clock
   execution all have finite admission or per-call limits.
4. **No hidden retries.** A step may perform the fixed lookup/fence/effect
   sequence ruled for one S4 operation, including at most one effect attempt.
   Retry, backoff, another Activity Attempt, or another subject requires another
   step.
5. **Durable reconstruction.** After any returned cut, a fresh process derives
   its next eligible step from History, Dispatch, readiness custody, host
   custody/catalog, and stable operation ledgers. Volatile continuations may
   avoid a repeated lookup but are never the only authority.
6. **Exact identity.** Every delivery, occurrence, timer, effect, route, and
   scheduler turn in a result carries its stable identity and generation where
   applicable. Payloads, credentials, and raw errors do not travel in results.
7. **Cancellation and deadline.** An external call has a declared timeout or
   cancellation policy. A step cannot remain an uninterruptible scheduler
   lease.
8. **Loud contract failure.** Corrupt identity, cardinality, ordering, or
   retained state fails closed. `Unavailable` is for classified inability, not
   a way to normalize corruption or an unexpected bug.

Semantic boundedness and computational boundedness are independent. For
example, rebuilding one timer state from an unbounded History is one semantic
operation but not a bounded step; it must return after one reconstruction page.

## Shared result values

These are ownership and value-shape pseudocode, not a choice of Python
`Protocol`, class hierarchy, or driver mechanism.

```text
CutRef:
  owner                 workflow | readiness | host
  kind                  one closed cut name from the tables below
  subject               PR subject, or none for a host catalog page
  identity              delivery / occurrence / operation / timer / turn, or none
  generation            lifecycle, timer, attempt, or route generation when relevant

StepResult = Progressed | Waiting | Quiescent | Terminal | Unavailable

Progressed:
  cut: CutRef            exactly one returned cut
  posture: WorkPosture
  admission: DeliveryPosture | none
  settled_agent_routes: tuple[OperationId, ...]  # zero or one in a progress step

Waiting:
  wait: WaitDisposition
  posture: WorkPosture

Quiescent:
  posture: WorkPosture

Terminal:
  lifecycle_generation
  reason                 closed | merged
  posture: WorkPosture   # proves no local terminal settlement is eligible

Unavailable:
  error_class            closed, bounded, secret-free classification
  retryable
  eligible_at_us         required for a timed retry; otherwise none
  posture: WorkPosture
```

`WorkPosture` is detached and bounded. It states whether another local step is
eligible now, the primary wait if one exists, the next deadline in integer
microseconds, whether one host delivery remains in readiness admission, and a
bounded count—not payloads—of retained workflow, Activity, timer, and route
items. Host may persist this as a reconstructible hint. Canonical state remains
with the owning stores.

`DeliveryPosture` is `pending(delivery)`, `accepted(delivery)`, or
`already_accepted(delivery)`. The last two appear only after every frozen entry
for that delivery is accepted and folded in canonical order. Host acknowledges
its inbox row only after either accepted posture is returned.

### Wait and quiescence dispositions

```text
WaitDisposition =
  activity_terminal(operation, occurrence, eligible_at_us?)
  timer_deadline(timer, due_at_us)
  host_custody(delivery, custody_generation)
  lifecycle_change(route_generation, custody_generation)
  external_observation(subject)
  retry_deadline(error_class, eligible_at_us)
  stop_requested
```

- `activity_terminal` means a requested Activity has no eligible terminal or
  retry now. It does not claim that the external provider is idle.
- `timer_deadline` is the earliest exact readiness timer. Host may project it
  into the runnable hint store without owning timer custody.
- `host_custody` and `lifecycle_change` retain the exact blocker/generation that
  must change before a deferred workflow operation can resume.
- `external_observation` names an open workflow obligation whose next event has
  no known time, such as human or provider evidence.
- `retry_deadline` is used only for classified bounded retry policy. Immediate
  failure requeue is not allowed to leapfrog already-due work.
- `stop_requested` prevents new effects while allowing later bounded terminal
  settlement or abort.

`Quiescent` is narrower than “waiting for something”: there is no internally
eligible cut, retained Activity, timer, custody/lifecycle blocker, retry, or
known workflow observation obligation. A future external admission may still
create work. `Terminal` is narrower still: the workflow has reached closed or
merged lifecycle and all already-created local terminals, blocked outcomes,
timer markers, and route settlements have been processed.

Multiple simultaneous waits remain in bounded inspection posture, but one
deterministically selected primary wait drives scheduling. Selection uses exact
deadline first, then stable kind and identity order; it does not erase the
other retained obligations.

## Workflow runtime step contract

The workflow package remains pure and has no second scheduler. As ruled in S3,
readiness and workflow simulation adapt Petrus through `readiness/runtime.py`.
One ordinary workflow step is exactly one normal Petrus coordinator action.

| Workflow cut | Work allowed before return | Result evidence |
|---|---|---|
| `history_page_replayed` | Decode and validate at most `history_records_per_page` and `history_bytes_per_page`; no Dispatch or effect call | page cursor, records and bytes consumed |
| `occurrence_repaired` | For one retained occurrence, perform exactly one redispatch, frozen-terminal projection repair, pure-completion repair, or cancellation repair | occurrence, repair kind, stable Activity operation when present |
| `observation_accepted` | Call one identified Engine delivery door for one token tuple already admitted by readiness | source, delivery identity, History position/generation |
| `observation_folded` | Target and commit one lifecycle fold for the accepted observation | source, delivery identity, firing occurrence |
| `workflow_action_committed` | Call one normal `Engine.advance()` after reconstruction is complete | action kind (`pure_firing`, `activity_requested`, `activity_terminal_projected`, `time_advanced`), transition and occurrence where applicable |

`Wait` and `Stop` coordinator actions do not become fake progress cuts. They map
to `Waiting`, `Quiescent`, or `Terminal` from durable state. A pure firing may
begin and complete inside one Petrus action because that is one atomic workflow
decision. An impure firing may commit one `ActivityRequested` and its Dispatch
publication as the one action; the effect itself cannot run inline.

Current Petrus does not fully meet the reconstruction contract: the first
`advance()` after load calls `_reconcile()` across all in-flight occurrences
before applying one normal action. S8 must determine whether a public Petrus
reconstruction cursor can supply `history_page_replayed` and
`occurrence_repaired`, or whether the readiness runtime must use a bounded
provider composition that Petrus explicitly supports. Calling the current
first `advance()` and relabeling it “one step” is not acceptable.

The workflow step result exposes no Net marking, mutable Engine, Dispatch
handle, History store, selection callback, or private occurrence object.
Workflow simulation seeds through S3's public values, invokes these runtime
steps, and observes detached workflow projections.

## Readiness step contract

`ReadinessLifecycle.admit(delivery, lifecycle_evidence)`,
`progress(reason, lifecycle_evidence)`, and `settle_terminal()` return the
shared `StepResult`. `admit` is repeated across host turns if one frozen
manifest has several entries; it never drains the manifest. `progress` chooses
one eligible lane. `settle_terminal` uses the same cuts but forbids claiming a
new external effect.

### Readiness cuts

| Readiness cut | One-step work | Recovery boundary exposed |
|---|---|---|
| `ingress_staged` | Recover an existing manifest or project, optionally classify one bounded conversation operation, then atomically store one bounded immutable manifest plus grant | before stage / after manifest+grant commit / before first History delivery |
| `ingress_entry_accepted` | Accept the next frozen manifest entry through `observation_accepted` | after History acceptance / before lifecycle fold |
| `ingress_entry_folded` | Fold the next accepted manifest entry through `observation_folded`; last fold may return `accepted` or `already_accepted` delivery posture | after fold / before host inbox acknowledgement |
| `runtime_reconstructed` | Replay one History page or repair one retained occurrence through the workflow runtime contract | restart repair is observable one item at a time |
| `workflow_advanced` | Apply one `workflow_action_committed` | one pure decision, request, terminal projection, or time action |
| `activity_attempt_claimed` | Claim one exact Motus Attempt; exhaustion repair, if needed, consumes its own reconstruction step | after durable claim / before effect invocation |
| `activity_effect_observed` | Perform the operation's fixed lookup/fence sequence and at most one external effect or agent call; return whether a terminal value was obtained or the attempt was interrupted/ambiguous | effect may have landed / no Activity terminal recorded yet |
| `activity_terminal_recorded` | Serialize and report one previously observed typed result or classified failure to Dispatch | terminal durable in Dispatch / not yet projected by workflow |
| `timer_command_applied` | Apply one exact outstanding workflow timer command transactionally | command result durable / ack not accepted in History |
| `timer_ack_accepted` | Accept the oldest pending command acknowledgement into History | ack in History / local delivered marker absent |
| `timer_ack_marked` | Mark that exact command result delivered in timer custody | marker durable / workflow fold may remain |
| `timer_maturity_claimed` | Claim and persist the earliest due `(due_at_us, timer_id)` | maturity durable / not accepted in History |
| `timer_maturity_accepted` | Accept the oldest persisted maturity into History | due fact in History / local delivered marker absent |
| `timer_maturity_marked` | Mark that exact maturity delivered in timer custody | marker durable / workflow fold may remain |
| `deferred_wake_accepted` | Under fresh lifecycle evidence, accept one exact review or announcement wake; its fold is the ordinary ingress fold cut | wake in History / deferred baton not yet folded |
| `agent_route_settled` | Report one operation identity whose workflow terminal is settled under R2 semantics | readiness interpretation complete / host route posture not yet persisted |

`activity_effect_observed` is an effect cut even when no local write occurred.
Its identity and detached disposition are public so simulation can crash after
the returned call. If the process continues, the next readiness step records
the terminal. If it dies, a fresh runtime does not trust the lost result: after
lease/retry eligibility, the same S4 adapter reconciles lookup-first and returns
the same classified terminal without repeating the effect. A volatile
continuation may carry the result between adjacent calls, but deletion of that
continuation must only cause lookup-first replay. S8 must prove this invariant
for its mechanism.

The conversation operation is different: S4 ruled that its result is frozen in
the immutable manifest before workflow delivery and that it has no provider
effect. One `ingress_staged` step may therefore perform at most one bounded
conversation call followed by the atomic manifest/grant commit. A crash before
commit reuses the stable conversation operation; a crash after commit bypasses
reclassification.

### Readiness eligibility and ordering

Correctness dependencies override lane fairness:

1. Complete bounded reconstruction before any fresh provider read or normal
   workflow action.
2. Preserve one manifest's canonical entry order: stage, accept entry, fold
   entry, then move to the next entry.
3. Do not claim an Activity effect while host lifecycle evidence reports
   pending same-subject custody. Route revocation follows R2: readiness creates
   the workflow-declared blocked outcome from lifecycle evidence; host does not
   decode work or fabricate it.
4. Report an already-observed Activity terminal before claiming another
   Attempt. Project a terminal through a later workflow step.
5. Deliver the oldest pending timer acknowledgement before applying another
   command or claiming maturity. Deliver a persisted pending maturity before
   claiming another due timer.
6. Mark a timer fact only after its exact History acceptance. Fold it through
   the ordinary workflow cut after acceptance.
7. Deliver at most one eligible deferred wake and one agent-route settlement
   per step.

Among lanes not ordered by these dependencies, readiness uses a deterministic
weakly fair cursor over ingress, workflow, Activity, timer, wake, and route
lanes. The cursor is durable or reconstructible from durable sequence; it is
not a process-local iterator. A continuously eligible lane is selected within
at most the number of eligible lanes after higher-priority dependency work
becomes finite.

## Host step contract

Host owns a durable fair-turn state machine. One raw host step crosses one cut;
one **service turn** is the bounded sequence that selects one subject, delegates
at most one readiness step, records its detached result, and then releases or
requeues that subject. Production may hold several selected subjects in one
turn batch, but each receives at most one readiness call before any receives a
second.

| Host cut | One-step work | Recovery boundary exposed |
|---|---|---|
| `catalog_page_inspected` | Read and validate one bounded catalog page or one readiness detached inspection page | startup/sweep cannot hide an all-instance scan |
| `custody_item_disposed` | Classify and terminally dispose one host-owned non-workflow delivery | one inbox row terminalized |
| `subject_selected` | Durably claim one due subject under monotonic fair sequence/cursor | wake selection committed / readiness not called |
| `instance_opened` | Open or reconstruct one selected readiness lifecycle within its construction bounds | bound instance available / no progress call yet |
| `readiness_step_returned` | Call `admit`, `progress`, or `settle_terminal` once and return its nested `CutRef` or non-progress disposition unchanged | readiness cut complete / host posture, route, and inbox writes not yet applied |
| `delivery_acknowledged` | Acknowledge one exact host inbox delivery only from returned accepted/already-accepted posture | readiness accepted / host custody terminal |
| `posture_recorded` | Persist one subject's bounded wake/deadline posture as a reconstructible hint | readiness state durable / runnable hint may previously be absent |
| `agent_route_recorded` | Persist one returned agent-operation settlement | readiness terminal interpreted / process route custody updated |
| `subject_requeued` | Release the selected subject at tail sequence, with retry eligibility when failed | one service turn complete |
| `instance_closed` | Close one readiness lifecycle/resource after bounded terminal settlement or explicit abort | one resource closed; shutdown continues with later subjects |

The host does not transform the nested readiness result. In particular, it
cannot inspect an Activity name, typed work, workflow terminal, History record,
or timer command. If route revocation makes a queued publication blocked, the
nested cut is readiness's workflow/activity progress; host sees only detached
posture and an eventual settled route identity.

A selection lease has a bounded expiry. If the process dies after
`subject_selected`, startup requeues the subject without assuming readiness ran.
If it dies after `readiness_step_returned`, readiness reconstruction observes
its own cut and the host repairs missing posture, route settlement, or inbox
acknowledgement in later host steps.

## Crash and recovery cut matrix

### Inclusion rule

This matrix covers every maintained test that deliberately creates or proves a
crash, restart, reconstruction, accepted-effect ambiguity, lost terminal, or
lookup-first recovery boundary in the current R2 workflow/readiness/host route.
Parameterized cases map to the same row. Tests that merely validate ordinary
idempotency, schema migration, malformed values, setup qualification, Pi
installation/runtime internals, or simulation-framework budget/artifact
bookkeeping are not crash-cut evidence for this contract. The two current World
resource-exhaustion tests are budget-framework evidence and remain inputs to
Exp 9, not workflow/readiness/host cut tests.

The target column names the public returned cut after which a simulation may
invoke `crash()`. “Before” is represented by crashing after the preceding
public result—no callback inside the next operation is needed.

| Current maintained evidence | Current boundary | Target public cut(s) |
|---|---|---|
| `test_manifest_and_authority_grant_commit_together_before_replay`, `test_replay_uses_frozen_manifest_even_when_fresh_projection_differs`, `test_v5_application_stages_grant_before_identified_delivery_and_replays_frozen_manifest` | immutable manifest and grant survive replay as one unit | `ingress_staged` |
| `test_manifest_and_grant_roll_back_as_one_transaction`, `test_reconciliation_manifest_and_grant_roll_back_as_one_transaction` | crash before atomic stage leaves neither manifest nor grant | preceding host/readiness result, then retry `ingress_staged`; there is no half-stage cut |
| `test_v5_application_replays_committed_reconciliation_before_reading_changed_provider_truth`, `test_v5_application_restart_replays_committed_reconciliation_without_provider_reads` | stage committed before first entry delivery | `ingress_staged` → crash → `ingress_entry_accepted` |
| `test_reconciliation_folds_a_final_row_accepted_before_the_prior_host_crashed`, `test_ambiguous_petrus_delivery_reopens_history_before_exact_retry` | entry accepted in History before fold or caller acknowledgement | `ingress_entry_accepted` → crash → `ingress_entry_folded` |
| `test_v5_application_checks_later_history_conflicts_before_replaying_an_earlier_gap`, `test_reconciliation_manifest_and_grant_corruption_fail_closed`, `test_manifest_replay_requires_its_subject_grant`, `test_new_delivery_cannot_replace_a_missing_grant_from_prior_custody` | reconstruction validates complete retained lineage before repair | `history_page_replayed`; invalid page raises a contract failure before any `occurrence_repaired` |
| `test_v5_comment_classification_is_frozen_and_settled_only_after_manifest_commit`, `test_comment_route_settlement_replays_after_crash_following_manifest_commit` | conversation result freezes at stage; route settlement may be lost afterward | `ingress_staged` → crash → `agent_route_settled` |
| `test_v5_publication_recovery_preserves_the_explicit_operation_at_ingress`, `test_v5_publication_recovery_requires_one_bounded_verbatim_operation` | recovery intent must freeze one bounded exact operation before workflow delivery | `ingress_staged` with bounded operation identity |
| `test_v5_announcement_wake_replays_after_restart_when_delivery_ack_is_lost`, `test_v5_review_wake_replays_after_restart_when_delivery_ack_is_lost` | exact wake accepted in History before its caller acknowledges it | `deferred_wake_accepted` → crash → `ingress_entry_folded` |
| `test_v5_restart_fails_closed_on_malformed_review_wake_history`, `test_v5_restart_fails_closed_on_malformed_announcement_wake_history` | reconstruction rejects a wake without its exact deferred predecessor | `history_page_replayed` raises before a wake repair/result |
| `test_exact_arm_replay_preserves_deadline_and_conflicting_payload_fails`, `test_ack_and_maturity_crash_markers_replay_exact_frozen_values` | command or maturity durable in timer custody before History delivery | `timer_command_applied` or `timer_maturity_claimed` |
| `test_timer_ack_crash_cuts_replay_one_identity_and_original_deadline` (`before_history`) | command result persisted, ack absent from History | `timer_command_applied` → crash → `timer_ack_accepted` |
| the same test (`after_history`) | ack accepted in History before timer-custody marker | `timer_ack_accepted` → crash → `timer_ack_marked` |
| `test_timer_maturity_history_marker_crash_replays_without_duplicate_fact` | maturity accepted in History before marker | `timer_maturity_accepted` → crash → `timer_maturity_marked` |
| `test_history_rebuild_recovers_acknowledged_deadline_and_maturity`, `test_history_rebuild_recovers_outstanding_arm_when_its_ack_is_canonical`, `test_semantically_corrupt_deadline_rebuilds_from_canonical_history`, `test_store_missing_new_history_generation_rebuilds_canonical_timer`, `test_pending_cancel_mismatch_rebuilds_before_the_net_command_applies`, `test_failed_history_rebuild_does_not_leave_false_empty_custody` | timer state reconstructs or fails closed from accepted History and one outstanding command | bounded `history_page_replayed`, then zero or more one-row `runtime_reconstructed` results; no provider/effect cut |
| `test_missing_or_corrupt_store_with_unacknowledged_arm_fails_closed`, `test_unacknowledged_arm_failure_preserves_the_database_triplet`, `test_pending_arm_must_equal_the_net_command_and_preserves_its_deadline_on_failure` | an unacknowledged command cannot be fabricated from History | reconstruction returns `Unavailable` or raises corruption failure; no progress cut |
| `test_disposable_runnable_index_rebuilds_from_intact_timer_custody` | host runnable hint can be lost after readiness timer posture is durable | `timer_command_applied`/`timer_ack_marked` → crash → `posture_recorded` |
| `test_review_agent_redispatches_one_frozen_global_operation_without_a_second_agent_execution` | Activity request survives; agent result/effect may occur while terminal is discarded | `workflow_advanced(activity_requested)` → `activity_effect_observed` → crash → lookup-first replay → `activity_terminal_recorded` |
| `test_findings_publication_reconciles_before_moved_authority_after_two_lost_terminals`, `test_rerun_reconciles_before_claim_and_runs_reads_after_two_lost_terminals`, `test_reminder_reconciles_before_claim_and_recipient_reads_after_two_lost_terminals` | provider effect landed but repeated Activity terminals were lost | repeated crash after `activity_effect_observed`; each recovery uses the same operation and eventually returns `activity_terminal_recorded` |
| `test_mutation_replays_one_agent_result_then_reconciles_one_ref_advance` | coding result survives by agent identity; process can die before Git effect and after ref acceptance | coding `activity_effect_observed` → crash/replay; Git `activity_effect_observed` → crash/reconcile → `activity_terminal_recorded` |
| `TestReviewRequestRecovery.test_restart_reuses_the_exact_frozen_request_before_any_provider_read` | exact request custody survives a lost review terminal | `activity_effect_observed` interrupted after request claim; restart reconstruction/lookup precedes fresh evidence |
| held/lookup-first publication tests in `test_v5_gates.py`: held reply, nudge, announcement, findings, and compatible-body lookup | accepted comment effect is reconciled before mutable context/authority reads | `activity_effect_observed` → crash → next `activity_effect_observed` reports lookup recovery, then `activity_terminal_recorded` |
| `test_an_already_held_rerun_reconciles_landed_before_any_read`, `test_a_race_found_existing_request_reconciles_landed`, `test_an_issuance_boundary_failure_fails_closed` | rerun lookup wins after definite or ambiguous issuance | `activity_effect_observed` (landed or interrupted) → replay with same operation → `activity_terminal_recorded` |
| `test_existing_commit_reconciles_before_claim_or_agent`, `test_ambiguous_ref_cas_reconciles_before_failing_closed`, `test_raw_publication_boundary_failure_remains_recoverable` | Git lookup proves a prior commit or retains an ambiguous exact operation | `activity_effect_observed` → crash/replay → lookup-first `activity_effect_observed` → `activity_terminal_recorded` |
| `test_delivery_remains_pending_when_post_activation_settlement_fails`, `test_delivery_factory_failure_is_recorded_for_durable_retry` | readiness settlement or construction fails before host can release custody | `readiness_step_returned(Unavailable)` or failed `instance_opened`; delivery remains pending, then `subject_requeued` with retry eligibility |
| `test_delivery_is_acknowledged_only_after_runnable_posture_succeeds`, `test_delivery_remains_pending_when_runnable_posture_fails` | readiness acceptance precedes host posture, which precedes inbox acknowledgement | `ingress_entry_folded(admission=accepted)` → `posture_recorded`; only then `delivery_acknowledged`. A posture failure retains custody |
| `test_retry_does_not_block_later_delivery_and_new_process_resumes_same_custody` | failed subject custody survives process replacement while another PR progresses | failed `readiness_step_returned` → tail `subject_requeued`; another `subject_selected`; restart later selects the retained delivery |
| `test_same_subject_delivery_waits_behind_an_earlier_deferred_failure`, `test_sweep_does_not_reconcile_while_addressed_comment_retry_is_deferred` | later same-subject delivery and reconciliation cannot pass the earlier custody fence | `Waiting(host_custody)` until the earlier delivery's retry deadline and admission cuts complete |
| `test_startup_sweep_applies_pending_comment_without_duplicate_provider_reconciliation` | retained host custody is admitted before optional provider reconciliation | `catalog_page_inspected` → `subject_selected` → admission cuts → `delivery_acknowledged`; no reconciliation admission is eligible first |
| `test_selected_v5_restart_replays_settled_webhook_after_death_before_acknowledgement` | readiness and posture durable while host inbox row remains pending | final `ingress_entry_folded(admission=accepted)` and `posture_recorded` → crash → `delivery_acknowledged` |
| `test_selected_v5_restart_rebuilds_timer_after_crash_before_runnable_hint` | maturity and next timer accepted before host records replacement hint | readiness timer/workflow cut → crash → `posture_recorded`; catalog reconstruction must not duplicate reminder |
| `test_startup_sweep_settles_frozen_terminal_before_provider_reconciliation` | Dispatch terminal exists at startup before provider reconciliation | `activity_terminal_recorded` → crash → `runtime_reconstructed`/`workflow_advanced(activity_terminal_projected)` before any reconciliation admission |
| `test_run_due_contains_instance_failure_rewakes_and_recovers_scheduler_health` | one subject failure requeues without blocking another | `readiness_step_returned(Unavailable)` → `subject_requeued` at tail; next `subject_selected` is the other due subject |
| `test_periodic_sweep_reopens_active_and_inactive_bound_instances`, due-wake reconstruction tests, and `test_startup_sweep_repairs_inactive_bound_instance_without_runnable_hint` | retained cataloged instance reconstructs without an in-memory object or hint | `catalog_page_inspected` → `subject_selected` → `instance_opened` → one `readiness_step_returned` |
| `test_real_host_recovers_one_ambiguous_readiness_effect_after_crash_and_exact_replay` | publication terminal durable before workflow projection | `activity_effect_observed`/`activity_terminal_recorded` → crash → `workflow_advanced(activity_terminal_projected)` |
| `test_real_host_recovers_one_ambiguous_reminder_after_timer_maturity_and_crash` | due timer leads to accepted reminder with lost response before projection | `timer_maturity_claimed` → accepted/marked/folded cuts → `activity_effect_observed`/`activity_terminal_recorded` → crash → projection |
| `test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash` | exact ref CAS accepted, response lost, later explicit recovery proves it | Git `activity_effect_observed` → crash; later admitted recovery uses `ingress_staged` and lookup-first Activity cuts |
| `test_generated_delivery_recovery_schedules_replay_exactly`, `test_generated_authority_lifecycle_schedules_replay_exactly` | crash may occur between any disclosed coarse host actions | target generator selects any returned `CutRef`; authority admission uses stage/entry/fold/host-ack cuts rather than a coarse host callback |
| `test_generated_reminder_timer_recovery_schedules_replay_exactly` (`before_due`, `after_due`, `after_acceptance`) | timer wait, due handling, and accepted reminder ambiguity | respectively `Waiting(timer_deadline)`, one selected timer maturity cut, and `activity_effect_observed` or `activity_terminal_recorded` |
| `test_generated_v5_git_publication_recovery_schedules_replay_exactly` (`before_delivery`, `after_acceptance`, `after_head`) | pre-admission, accepted ref, and later authority-head admission cuts | host custody posture, Git `activity_effect_observed`, and final `ingress_entry_folded` respectively |

Tests whose names contain “recovery” but only validate bounded user syntax or
artifact retention remain valuable without defining a runtime crash cut. Tests
for inline identity rejection map to admission/Activity input bounds, not to a
crash boundary. Legacy migration and corrupt-store quarantine tests inform
fail-closed construction and resource limits; they do not add semantic steps.

## Production drains over the same steps

No production-only settle path exists. A convenience drain is a budgeted loop
over the same public method used by deterministic simulation:

```text
drain_readiness(lifecycle, reason, evidence, step_budget):
  require 0 < step_budget <= configured_max
  for count in 1..step_budget:
    result = lifecycle.progress(reason, evidence)
    emit result.cut when Progressed
    if result is Waiting | Quiescent | Terminal | Unavailable:
      return DrainResult(result, steps=count)
  return BudgetExhausted(last_posture, steps=step_budget)
```

Admission uses the same shape with repeated `admit(delivery, evidence)` and
stops only on accepted/already-accepted posture, wait, unavailable, or budget
exhaustion. It does not call `progress()` to settle unrelated work before host
acknowledgement.

```text
run_host_turn(host, subject_budget):
  selected = host.select_distinct_due(subject_budget)
  for subject in selected:              # finite, unique subjects
    host.invoke_one_readiness_step(subject)
    host.record_at_most_one_pending_host_cut(subject)
    host.release_or_requeue(subject)
  return TurnResult(selected, per_subject_results)
```

The pseudocode abbreviates raw host cuts; implementations and simulations can
stop after any returned `subject_selected`, `readiness_step_returned`,
`posture_recorded`, `delivery_acknowledged`, or `subject_requeued` cut. A
production helper may run those cuts back-to-back only under an explicit host
cut budget.

The proof is structural:

- every loop counter is a validated finite input;
- the loop body invokes one contract step, which has its own row/byte/call/time
  bounds and no inner drain;
- a non-progress disposition terminates the loop;
- reaching the budget returns `BudgetExhausted`, never a false `Quiescent`;
- reconstruction, startup, sweep, inspection, and shutdown use the same page
  and subject budgets; and
- therefore one production call consumes at most the sum of its finite step
  budgets and cannot secretly converge another subject.

An operator command may request repeated bounded turns, and the long-lived
worker may poll forever. Neither changes the contract of one occurrence.

## Fairness and liveness bounds

### One readiness instance

Let `L` be the finite set of readiness lanes eligible after correctness
dependencies: ingress, workflow, Activity, timer, wake, and route settlement.
The lane cursor is weakly fair:

- one step serves one lane once;
- a served lane rejoins behind lanes already eligible at that instant;
- a retry is eligible only at its recorded retry time and rejoins at the tail;
- newly eligible work cannot reset the cursor ahead of continuously eligible
  older work; and
- Petrus candidate selection must be weakly fair among continuously enabled
  workflow candidates or expose enough cursor state for readiness to provide
  that property.

If dependency work is finite and `k <= |L|` lanes remain continuously eligible,
each receives a step within at most `k` successful lane selections. This is not
a convergence claim: an external Activity, human observation, timer, revoked
route, unavailable store, or infinite stream of new authority can keep the
instance open. Liveness is claimed only under finite step execution, readable
stores, bounded retries, available workers, advancing logical time, stable
authority, and eventually stopped generated faults.

### Multiple instances

Host runnable custody uses a durable monotonic enqueue sequence or equivalent
round-robin cursor. Ordering by `(due_at, instance)` alone is insufficient
because an immediately failed/re-woken lexically early subject can repeatedly
win a small selection limit.

For each service turn:

1. select at most `H = subjects_per_turn` distinct due subjects;
2. invoke at most one readiness step for each selected subject;
3. put a progressed, failed, or immediately re-woken subject behind all
   already-due unselected subjects; and
4. preserve retry eligibility/backoff without blocking unrelated subjects.

For a finite continuously eligible set of `N` subjects, each subject receives
one readiness call within at most `N` subject selections, or
`ceil(N / H)` complete host turns. A subject whose step returns `Waiting`,
`Quiescent`, or `Terminal` leaves the due set until an exact wake creates new
eligibility. A selected-subject process crash cannot consume its chance
forever: selection leases expire and reconstruct at the tail.

No global fairness claim is made for an infinite arrival stream, a subject with
an unbounded step, permanently unreadable custody, or a retry policy with no
eligibility delay. Those are resource/availability violations, not scheduler
success.

## Resource bounds

The contract fixes named measures; delivery work chooses concrete values from
executed workloads and rejects or pages inputs that exceed them. Every value is
a positive integer except an explicit zero work budget.

| Measure | Applies to | Enforcement |
|---|---|---|
| `history_records_per_page`, `history_bytes_per_page`, `history_record_bytes` | runtime load, wake/timer/route projection, inspection | page reads; reject an oversized record before decode |
| `in_flight_occurrences_per_instance` | reconstruction and Dispatch repair | workflow/runtime admission invariant; excess is unavailable/fail-closed, never scanned in one step |
| `manifest_entries`, `manifest_bytes`, `ingress_entry_bytes` | one staged provider or reconciliation manifest | validate before atomic stage; entries progress individually |
| `conversation_input_bytes`, `conversation_output_bytes`, `conversation_deadline_us` | optional ingress classification | validate before call; one attempt per stage step |
| `activity_input_bytes`, `activity_result_bytes`, `adapter_reads_per_step`, `effect_calls_per_step=1`, `effect_deadline_us` | Motus execution and S4 adapters | validate at request/return; each operation declares its finite lookup/fence read budget; no Worker drain or internal attempt loop |
| `timer_rows_per_page`, `timer_fact_bytes`, `timers_per_instance` | timer open/rebuild/live custody | page reconstruction; one live command/ack/maturity cut |
| `agent_route_operations_per_page`, `operation_identity_bytes` | readiness posture and host route repair | one settlement per progress cut; paged detached inspection |
| `custody_rows_per_page`, `custody_payload_bytes` | host webhook inbox | bounded receipt and page; one due row or one read-only page step |
| `catalog_rows_per_page`, `inspection_bytes`, `loaded_instances` | startup, sweep, inspection, memory | catalog paging and bounded detached readiness inspection |
| `subjects_per_turn`, `host_cuts_per_turn`, `readiness_steps_per_drain` | scheduling and convenience drivers | validated caller/config budgets; budget exhaustion is explicit |
| `retry_attempts`, `retry_delay_us`, `selection_lease_us` | Activity and scheduler recovery | durable policy; no immediate head-of-line retry |
| `shutdown_subjects_per_page`, `shutdown_cuts` | graceful closure | bounded terminal settlement; abort preserves semantic state after budget |
| `directory_entries_per_scan` | corrupt-store quarantine and retained-root hygiene | bounded directory page; no unbounded suffix search |

Collections embedded in workflow values—findings, checks, dashboard entries,
changed files, and agent context—must already satisfy their owning value's item
and byte admission limits before they can enter a step. “One token” is not a
resource bound when the token contains an unbounded list.

For one readiness step, resource use is bounded by one row/page budget, one
value byte budget, one fixed S4 lookup/fence sequence, and at most one external
effect call. For one host turn, the bound is `H` times one readiness step plus
the declared host cuts/pages. Loaded-instance count affects memory but does not
increase one subject's service allocation.

## Simulation cut proof

The target simulation needs only public construction, command, step, crash, and
detached observation seams:

```text
configure deterministic ports through typed public commands
construct workflow runtime, readiness lifecycle, or host
call one public step
read StepResult.cut
optionally crash after that returned cut
drop the generation
reconstruct from retained public stores and modeled provider/agent ledgers
continue with the same public step
check detached projections
```

Every cut in the matrix is reachable this way:

- manifest, History, fold, timer, route, posture, inbox, and scheduler cuts are
  separate returned steps;
- effect acceptance/loss is returned as `activity_effect_observed` before
  `activity_terminal_recorded`;
- Dispatch terminal persistence is returned before workflow projection;
- reconstruction returns one page or occurrence repair before fresh work; and
- host acknowledgement and runnable posture are returned after, not inside,
  the readiness step they reflect.

Fault schedules name `CutRef` plus occurrence, for example “crash after the
first `timer_maturity_accepted` for timer T.” Deterministic adapters model
response loss through typed public fault commands and stable operation ledgers;
they are not installed callbacks into readiness. Tests do not replace methods,
provide a custom Dispatch to discard terminals, query a private Engine marking,
mutate SQLite behind an owner, or retain a mutable runtime handle across crash.

The current World does not yet satisfy this interface: its disclosed host step
can call the nested drains inventoried above, and several unit tests use custom
Dispatch or method replacement to cut inside them. This record supplies the
contract that removes those techniques. S8 owns the executable driver-mechanism
proof; Exp 9 and Exp 10 own the deterministic runtime and module simulations.

## S8 handoff and unresolved mechanism questions

S8 must implement a non-production spike against this contract and answer only
mechanism questions:

1. Can current Petrus expose bounded first-load History replay and one retained
   occurrence repair, or is a small upstream/public provider seam required?
2. How does Activity execution pause after `activity_effect_observed` and before
   `activity_terminal_recorded` without making a generator frame or private
   continuation authoritative? The proof must kill the process at that cut and
   recover lookup-first.
3. Which explicit-loop, trampoline, or generator spelling makes the one-cut
   result and cancellation route clearest while preserving the same durable
   state owners?
4. Can host fair selection, one readiness call, posture recording, inbox ack,
   and requeue be inspected at every cut without adding a second scheduler?
5. Do the named resource pages compose without an all-History validation scan
   before the first result?

The spike may reject all alternatives and keep an explicit step baseline. It
must not change the R2 trees, move effect semantics, create a second workflow
scheduler, or promote a mechanism to architecture without the R3 ruling.

## Exit assessment

Workflow, readiness, and host each have an exact one-cut result contract.
Waiting, quiescent, terminal, and unavailable states are distinct. Every
maintained crash/recovery boundary in the target route maps to a returned cut;
production drains are finite loops over those same calls; single- and
multi-instance fairness have stated assumptions and service bounds; and every
step has named count, byte, call, time, and retry measures.

The simulation route reaches all required crash cuts through public result
values and reconstruction, without callbacks, monkeypatches, or private mutable
runtime access. Experiment 7 therefore meets its design exit criterion. S8 may
spike the driver mechanism after Navigator acceptance of this record. R3
remains unruled.
