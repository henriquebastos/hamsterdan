# 1. Initial summary startup proven in production

The Navigator approved publishing the initial summary before all normal
Activities, while retaining independent ongoing summary updates.
[RS-036](../../../project/workbench/rs-036-publish-initial-summary-before-review.md)
records the diagnosis, accepted ordering, implementation, and proof.

Revision `2f1b646906bcd8e3b13f6b969eed808f6d70e905` adds one durable startup
precondition owned by the Net. A successful first summary releases normal
Activities once. Initial publication failures preserve that precondition;
later summary failures do not pause work. Restart and legacy-History behavior
are covered without changing provider boundaries or Worker concurrency.

Manual App comment creation, repeat, and update behavior was proven on issue
#81 before qualification or deployment. The release gate passed 1,267 parallel
and 1,267 serial tests, with 18 declared platform deselections. Static,
architecture, replacement-bridge, Bun, TypeScript, and distribution checks
passed. The exact verified image was qualified and provisioned; both repeated
with `changed=0, failed=0`. It started at 23:35:38Z, healthy with zero restarts.

[PR82](https://github.com/HBNetwork/demo-pr-readiness/pull/82) proved the first
summary nine seconds after opening, before any normal Activity request.
History places `DashLanded` at sequence 208, startup completion at 231, and the
first review request at 235. The clear review returned `AgentReview` and
`ReviewLanded`; all six CI jobs passed. Eleven dashboard publications retained
one comment, and exactly one advisory accompanied the final all-clear state.
Both inspectors passed six checks. The 792-record preclosure History contained
no error terminals or pending Activities. Two `RoundDeferred` results were
webhook-custody synchronization states. The clean-green policy required no
human review; PR80 remains the full three-actor repair and approval proof.

PR82 was closed unmerged after capture. The
[manifest](../../../project/workbench/proof/rs036-pr82-manifest.json) identifies
the release, ordering evidence, local capture files, and archive. This bounded
proof adds no media or transcript capture. Secrets and raw webhook payloads
remain excluded. Every production operation ran through `scripts/ops` with
service-account authentication and pinned SSH, without interactive prompts.

Review found no unrelated refactoring or new durable debt. The existing
candidate-retention obligation was checked before deployment and remains open.
CV19 still awaits capture-package acceptance and the broader repository
monitoring portfolio; this refinement is complete.
