---
status: Active
captured: 2026-09-04
navigator: Henrique
source: ../roadmap/cv19-private-v0-1-production/proof/pr80.md
---

# 1. RS-036 — Publish the initial summary before review

## 1a. Investigation result

Henrique asked why the summary is not the first visible action when Hamsterdan
starts observing a PR. On 2026-09-04 he approved implementation, then clarified
that initial summary creation should precede all normal Activities. The
pre-change V5 runtime queues the summary early but services that queue after
synchronous review work. It has no workflow dependency requiring the first
summary to land before a review starts.

The PR80 export establishes this ordering on deployed revision `14f41d8`:

| Event | UTC on 2026-09-04 |
| --- | --- |
| PR opened | 21:48:44 |
| Summary occurrence 48 queued | 21:49:06.225 |
| Review submitted to GitHub | 21:50:17 |
| Worker claimed summary occurrence 48 | 21:50:19.176 |
| Summary comment created | 21:50:19 |

The summary spent 72.951 seconds queued before its first claim. A snapshot at
21:49:52 still shows `queued` and no attempt start. This delay therefore precedes
the summary's provider call. History requests `dash.publish` before
`review.agent`, but completes review occurrence 88 and publication occurrence
90 before the first `DashLanded`. GitHub independently records that visible
order. The earlier 22 seconds between PR creation and summary scheduling are
not broken down by this evidence.

Evidence remains under `tools/demo-video/output/proof/cv19-pr80/`:
`03-runtime.jsonl`, `04-runtime.jsonl`, `14-ready-github.json`, and
`pr80-durable-evidence/history/history.jsonl`. Their hashes are in the
[committed manifest](../roadmap/cv19-private-v0-1-production/proof/pr80-manifest.json).
History's `instant` is logical time, so the wall-clock calculation uses the
Dispatch timestamps rather than interpreting History's zero instants as UTC.

## 1b. Pre-change mechanism

1. `DURABLE_PUBLICATION_GATES` in `readiness/net_v5/gating.py` contains
   `reply_gate`, `dash_gate`, and `announce_gate`. Review generation and review
   publication belong to the inline group.
2. `_CompositeDispatch.dispatch` in `host/v5/runtime.py` queues those durable
   publications in SQLite, while `InlineDispatch` executes review work during
   Engine advancement. `V5Runtime.drain` continues advancing until the Engine
   reaches an external wait.
3. `HostService.pump` in `host/service.py` calls `project_pending()` and
   `run_due()` before `run_durable_activities()`. Activation calls
   `application.settle()` while holding the PR lock. Review generation and
   inline publication can finish before control reaches the queued summary.
4. Pending same-PR webhook custody also suppresses worker claims. That is an
   existing authority-safety condition, not a reason to bypass custody for a
   faster initial comment.

At diagnosis, the dashboard was a single-flight sink. Its memory is held while an
immutable publication is outstanding; subsequent facts wait in its mailbox.
Consequently, the delayed first summary can also display an older state until
follow-up upserts catch up. Dashboard rendering itself does not call an LLM.

## 1c. Local reproduction and test gap

The bounded probe used the real `PrReadinessV5Application`, Engine, History,
LocalDispatch, and Worker with the existing `Authority`, `Transport`, and
`Runner` fixtures from `tests/unit/host/test_v5_ingress.py`. It processed one
`pull_request/opened` observation and recorded review entry/exit and comment
creation. The only changed configuration between runs was `dispatch_path`.

| Configuration | Observed order |
| --- | --- |
| Production-style durable publications | review starts; review finishes; worker creates summary |
| Inline-only test configuration | summary created; review starts; review finishes |

The probe reproduced twice without network calls or sleeps. At review entry,
it asserted that no summary existed in durable mode and that one already
existed in inline mode. It also confirmed that the summary was requested first
in both cases. The local probe and output are retained at
`.amp/runtime/probe_summary_order.py` and
`.amp/runtime/summary-order-reproduction.txt` as disposable diagnostics.

Three existing focused tests pass: per-instance durable queue ownership,
authority projection before durable execution, and withholding claims while
same-PR custody remains pending. None asserts first-summary ordering. A future
regression must exercise the production dispatch configuration and a controlled
review that stays in progress; an inline-only test can conceal this problem.

## 1d. Recommended refinement

Make successful initial summary publication a prerequisite for starting review
work, with the Net owning that ordering. The visible sequence should be an
initial "reviewing" summary, then inline findings, then updates to the same
summary. Preserve durable publication, lookup-first recovery, pending-custody
fencing, and one-owner Engine advancement.

The current dashboard sink has no completion signal to the review loop. The
implementation must explicitly decide how initial publication failure affects
review admission and preserve that decision through restart. Moving the summary
back to inline execution is only the diagnostic comparison above, not the
recommended durability change. Merely running the worker concurrently would
also leave visible ordering as a race unless workflow encodes the dependency.

No runtime code, provider state, or deployment changed during this investigation.

## 1e. Accepted startup sequence and correctness plan

The first successful dashboard Activity completes startup and releases all
other workflow Activities. Intake and pure folds remain available while startup
waits, including routing an explicit recovery request. Later dashboard updates
never suspend the workflow. This supersedes the narrower review-only proposal.

The composer owns one `startup.pending` token in each fresh History. Its
presence inhibits every non-dashboard Activity gate. `DashLanded` mails a
publication fact; startup consumes that fact and its pending token once.
Subsequent publication facts drain without changing startup. This deliberately
adds a composer-owned startup precondition to V5's otherwise loop-local
inhibitors. It does not change Worker concurrency or the dashboard's single
publication custody, digest, or lookup-first rules.

History is authoritative across restart, including a queued first publication
and the consumed startup token. Existing Histories have no startup token and
continue their already-started work. No retroactive summary-first claim is made
for those instances. Startup does not complete after a blocked, deferred, or
unknown publication terminal. Recovery uses the retained exact operation;
success releases work. A closed or draft PR retains the existing lifecycle
fences. Pure intake may continue to queue facts while GitHub is unavailable;
existing inbox and Activity limits remain in force.

Validation must observe actual effect ordering with production-style durable
Dispatch, resume before and after the first publication, hold unrelated work
behind failed startup, recover without duplicate comments, and demonstrate that
later dashboard failures do not pause work. The normal release gate must also
cover existing authority, custody, lifecycle, and replay contracts. Provider
behavior must be manually proven before any deployment; deployment is never a
behavioral experiment.

## 1f. Manual provider evidence

Before release qualification, the existing production `CommentPublisher`
created the App summary on disposable issue
[HBNetwork/demo-pr-readiness#81](https://github.com/HBNetwork/demo-pr-readiness/issues/81).
It returned `created`, `existing`, `updated`, `existing` for initial creation,
exact repeat, changed body, and final repeat. Independent GitHub inspection
found exactly one App-owned comment, ID `5547518436`, created at
2026-09-04T23:13:50Z and updated at 23:13:51Z.

The first probe's final request-count assertion also counted installation-token
authentication. Its four publication-result assertions had passed; this was a
probe audit error. The corrected repository-path filter then verified two
updates returning HTTP 200 and exact repeats returning `existing`, all on that
same comment. Request IDs were `966C:366D49:7E7F82:1973A59:6A9B50D7` and
`CF4C:3313BC:7E106A:1997530:6A9B50D8`. The independent read again found one
comment, and the issue was closed after verification.

Commands ran through `scripts/ops` using the existing service account and
pinned SSH access. No fingerprint prompt, secret output, raw webhook export,
or deployment was needed. Local sanitized evidence is in
`.amp/runtime/rs036-provider-proof.json` and
`.amp/runtime/rs036-provider-independent.json`. This proves the provider
create/update/recovery boundary; the new workflow ordering is proven separately
with the production Dispatch configuration in the application tests.

## 1g. Review and qualification

The final runtime change adds one pending token per new PR and two pure startup
transitions. Every normal Activity gate is inhibited until a successful summary
publication consumes the token. Existing dashboard request/result schemas,
provider operations, Activity retry policies, and Worker composition remain
unchanged. No new concurrency mechanism or dependency was added.

The regression initially failed at agent entry because no summary existed. It
now verifies one real application summary before review with durable Dispatch,
including restart while queued, after provider completion but before folding,
and after startup completion. Additional tests hold the first summary while
review, reply, repair, and CI work are queued; test blocked and unknown first
publication recovery; preserve independent later reviews/replies through update
failures; and exercise initial draft and close during publication.

Existing publication-recovery tests now account for the review facts that arrive
after startup recovery. Custody-race fixtures establish the summary and clear
review before approval. Timer tests count reminder comments independently from
the new initial summary. The retained-Net bridge's exact History counts and
corruption positions advance by one for the startup token. Those are fixture
updates to preserve the original assertions, not new replacement-runtime work.

No unrelated refactoring or new durable debt was introduced. The deliberate
composer-owned startup precondition is recorded above. Broader Activity
concurrency remains a separate, unpulled improvement.

`scripts/check release` passed 1,267 tests in parallel and 1,267 serially, with
18 declared platform deselections. Static, architecture, replacement-bridge,
Bun, TypeScript, and distribution checks passed. A final focused startup run
passed seven tests after strengthening the queued code-change case; no runtime
code changed after the release gate began.

Production promotion is next under the Navigator's standing deployment
authorization. Capacity was checked first: 2.5 GB free on the 20 GB VM, with
the current `14f41d8` and prior `e3a79bb` image candidates retained. This is a
verified release promotion, not a deployment to discover behavior.
