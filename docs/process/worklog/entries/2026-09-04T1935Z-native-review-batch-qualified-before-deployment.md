# Native review batch qualified against GitHub before deployment

The fresh production proof campaign separated two failures. PR #72 exhausted
four OpenAI review attempts as `RoundUnable` before publication and was closed
unmerged. PR #73 produced the expected three findings, but three separate
review-comment mutations again landed only the first two before
`review.publish` retained `ReviewBlocked(failure_class=transport_ambiguity)`.
That PR was also closed unmerged before any human review or repair action.

The previously accepted PR #61 presented all findings through one conversation
comment. The per-finding native presentation introduced on 2026-09-02 changed
that provider shape to several consecutive content mutations. GitHub documents
both a native review endpoint whose `comments` array creates multiple inline
comments and secondary limits on content creation. The publication gate now
uses one review submission for all anchored findings in a round. Each finding
keeps its own marker, line thread, suggestion, lookup-first reconciliation, and
durable identity; an ambiguous outcome is reconciled marker by marker before
another exact-head-fenced attempt.

This provider shape was checked manually before deployment. The production
service was stopped, fresh disposable
[PR #74](https://github.com/HBNetwork/demo-pr-readiness/pull/74) had zero inline
comments, and one direct request authenticated as the Hamsterdan App submitted
the three hero anchors through `POST /pulls/74/reviews`. GitHub returned 200 and
created comments `3937324010`, `3937324018`, and `3937324024` at `gate.py:10`,
`gate.py:16`, and `cache.py:11`. All three belong to
[review `5117101264`](https://github.com/HBNetwork/demo-pr-readiness/pull/74#pullrequestreview-5117101264),
and an independent API read confirmed the App identity, shared review id, and
exact anchors. PR #74 was closed unmerged.

The publisher and gate suite passes 136 tests, `scripts/check quick` passes,
and the three integration journeys initially exposed by the new fake endpoint
pass against a batch-aware provider fake. `scripts/check release` passes 1,245
tests in its parallel run and 1,245 tests with 18 platform deselections in its
independent serial run. No batch code had been deployed at this checkpoint.
