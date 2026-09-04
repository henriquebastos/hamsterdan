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

The first clean image build then exposed a separate omission from the recent
three-vault migration: `env-ops.tpl` did not carry the private Petrus source
token required by the release builder. The existing read-only token was
streamed directly from `hamsterdan-dev` into a deployer-owned
`hamsterdan-ops/petrus-github-token` item without printing or local persistence.
The operations template and its exact-name contract now include that build-only
authority; it remains absent from production runtime custody.

The first fresh run after deploying the immediate retry, PR #66, retained all
three findings and published the first two before the third returned the same
blocked terminal. It was closed unmerged and discarded before human review or
repair. PR #64 had already proved that the exact third payload and anchor could
publish unchanged after time passed, isolating the remaining defect to retry
timing. [GitHub's REST guidance](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit)
requires waiting at least one minute after a secondary limit when no provider
delay is available. The publisher now makes
that bounded pause before its single retry, and the publication Activity has a
120-second heartbeat window so the wait remains one valid execution. Injected
delay and composition regressions cover both timings without slowing tests.

PR #67 exercised that paced build from a fresh head. The first two findings
landed, the third stayed absent beyond the retry window, and the Activity
completed as `ReviewBlocked` without taking the delay path. The run was closed
unmerged and discarded. Because the old blocked terminal discarded the
provider response class, the next diagnostic slice carries only a closed class,
HTTP status, and validated structural field/code atoms through canonical
History. Provider messages and bodies remain outside retained state. This
instrumentation must identify the rejection on a new disposable PR before the
final clean proof run proceeds.
