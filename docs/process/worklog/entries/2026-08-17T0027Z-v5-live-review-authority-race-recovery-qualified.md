# V5 live review authority-race recovery qualified locally

The first fresh selected-V5 clean-green attempt at
[`HBNetwork/demo-pr-readiness` PR 52](https://github.com/HBNetwork/demo-pr-readiness/pull/52)
preserves the failed live evidence that exposed the gap: head
`a9fa303fa7ccc7fbd55ff94a8d9ef14c4d539e28`, successful Actions run
`31979694600` attempt 1, and the
[App dashboard](https://github.com/HBNetwork/demo-pr-readiness/pull/52#issuecomment-5310261923).
A same-PR workflow delivery entered durable custody during opening-webhook
normalization. Settlement saw authority newer than the staged host grant and
correctly refused review, but the refusal escaped as an Activity and firing
failure that consumed the review baton.

Selected V5 now drains newly arrived due same-subject custody under the
per-instance lock before one final settlement. A residual arrival returns a
typed silent deferred round that retains the baton and stable Agenticus
operation. Once custody clears, an identified durable wake opens a fresh
numbered attempt with fresh request custody. Lost wake acknowledgement replays;
malformed or unbacked wake history fails closed; old operation-keyed request
stores migrate to attempt 1. Acknowledgement remains after settlement,
authority fencing is unchanged, and production remains untouched and default.

`scripts/check full` passed 1,133 Python tests, nine Bun relay tests, Ruff,
formatting, typing, and source/wheel builds. Oracle review found no blocker and
returned `clear to commit`. PR 52's failed canonical History remains unchanged;
a fresh selected-V5 clean-green PR is still required for live acceptance.
