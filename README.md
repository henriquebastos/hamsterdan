# Hamsterdan

Hamsterdan is a GitHub-native PR-readiness application powered by
[Petrus](https://github.com/henriquebastos/petrus). It coordinates durable
review, GitHub Actions observation, human decisions, guarded repository effects,
and readiness advisories through one explicit Petri-net workflow.

This is an early source publication under the [Apache License 2.0](LICENSE).
Copyright 2026 Henrique Bastos. Third-party material retains its own notices.
The pinned Petrus source dependency is public. Public CI remains disabled;
running Hamsterdan requires a configured GitHub App and runtime credentials.
See [contributing](CONTRIBUTING.md),
[security reports](SECURITY.md), and the [code of conduct](CODE_OF_CONDUCT.md).

Historical tags and operational records describe private qualification;
they are not public release or compatibility promises.

## Status

The private `0.1.0` candidate uses non-sharded V5 as its only runtime topology.
The former production topology, runtime selector, and sharded prototype are not
available. A stale selector or former/unlabeled durable state fails closed
without mutation.

The V5 route has accepted deterministic evidence across eleven semantic
journeys and real GitHub evidence for clean green, transient-CI recovery, and a
complete three-actor repair. Production runs release `1eef74a` with Petrus
`913acb0`, qualified through the local release gate and image verification.
[PR85](docs/project/roadmap/cv19-private-v0-1-production/proof/pr85.md) completed
review, App repair, clear rereview, human approval, and one readiness advisory.
The exercise also found misleading approval wording in a status reply and an
older Pi cleanup record that causes shutdown errors. Both findings remain open.
Capture acceptance and broader repository monitoring remain under
[CV19](docs/project/roadmap/cv19-private-v0-1-production/index.md).

## Architecture

```text
                      host
             custody / composition
                       |
        +--------------+--------------+
        |              |              |
   github_app        agents    readiness/net_v5
        |              |              |
        +--------------+--------------+
                       |
                   contracts
```

`host` is the only concrete composition root. The sibling subsystems share
neutral contracts but do not import one another. GitHub and agent effects run as
typed Motus Activities; GitHub credentials stay in the host and never enter an
agent territory.

The shortest maintainer path through one reconciliation is:

```text
signed GitHub webhook / startup or periodic reconciliation
  -> HostService custody and per-PR activation
  -> PrReadinessV5Application
  -> V5Runtime / petrus.engine.Engine
  -> readiness.net_v5.topology
  -> typed Motus Activity request and result
  -> authority-fenced V5 fold and publication
```

The V5 topology owns nine cohabited concern loops plus lifecycle control. Typed
mailboxes and specialized readiness facts make durable alternatives explicit;
current authority, external operation identity, and lookup-first recovery fence
every effect. Each PR has an independent Engine and History. Durable webhook,
Dispatch, timer, and runnable stores survive host reconstruction. Hamsterdan
never merges.

For newly observed PRs, the initial summary must land before other workflow
Activities start. Later summary updates keep updating that same comment and
do not pause the workflow.

Start with:

- `src/hamsterdan/host/service.py` for runtime composition and custody;
- `src/hamsterdan/host/v5/application.py` for provider-to-V5 reconciliation;
- `src/hamsterdan/host/v5/runtime.py` for Engine, Dispatch, Worker, and recovery;
- `src/hamsterdan/readiness/net_v5/topology.py` for the sole workflow; and
- `src/hamsterdan/readiness/net_v5/gating.py` for typed Activity gates.

## Development

Python 3.14, [uv](https://docs.astral.sh/uv/), and Bun 1.3.10 are required.

```sh
scripts/build-secrets scripts/sync-dependencies
scripts/check full
```

Orb setup also installs and starts Docker and Graphviz so the adjacent Petrus
checkout can run its PostgreSQL and graph-validation feedback locally. Orb
resume checks restart Docker when needed; no manual daemon setup is required.

Petrus is a public source dependency pinned to exact revision `913acb0`.
The existing build wrappers still retrieve a dedicated read-only
`PETRUS_GITHUB_TOKEN` from the separate `hamsterdan-build` vault.
Orb setup presents it only through temporary Git askpass/config files and
removes those files on every outcome. Canonical environments never float on
Petrus `main`, assume package publication, or depend on a local checkout.

Application starts retrieve either the development or production 1Password
Environment through `scripts/hamsterdan-host` and the shared secret launcher.
See [deployment and credential operations](deployment/README.md) for the schema,
bootstrap paths, migration status, and restart/recovery workflow.

## Runtime ownership

The host authenticates as the GitHub App, obtains one-hour installation tokens
through GitHubKit, and narrows each operation client to one admitted repository.
The App webhook reaches the orb through a durable Amp relay. The host verifies,
sanitizes, durably accepts, deduplicates, and asynchronously processes each
delivery. Persisted PR instances are reconciled on startup and periodically so
a missed follow-up event does not strand active work.

The existing private App is HBNetwork-owned and can be installed only on
HBNetwork repositories. Another owner needs its own private App registration or
a later deliberately public App contract.

## Operator qualification

The JSON-output operator CLI is available as `python -m hamsterdan.operator` or
`scripts/hamsterdan-demo`. Start with the non-mutating `preflight`; scenario
creation and broker preparation are explicit human actions and never merge,
force-push, or bypass protection.

The private App registration, supervised host, selected-repository installation,
broker cutover, inspection, rotation, and rollback sequence is in the
[HBNetwork operator runbook](docs/operator/README.md). Do not start
`hamsterdan-host` merely to inspect this candidate: existing durable webhook
state may cause GitHub effects.

## Demo video

The Remotion source under `tools/demo-video` preserves the accepted PR47
presentation. It is secondary to production, is not a host launch prerequisite,
and receives no additional browser download during orb setup. Whether to retain
or remove the studio is deferred to the post-production open-source audit.
