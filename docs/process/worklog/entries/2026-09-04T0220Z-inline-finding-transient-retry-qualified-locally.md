# Inline finding transient retry qualified locally

A controlled production journey on PR #64 retained three OpenAI review
findings but initially published only the first native inline comment. The
exact recovery command later found that first marker and published the other
two findings unchanged, proving that review discovery and per-finding identity
were intact. The run was closed and discarded before repair at the Navigator's
direction.

Diagnosis found an incomplete bounded retry in `CommentPublisher`: transport
exceptions performed lookup-first recovery and used the second attempt, while
a returned transient HTTP response performed the lookup and then raised
immediately. A deterministic regression reproduced that path with the real
publisher and a fake HTTP transport. The boundary now retries recognized
secondary-limit, bare validation, rate-limit, and server responses once after
the absent-marker lookup and a fresh full authority fence. Structured payload
and authorization failures still stop after one request.

The regression failed before the fix and passes afterward for all four
transient response classes. The adjacent publisher and V5 publication-gate
suite passes 131 tests; `scripts/check quick` passes; and `scripts/check full`
passes 1,239 tests. The original provider response class was not retained in
History, so that independent diagnostics gap is recorded in the debt ledger.
