# Authority and collaboration gates accepted live

CV3.DS2 completed on isolated PR29-33 in
[`HBNetwork/demo-pr-readiness`](https://github.com/HBNetwork/demo-pr-readiness)
under branch-only ruleset `20242556`. The dedicated base required strict
`lint`, `type`, `unit`, `build`, and `integration` checks, one approval, and
review-thread resolution. It did not alter `main`, scenario-control files, or
accepted PR14/15 and PR23-28.

[PR29](https://github.com/HBNetwork/demo-pr-readiness/pull/29) received a real
distinct `hsbastos` approval and was the portfolio's only merge, advancing the
isolated base from `661002b8bdcb57d0ea7c2d7fb4fbfa58af3aae60` to
`11e2c9a2865e96d2db54cdb9ac0338a25365aaa9`.
[PR30](https://github.com/HBNetwork/demo-pr-readiness/pull/30) then proved
strict stale but clean authority and an exactly confirmed App update from
`b8bb6e6bdbacedbbba1bcb9f92af5326fd2eff61` to
`24e2adf15e6414c15a6bc5f7186d3aa8e366f608`. Its confirmation digest was
`a544b5473a9fc9befa8c3d4a8918e55b53c42c96936fe2b466ca278860fcae61` and its
single change operation was
`change:a2fdf7e01858cbe5aeb420867949808f952762ef0c0be99e46ce05d195300742`.
[PR31](https://github.com/HBNetwork/demo-pr-readiness/pull/31) proved a real
same-line conflict and an exactly confirmed App resolution from
`c7845ba395610f51a98d0d889d6f7740dc7b9750` to
`c25712f84135fb7b12eead8508e56bf344bdc587`. Its confirmation digest was
`afb87579887159473c04edfc201782eb1e9b6e34bb3f0cc20c104c9b3757a5fb` and its
single change operation was
`change:68e733019142116dfe92780c533d5f285dabd34c8462a00447674a950282d81b`.
Both publications were two-parent, App-authored commits containing the exact
old head and current base; only the original neutral demonstration path
changed.

[PR32](https://github.com/HBNetwork/demo-pr-readiness/pull/32) opened as a real
draft and caused no admission, Activity, or App comment. Its ready event created
one epoch-1 admission at unchanged head
`b63946c52a679c4584881bb08f1c924784f56391`.
[PR33](https://github.com/HBNetwork/demo-pr-readiness/pull/33) kept unchanged head
`48947f8650714290cb613ec43ebb080094d5e6a7` through one requested reviewer, a
formal changes-requested inline thread, one unresolved conversation, a later
formal approval while the thread still blocked, reviewer resolution, final
`reviewDecision=APPROVED`, and collaboration-clear readiness.

All five PRs reached their expected durable projection under deployed source
`2eb0c6eb513da34630572d6b26963d3fba1ee353`. Across 99 Activity requests there
were no unresolved Activities, ActivityFailed, or FiringFailed records. The
final host was healthy with installation reconciled, 22 applications, and 827
terminal / zero pending or failed inbox deliveries. Every dashboard operation
was unique; no duplicate effect, self-loop, credential exposure, raw payload,
manual branch update, force-push, bypass, or History edit occurred. PR30-33
remain open and unmerged.

GitHub authority was inspected directly with separate operator sessions for
`henriquebastos` and `hsbastos`; those credentials remained in ignored runtime
configuration and never entered source, agents, logs, or History. The existing
operations thread independently corroborated provider events from durable inbox
and History evidence without mutation. PR20 remains CV3.DS3 debt: its currently
drained deliveries do not prove unresolved-Activity recovery is fixed.
