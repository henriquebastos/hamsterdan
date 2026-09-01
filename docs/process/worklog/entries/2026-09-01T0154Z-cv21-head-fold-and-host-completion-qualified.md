# CV21 Head fold and host completion qualified locally

CV21.DS2 task 5 completes the cumulative source-neutral tracer without entering
DS3. `ObservationAcceptanceAuthority.fold_accepted_observation(...)` selects the
original task-2 route/delivery under the host catalog writer fence, reconstructs
task-3 staging and task-1 registration/root authority, exact-reoffers the
bridge-private source/token/identity through public `Engine.accept_delivery`,
and calls public `Engine.complete_delivery` only for the returned unfinished
carrier. It validates exact instance/source/identity/occurrence correlation and
the `FiringOutcome` before returning a detached fold posture.

The fold commits only `TokensProduced` and `FiringCompleted` after task 4's
`ExternalEventDelivered` and `FiringBegun`. The exact `HeadSeen` is deposited at
`life.heads`, occurrence 1 disappears from the unfinished set, no
`FiringFailed` exists, and no newly enabled transition advances. Dispatch stays
empty; no Worker, Activity, provider call, discovery, currentness, ancestry,
agent, effect, or lifecycle increment occurs.

Response-loss recovery exact-reoffers immutable staging and receives
`PriorAcknowledgement`. It does not call completion again. One finite complete
History page and bounded public runtime inspection must prove the unique exact
delivery/terminal suffix, running state, no in-flight occurrence, exact
`life.heads` token, and retained running incarnation 0. Failed, partial,
malformed, unrelated, scoped, or mismatched evidence fails closed. Only
occurrence 1 is eligible, and any `FiringFailed` in the bounded History page
invalidates the fold proof. Backend
refusal or an ambiguous completion acknowledgement returns one fixed
cause-free error; fresh load decides whether History is unfinished or contains
the exact successful terminal.

The complete mapping identity is deliberately
`workflow-bridge/head-seen-history-fold@3`, replacing task 4's acceptance-only
`@2` identity and changing the fresh-state History delivery identity. No old
roots are migrated. The bridge alone projects actual retained state into strict
`ObservationFoldPosture`: exact subject/instance and delivery/occurrence,
running phase, local incarnation 1, source-neutral repository/ref/SHA branch
tips correlated to retained SHAs, explicit-true mergeability, manifest policy,
`strict_base=True`, `base_current=False`, finished/folded status, and
`observation_folded`. No current/Petrus/provider type or generic marking/token
payload crosses the new-facing boundary.

`ObservationAcceptanceAuthority.complete_observation_delivery(...)` is the
separate host cut. It reconstructs and verifies the same fold itself, then
records one `HostDeliveryCompletionReceipt` in the existing delivery custody
database. The receipt binds original route/delivery/custody generation,
subject/instance, bridge, manifest/grant/digest/entry/key, History delivery/
occurrence, `observation_folded`, and `host_delivery_completed`. History remains
the sole fold ledger. First exact completion inserts once; exact replay reads
without write; changed correlation never overwrites. Every insert and receipt
reconstruction also authenticates route/delivery/generation/subject and exact
canonical content/digest against the immutable staged acquisition, plus a
strict retained-or-valid-quarantine custody disposition. An orphan receipt or
malformed collision fails closed. Original normalized custody and late
quarantine remain visible and unchanged. Singleton receipt reads use `LIMIT 2`
and strict SQL type/byte projection before model construction.

The existing History file/WAL/shared-memory ceiling remains 2 MiB. Inspection
uses at most one 4,096-record History page. Unfinished completion remeasures and
reserves 1 MiB for its two-record transaction; ended reoffer reserves no append
headroom. Retained projection is capped at 64 places and 128 tokens. Completion
rows, SQLite pages, state files/bytes, diagnostics, process artifacts, and
checker materialization remain finite.

Owner-local and cumulative root Worlds add separate fold and host-completion
commands. Their deterministic sequence exposes open, custody, staging,
unfinished acceptance, fold, and completion cuts; fresh-root exact replay,
out-of-order refusal/idempotence, late quarantine, and finite resources are
checked independently. Mutation sensitivity covers terminal order/content,
produced token and entries, every fold-posture field, unfinished-occurrence
disappearance, every receipt correlation and cut, and cross-owner custody→
staging→History→fold→completion identity and occurrence equality. Real SQLite
concurrency converges on one folded occurrence and one receipt under the host
fence.

Actual `SIGKILL` after `Engine.complete_delivery` commits but before caller
acknowledgement reconstructs the same fold through prior acknowledgement with
no History append and no host completion. Actual `SIGKILL` after host completion
commits reconstructs the same receipt with no History or completion append. The
earlier custody, staging, and unfinished-acceptance interruption scenarios still
pass.

Focused evidence passed 59 exact fold/completion tests, 142 cumulative DS2
simulation tests, five process-recovery tests, and 24 architecture tests.
`scripts/check hamsterdan2` passed strict Ruff, formatting, `ty`, seven
ast-grep rule fixtures/scans, architecture/feedback checks, and all 448
replacement tests. `uv lock --check`, the exact installed Petrus commit
`4e5c2500af4eb439e8e8f5ec108982c81bfc7427`, forbidden API/import scans, and
`git diff --check` passed. The complete `scripts/check full` profile passed
quick/replacement, Bun/TypeScript/live-capture, and distribution-build checks;
its cumulative Python run reproduced exactly the inherited 14
`tests/unit/test_orb_setup.py` failures from unset `$USER` at
`.agents/setup:229`, alongside 1,151 passes and no new failure.

Coherence review found that the glossary added to `origin/main` while this task
was in progress discourages `custody`, `cut`, `incarnation`, and `subject` in
favor of current-product terms. The confirmed CV21 Plan Checkpoint and existing
outer-system contracts require those technical terms for this tracer. Its
`Webhook Inbox` entry also describes raw-delivery retention, HTTP 200, and later
Worker processing, while the delivered CV21 contract stores only normalized
canonical content, returns HTTP 202, and keeps readiness authority separate from
HTTP without running a Worker. This task therefore changes no accepted glossary
entry; Navigator Experience Report acceptance must rule whether and how that
product glossary applies to CV21-internal architecture before DS2 closure.

CV21.DS2 remains `Active`. Tasks 1–5 are delivered, but Navigator Experience
Report acceptance and closure remain before `Completed` status or the final DS2
completion worklog. DS3 is not pulled and no cutover is claimed.
