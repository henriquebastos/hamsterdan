# Runtime-owned agent deadline qualified locally

After the exact-head Actions correction resumed fresh selected-V5
[`HBNetwork/demo-pr-readiness` PR 53](https://github.com/HBNetwork/demo-pr-readiness/pull/53),
all seven webhook rows reached terminal custody without an Activity or firing
failure and the
[App dashboard](https://github.com/HBNetwork/demo-pr-readiness/pull/53#issuecomment-5310594150)
became visible. Its real OpenAI-backed review ran for approximately five
minutes, then produced typed fail-closed `RoundUnable(runtime_lifecycle)` with
no readiness advisory.

The durable Pi ledger retained cancellation, zero accepted appends, no output,
and clean client-close evidence. Investigation proved Hamsterdan's runner had
cancelled at its independent 300-second deadline, preempting the exact Petrus A2
runtime's finite 900-second wall policy. The default runner now lets Petrus own
that deadline while continuing 100 ms current-authority polling. It checks
authority again after synchronous settlement, retains an explicit finite test
deadline, and strictly validates timing values.

Focused Pi A2 unit and integration checks passed 72 tests. The full checkpoint
passed 1,151 Python tests, nine Bun relay tests, Ruff, formatting, typing, and
source/wheel builds. Oracle identified strict timing-type validation as the one
review blocker; boolean and nonnumeric cases were added, all checks reran green,
and the follow-up returned `clear to commit`. PR 53 remains preserved failure
evidence. No hidden retry, provider substitution, or new live PR occurred in
this slice.
