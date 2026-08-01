# GitHub App host and qualification portfolio completed locally

**Time:** 2026-08-01T03:35:00Z
**Roadmap:** CV1.DS1

Hamsterdan now contains the transferred PR-readiness Net, neutral contracts,
credential-free Amp runner, GitHub App package, and the host that composes them
through public Petrus Engine and Motus Activity APIs. GitHubKit owns App JWT and
installation-token mechanics; Hamsterdan owns registration validation,
selected-repository routing, exact authority, webhook custody, durable workflow
state, effects, and observability.

The App-owned ingress is complete for Amp deployment: a durable project webhook
relay wakes the orb and forwards exact signed bytes to the supervised loopback
host. The host verifies before parse, deduplicates, sanitizes, durably queues,
backs off retryable failures, parks poison deliveries, and sweeps persisted PR
Instances after restart or missed follow-up events. Operation clients are
narrowed to one repository; no App credential enters agent input, subprocess
environment, checkout, History, logs, or evidence.

The HBNetwork operator tooling inventories exact provider IDs, creates bounded
scenario PRs, prepares but never merges the broker cutover, and inspects visible
App ownership, immutable markers, exact-head workflow evidence, and commit
metadata separately from authenticated pusher attribution. Live preflight
passed for `HBNetwork/demo-pr-readiness`; its broker remains deliberately on the
legacy writer until the App host exists.

The full local qualification route passed 172 Python tests (with the opt-in
real-Amp test skipped by default), nine Bun relay tests, Ruff, formatting, ty,
wheel/sdist build, and credential/architecture guards. The opt-in real-Amp
read-only operation then passed separately in 33.96 seconds. Real GitHub
acceptance is not claimed: the private `henriquebastos/hamsterdan` repository
and HBNetwork Hamsterdan App registration do not exist, and current automation
credentials cannot create either provider resource.
