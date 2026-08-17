# Selected-V5 clean-green completion qualified live

Fresh selected-V5
[`HBNetwork/demo-pr-readiness` PR 55](https://github.com/HBNetwork/demo-pr-readiness/pull/55)
first proved that the canonical provider review could complete, then exposed a
new readiness race. Its six checks succeeded and its App dashboard landed, but
the dashboard comment's own webhook was still in same-PR custody when readiness
tried to publish. The temporary authority fence became permanent `ABlocked`, so
no advisory appeared. PR 55 remains unchanged as the failure evidence.

Readiness publication now retains an exact deferred request and blocker rather
than classifying unstaged custody as provider failure. Host reconciliation wakes
that request only after the named delivery is staged or terminal. The same
operation re-enters lookup-first settlement; changed authority moves before a
fresh request, queued mutation or close wins before retry, unrelated terminal
rows cannot wake it, and malformed durable wake evidence fails closed.

After deployment, fresh
[`HBNetwork/demo-pr-readiness` PR 56](https://github.com/HBNetwork/demo-pr-readiness/pull/56)
completed the real clean-green journey at head
`7e3266a5eb87f921485295358af9745016b4ee15`. All six jobs in
[Actions run 31989355776](https://github.com/HBNetwork/demo-pr-readiness/actions/runs/31989355776)
succeeded. One canonical provider review followed three authority-safe
deferrals; the
[App dashboard](https://github.com/HBNetwork/demo-pr-readiness/pull/56#issuecomment-5311272876)
and
[readiness advisory](https://github.com/HBNetwork/demo-pr-readiness/pull/56#issuecomment-5311276734)
are visible under the exact head-bound operation.

Real App updates stressed the custody boundary: ten exact announcement
deferrals and wakes occurred before the eleventh identical request landed, all
under `ready:7e3266a5eb87f921485295358af9745016b4ee15:i1`. Canonical History
contains 1,065 records, 26 Activity requests and completions, and no Activity,
firing, or quarantine failure. All 18 PR-specific webhook rows are terminal.
The production `inspect` command passed dashboard, advisory, ownership,
exact-head workflow, and legacy-marker checks; all eight preflight checks also
passed.

The implementation checkpoint passed 1,168 Python tests, nine Bun relay tests,
Ruff, formatting, typing, and source/wheel builds. Oracle returned
`clear to commit`. PR 56 remains open and unchanged as the accepted live
clean-green evidence. Additional fresh V5 user journeys and GitHub-site
recordings remain before CV17 closes.
