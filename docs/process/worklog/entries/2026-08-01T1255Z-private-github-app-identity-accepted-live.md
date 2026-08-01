# Private GitHub App identity accepted live

**Time:** 2026-08-01T12:55:00Z
**Roadmap:** CV1.DS1

The private HBNetwork-owned `hamster-dan` App is installed only on
`HBNetwork/demo-pr-readiness`. Startup proved App ID `4452953`, installation ID
`150464548`, repository ID `1316665126`, exact selected-repository routing,
five subscribed workflow events, and the least practical live permission set:
Administration read, Actions read, Contents write, Issues write, and Pull
requests write. GitHub denied PR-thread comments when Pull requests was read;
an empty-body non-mutating probe and the provider's accepted-permissions header
proved the needed write grant. Validation now checks both the App registration
and the installation's accepted permissions.

Two transport defects surfaced during live ingress. First, network errors were
not normalized. Then GitHubKit's context-local temporary sync client was closed
before a streamed response body was read. Commits `fce1472` and `3ed9059`
normalize the boundary and consume each response inside its client scope. All
16 originally held deliveries subsequently drained with no new raw transport
errors. Commit `35d2ee5` also retains an exact conversation publication Work,
reissues the lookup-first operation at most three times, and blocks rather than
silently advancing after exhaustion. A later `/hamsterdan status` interaction
published the recovered reply and dashboard as `hamster-dan[bot]` without a
duplicate immutable marker.

The complete acceptance route is
[HBNetwork/demo-pr-readiness#14](https://github.com/HBNetwork/demo-pr-readiness/pull/14),
head `4e4f411c0ef352d7b39f7c7071380c433aa63a3b`. The installation identity
created the one-file scenario commit through Git data REST; GitHub linked both
authenticated author and committer to `hamster-dan[bot]`, while explicit Git
metadata remained `Hamsterdan <hamster-dan[bot]@users.noreply.github.com>`.
Workflow run `30699749460` failed as designed on attempt 1. The App published
dashboard comment `5151424752`, exact rerun marker comment `5151425962`, and
operation `actions-rerun:27ad783ee9233e7ae1b70d4c8ab54dcb7ee5821a27df371f886465bb32b1514c`.
The merged strict broker accepted only the exact App bot/type/marker grammar;
attempt 2 passed all six jobs. Readiness advisory `5151430217` then published
from the App at the same head. The production inspection command passed every
identity, marker, head, workflow, and attribution check.

A supervised host restart minted a fresh repository-scoped token with a
one-hour TTL, reopened three persisted applications, and left PR 14's 458
History records and three comments unchanged. GitHub App delivery
`d41401f0-8da4-11f1-89e9-e2f2ba9c7ca0` was then redelivered from the provider.
Durable custody recognized the same GUID; inbox count remained 80 terminal,
History remained 458 records, and no Activity failure or duplicate effect was
created. No token, key, signature, raw webhook payload, or comment prose entered
logs or evidence.

The App broker cutover was merged by the trusted human operator in PR 13. The
legacy host remains stopped; its old repository webhook is inactive, so there
is no dual writer. The temporary demo deploy key was removed. Rollback remains
an explicit stop/grammar/start handoff rather than shared state or credentials.

Finally, the Petrus namespace-migration history was published at the same SHA
to the private `henriquebastos/petrus` repository. Hamsterdan now pins that
location and CI fetches it through one read-only Petrus deploy key that is
removed before project code executes. Private-source CI run `30700556647` at
Hamsterdan commit `634b22a` passed dependency sync, key cleanup, Ruff,
formatting, ty, nine Bun tests, 179 Python tests with one opt-in skip, and
wheel/sdist build without credential material in logs.
