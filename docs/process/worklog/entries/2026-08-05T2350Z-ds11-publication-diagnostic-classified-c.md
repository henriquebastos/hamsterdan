# DS11 publication diagnostic classified C

A credential-free diagnostic started from exact clean Hamsterdan
`a414a3a0025179c79e7b9f8d65ecc7bff930d516`. It used no key, provider,
subscription, paid operation, network repository, or remote mutation.

One new integration regression passes a canonical archive through the production
`GitPiWorkspaceProvider`, derives the host patch, and sends the unchanged
`CodingResult` contract through the real `HostGitPublisher`. A bounded local
authority implements GitHub object writes and exact ref compare-and-swap over a
local bare remote. Production clone, exact checkout, recovery lookup/fetch,
binary apply, index/path/mode checks, tree reproduction, blob/tree/commit
creation, fresh current-authority read, one ref advance, and idempotent replay
all succeed. Replay performs no second advance and receiver stages are removed.

The live attempt's retained `GitPublishError` cannot be the original publication
reason. Production Activity catches the original publisher error and returns a
failed typed outcome. After observing zero publication, the qualification
harness continued into replay, derived an empty diff from unchanged refs, and
called the publisher again. That secondary call deterministically raises the
retained empty/unchanged-patch `GitPublishError`. The original reason was present
only in suppressed, erased logging. The exact live rejection is therefore
classification C: safe retained evidence cannot prove either a production
publisher defect or an insufficient synthetic authority/setup contract.

Focused receiver, publisher, and Activity suites pass 56 tests. The full gate
passes formatting, Ruff, ty, nine Bun tests, source/wheel builds, and 333 Python
tests with one explicit provider test skipped. No production behavior or Petrus
pin changed. Before any separately authorized fresh live request, the
credential-free qualification contract must retain a stable publisher
stage/error category before replay and must stop replay checks after zero
publication. The orphaned qualification repository still requires a separately
approved administration identity with its exact owner/name supplied out of
band, repository-deletion authority confirmed on that exact target, and
post-delete not-found verification. No account-wide discovery is needed or
authorized.
