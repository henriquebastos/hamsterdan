# Reused-head Actions association qualified locally

A fresh production proof attempt on
[`HBNetwork/demo-pr-readiness` PR 65](https://github.com/HBNetwork/demo-pr-readiness/pull/65)
reused the exact commit from discarded PR 64. The opening webhook remained in
durable retry with `GitHubBoundaryError`, before manifest staging or any App
publication. The run was closed and discarded as diagnostic evidence.

The live Actions API returned workflow runs for both PRs because they shared a
head SHA. GitHub empties the `pull_requests` projection for a run after its PR
closes. `GitHubAuthority.workflow_runs` filtered by exact head before validating
every remaining run, so PR 64's empty association made PR 65's otherwise valid
current evidence unavailable.

The provider boundary now admits a same-head workflow run only when its typed
`pull_requests` projection explicitly contains the current PR number. Empty or
foreign associations cannot authorize current workflow evidence; malformed
association projections still fail closed. A regression using a current run
beside an empty-association historical run failed before the correction and
passes afterward. The complete GitHub provider unit file passes 79 tests, and
`scripts/check quick` passes.
