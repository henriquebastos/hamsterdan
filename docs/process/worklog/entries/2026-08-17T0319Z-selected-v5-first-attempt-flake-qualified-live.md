# Selected-V5 first-attempt flake qualified live

Fresh selected-V5
[`HBNetwork/demo-pr-readiness` PR 57](https://github.com/HBNetwork/demo-pr-readiness/pull/57)
qualified the real transient-CI recovery journey at head
`4db1e173ed22aa0d314cfd5bac0be889eff6e9c8`. Attempt 1 of
[Actions run 31990573431](https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31990573431)
failed in the controlled `scenario-control` job. Hamsterdan posted exactly one
[App-owned rerun marker](https://github.com/HBNetwork/demo-pr-readiness/pull/57#issuecomment-5311358830)
bound to that run and head under
`rerun:L1:e09bd0a7017f59322fae5b6b081863c0c0704ed0fef37dddc6ae7b37133a4c63`.
The strict broker accepted it once, and attempt 2 passed all six jobs on the
same run and unchanged head.

One canonical provider review settled clear after five authority-safe
deferrals. The
[App dashboard](https://github.com/HBNetwork/demo-pr-readiness/pull/57#issuecomment-5311368890)
and
[readiness advisory](https://github.com/HBNetwork/demo-pr-readiness/pull/57#issuecomment-5311372351)
are visible under the exact head. No coding/repair agent, Git/ref mutation,
second rerun, finding, or merge effect occurred.

Canonical History contains 1,368 records and 35 matched Activity requests and
completions with no Activity, firing, or quarantine failure. One rerun landed,
one review completed, and the final readiness advisory followed twelve exact
custody deferrals; all thirteen announcement requests were byte-for-byte
identical under one operation. All 23 PR-specific webhook rows reached terminal
custody, the host remained healthy, and the operator `inspect` command passed
App ownership, dashboard, readiness, exact-head workflow, and legacy-marker
checks. PR 57 remains open and unchanged as the live evidence. The project-wide
checkpoint passed 1,168 Python tests, nine Bun relay tests, Ruff, formatting,
typing, and source/wheel builds.
