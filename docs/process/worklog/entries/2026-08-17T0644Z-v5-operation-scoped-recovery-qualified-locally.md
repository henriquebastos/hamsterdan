# V5 operation-scoped recovery qualified locally

After the coding and restart corrections, selected-V5 PR 60 passed all six
checks but its completed provider review explicitly returned `unable` with zero
findings. V5 retained typed `RoundUnable`, no effect fault, and no finding
publication. The operation was not retried.

Fresh [PR 61](https://github.com/HBNetwork/demo-pr-readiness/pull/61) then
qualified the blocked three-finding checkpoint and received one explicit author
[repair request](https://github.com/HBNetwork/demo-pr-readiness/pull/61#issuecomment-5312521927).
The corrected 32-call coding boundary produced App-authored commit
[`e3d11a8`](https://github.com/HBNetwork/demo-pr-readiness/commit/e3d11a8171dbbb4af910b7c199a5f240dfb2441e),
which changed only the two defect-bearing fixture files with three additions
and three deletions. All six repaired-head jobs passed.

The exact ref CAS landed while GitHub's immediate PR projection still reported
the old head, so V5 correctly retained `FaultM` rather than forging `Pushed`.
The stable operation is
`push:comment:5312521927:02e084286c2324220d7b25164b685655ec87a07d:i1`.
No provider or Git operation was retried.

The live ambiguity exposed that V5's real classifier could not reach its
existing operation-prefix recovery mailboxes: it copied production's
`target + operation` declaration and concatenated the fields. V5 now declares
operation-only recovery, preserves one bounded graphic operation byte-for-byte,
and requires the admitted human comment to contain it verbatim. Production is
unchanged. One hundred eighty-eight focused protocol, ingress, mutation-gate,
and actor-loop tests passed, followed by quick checks, 1,183 Python tests, and
nine Bun relay tests. Oracle returned `clear to commit`. Redeployment and one
explicit lookup-first recovery of PR 61 remain.
