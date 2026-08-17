# Canonical agent response contract qualified locally

Fresh selected-V5
[`HBNetwork/demo-pr-readiness` PR 54](https://github.com/HBNetwork/demo-pr-readiness/pull/54)
passed all six required jobs in
[Actions run 31984786963](https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31984786963)
and published the
[App dashboard](https://github.com/HBNetwork/demo-pr-readiness/pull/54#issuecomment-5310788618).
After three authority-safe deferred attempts, its provider-backed Pi helper ran
for approximately 329 seconds, settled with one accepted append, and closed
cleanly. This is real-route evidence that the DS4.15 runtime-owned deadline no
longer cancels valid work at 300 seconds.

Strict result admission then rejected the response as `output_schema`, so V5
emitted typed `RoundUnable`, kept readiness fail-closed, and published no
readiness advisory. The canonical prompt had referred to the result schema but
did not supply it, while the pinned Petrus runtime offers no separate
structured-output schema channel.

Every Pi prompt now includes a compact deterministic response contract for its
exact closed top-level and nested fields, request-relative values, closed
vocabularies, and cross-field invariants. The strict validators remain
unchanged and no partial response is repaired. Prompt version 2 also makes a
retained version-1 operation with the same identity fail closed before new
authority or execution instead of silently replaying incompatible output.

Focused agent and host checks passed 129 tests. The full checkpoint passed
1,156 Python tests, nine Bun relay tests, Ruff, formatting, typing, and
source/wheel builds. Oracle returned `clear to commit`. PR 54 remains preserved
failure evidence; no hidden retry occurred, and a fresh selected-V5 PR is still
required to prove provider-produced clean-green review completion.
