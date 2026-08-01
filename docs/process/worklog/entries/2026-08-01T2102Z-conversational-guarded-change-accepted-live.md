# Conversational guarded change accepted live

CV2.DS2 completed on
[`HBNetwork/demo-pr-readiness` PR 15](https://github.com/HBNetwork/demo-pr-readiness/pull/15).
A natural `@hamster-dan` change request staged one digest-bound intent without
coding or Git mutation. An altered digest was rejected. Exact confirmation ran
the current same-orb Amp coding strategy in a disposable credential-free
checkout.

The agent changed only `.pr-lab/scenario.json`, replacing fingerprint
`hamsterdan:cv2-ds2:v1` with `hamsterdan:cv2-ds2:v2`. The host validated the
captured diff and published commit
`b90680615675721a4247131473b512a782b273e5` as `hamster-dan[bot]` through an
exact GraphQL ref compare-and-swap. The commit records stable operation and
payload-digest trailers. The head entered epoch 2; Actions failed once as the
fixture specifies, the host brokered attempt 2, and CI, coordinating review,
dashboard, and readiness converged successfully.

Operational qualification also found and corrected:

- provider-backed authority reads inside the runner's 50 ms cancellation poll;
- a persisted `review=unable` generation with no bounded recovery admission;
- silent agent and publication failure classification;
- nondeterministic coding-agent inability without bounded same-request retry;
- case-sensitive comparison between route-normalized and GitHub-canonical
  repository full names at the same-repository publication fence.

Final evidence: deployed source `6d8fbb788e832427c2661ba42e8a71b041dc1561`,
PR head `b90680615675721a4247131473b512a782b273e5`, CI run `30717688317`
at successful attempt 2, ready/current dashboard, 221 terminal inbox deliveries,
zero pending or failed deliveries, no Activity/Firing failure, and no duplicate,
self-loop, manual push, approval, merge, or credential-bearing log.
