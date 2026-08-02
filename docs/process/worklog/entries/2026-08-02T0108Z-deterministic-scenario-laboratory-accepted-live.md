# Deterministic scenario laboratory accepted live

CV3.DS1 completed on six fresh isolated pull requests in
[`HBNetwork/demo-pr-readiness`](https://github.com/HBNetwork/demo-pr-readiness),
all based on corrected scenario-laboratory main
`661002b8bdcb57d0ea7c2d7fb4fbfa58af3aae60`. Preparation was idempotent and
machine-readable evidence matched each manifest's admitted paths. The earlier
PR17-21 generation was closed unmerged and excluded after its tests were found
to depend on an unprepared fixture state.

The accepted portfolio is:

- PR 23, clean-green: attempt 1 green, review clear, terminal readiness;
- PR 24, first-attempt-flake: attempt 1 failed, the exact brokered rerun passed,
  and no repair ran;
- PR 25, persistent-ci-regression: both attempts failed and three bounded repair
  attempts returned unchanged without disabling `.pr-lab` or deleting fixtures;
- PR 26, seeded-review-finding: the expected high-severity mergeability finding
  was published and remained open for disposition;
- PR 27, conversational-change: one human request staged digest
  `89c491f79843929862530a75e3a4934e5992f82acba9a4767442e7bfa8ce5c06`,
  exact confirmation authorized operation
  `change:6455fb673af324b7ced254835a7ac23cbc5ba4bfc234b0151d9709cb96b747bb`,
  and host publication advanced head from `132669ba01868b653932c18aa1ca5ecc0a0038a9`
  to `cba626f9dbdb4e999b391cfcf41fa30573e2da5c` at epoch 2. Both CI attempts
  then rejected the README path as designed, and repair remained bounded without
  bypassing the scenario gate;
- PR 28, agent-repair: a legitimate repair advanced head from
  `463cdddf41374fe880f2d25e6ece15b0fa9982bb` to an App-published epoch-2 head,
  CI passed, coordinating review cleared, and the seeded finding resolved.

Qualification also delivered source safeguards
`a958a3219338caee733f29992e93339a333e5fe3`, which prevents repeated lifecycle
delivery to terminal Instances, and
`d6244c1d556a57d5dd3c58cb9f7c2161e56c12e8`, which forbids coding agents from
disabling deterministic scenario controls instead of repairing product defects.
The final portfolio had no unresolved Activities, ActivityFailed or
FiringFailed records, duplicate effects, self-loops, credential exposure,
manual pushes, approvals, merges, or History edits. A separate older PR20 still
exhibits non-terminal unresolved-activity retry churn and remains a recovery
obligation rather than CV3.DS1 acceptance evidence.
