---
status: Candidate
captured: 2026-09-04
navigator: Henrique
source: ../roadmap/cv19-private-v0-1-production/proof/pr80.md
---

# 1. RS-036 — Publish the initial summary before review

## 1a. Investigation result

Henrique asked why the summary is not the first visible action when Hamsterdan
starts observing a PR. Investigation is complete; implementation has not been
pulled. Current V5 queues the summary early but services that queue after
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

## 1b. Mechanism

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

The dashboard is currently a single-flight sink. Its memory is held while an
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
