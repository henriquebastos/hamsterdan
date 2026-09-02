# Gate B, two releases, and the first full hero journey in production

The Navigator approved Gate B, the new-code release, closing all stale
demo PRs, and a fully exercised hero journey with browser-video
evidence, in one directive on 2026-09-01.

## Gate B and cleanup

`v0.1.0` was tagged at the accepted revision `7df44260…` and pushed;
the deployment recovery and rollback facts are recorded in the CV19
launch runbook. Demo PRs #52–61 were closed unmerged by the operator.

## Release sha-f4e443b0… — the schema boundary

The candidate carrying the board renderer and watched-authors narrowing
built and verified locally, deployed (ok=17 changed=3), but the service
crash-looped: the petrus pin moved History schema 4→5 with deliberately
no migration, so startup failed closed against the accepted-era durable
state — exactly the recorded fail-closed doctrine. All eleven persisted
instances were closed PRs, so the state was backed up on the VM
(`/var/lib/hamsterdan-state-schema4-backup-20260902.tgz`) and replaced
deliberately. Provisioning also requires an inactive service, fixing
the sequence as stop → provision (ok=40) → start. Startup
reconciliation rebuilt routes; `/healthz` returned 200 with a clean
scheduler, and the hero PR's `pull_request opened` delivery through the
exe.dev share (OK 202) was the live ingress proof.

## Hero journey — PR #63

[PR #63](https://github.com/HBNetwork/demo-pr-readiness/pull/63),
branch `hamsterdan/hero-review-20260902-012749`.

- Opened at head `5d71a9de…`; the board's first production render was
  "⏳ waiting on CI — nothing for you to do."
- Review round 1 returned `RoundUnable`: the Pi session shows every
  `workspace_read`/`workspace_search` failing (`provider operation
  failed`) after two rounds were correctly deferred/cancelled by
  arriving deliveries — a cold-start race, not a code change (neither
  petrus agenticus nor the Pi glue differ between images). The board
  surfaced it honestly and offered the retry ask.
- The retry mention exposed the reply-token defect: Dan's agent
  composed "The review of the current head is already running." but the
  host published the internal token `answer:reply`.
- Author pushed empty-commit head `1fab2e60…`; CI run 33580107163 green
  6/6; review round 2 produced the complete findings batch (comment
  5503038348): lease-TTL suggestion, conceptual approval-policy defect,
  cache-key defect with related location. Cris submitted
  `REQUEST_CHANGES`. Blocked-checkpoint inspection: ok, all checks,
  readiness correctly absent.
- Patch release `sha-8ecc2a81…` (reply-voice fix, commit 8ecc2a8)
  deployed mid-journey as the supervised restart: stop → provision
  (ok=40) → start; the PR instance and inbox custody survived intact.
- The repair ask "apply your suggested fixes" was declined with a real
  question — the conversation agent receives `gates=[]`/`findings=[]`,
  so it cannot see its own findings (defect, open). An explicit change
  instruction then drove the fenced repair: commit `ae84a2ae…`
  authored Hamsterdan, pushed by `hamster-dan[bot]`, touching only the
  two fixture files.
- The push settle raced its own webhook and faulted
  (`Git remote ref differs from the current PR projection`) though the
  push had landed; the board's recovery ask + a human
  `recover the publication push:comment:…` mention reconciled it
  lookup-first ("On it — I'm retrying that publication now.").
- Re-review on the repaired head: clear, 0 findings. `@hamster-dan
  status` answered in prose (content thin — same empty-context defect).
  Cris approved; the board went all-clear pointing at the readiness
  advisory (comment 5503360116), which announced exactly once. Full
  inspection: ok, 10/10 including readiness present. Closed unmerged;
  the dashboard close-froze at the all-clear board by design.

## Defect ledger from the journey

1. Cold-start review round returns unable (workspace reads fail) —
   transient, recovered by a new head; watch for recurrence.
2. Conversation replies published internal tokens — **fixed** in
   8ecc2a8, verified live in production.
3. The conversation agent receives empty `gates`/`findings` context —
   open; blocks "apply your fixes" phrasing and thins status replies.
4. A successful push can still fault its own settle when the webhook
   loses the race — recovery works as designed but is human-visible
   noise; candidate improvement.

## Evidence

`~/Desktop/hamsterdan-hero-20260901/`: four WebM clips (opened/first
board, retry + findings, repair, approval + advisory) and eight
full-client-area screenshots, one per checkpoint. Inspection JSON for
the blocked and final checkpoints ran clean via
`scripts/hamsterdan-demo inspect --pr 63`.
