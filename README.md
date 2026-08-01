# Hamsterdan

Hamsterdan is a GitHub-native PR-readiness application powered by
[Petrus](https://github.com/henriquebastos/impetus). It coordinates durable
review, Actions observation, human decisions, and guarded repository effects
through one explicit Petri-net workflow.

This repository is private during the first controlled validation. The first
real deployment uses an HBNetwork-owned private GitHub App registration and a
selected-repository installation in the HBNetwork sandbox organization. Source
ownership, App registration ownership, installation ownership, and deployment
state are intentionally separate.

## Status

The standalone application, transferred PR-readiness Net, installation-authenticated
GitHub boundary, durable App webhook ingress, host composition, credential-free
Amp agent runner, guarded effects, and HBNetwork qualification tooling are
implemented and locally qualified. Real-provider acceptance is pending the
unavoidable provider bootstrap: create the private source repository, register
the HBNetwork-owned private App, generate its key, install it on the selected
demo repository, and run the controlled acceptance portfolio.

## Architecture

```text
                      host
             custody / composition
                       |
        +--------------+--------------+
        |              |              |
   github_app        agents       readiness/net
        |              |              |
        +--------------+--------------+
                       |
                   contracts
```

`host` is the only concrete composition root. The sibling subsystems share
neutral contracts but do not import one another. The host creates and drives
public `petrus.engine.Engine` instances; the readiness Net decides work, and
GitHub or agent providers perform typed Motus Activities.

## Development

Python 3.14, [uv](https://docs.astral.sh/uv/), and Bun 1.3.10 are required.

```sh
uv sync --frozen
scripts/check full
```

The Petrus dependency is pinned to the accepted namespace-migration commit.
Canonical environments never float on Petrus `main` or depend on a local
checkout.

## Runtime ownership

The host authenticates as the GitHub App, obtains one-hour installation tokens
through GitHubKit, and narrows each operation client to one admitted repository.
The App-owned webhook reaches the orb through a durable Amp relay; the relay
forwards exact signed bytes to the host but has neither the webhook secret nor
GitHub credentials. The host verifies, sanitizes, durably accepts, deduplicates,
and asynchronously processes each delivery. Failed deliveries back off and
eventually park; persisted PR Instances are reconciled on startup and every
minute so a missed follow-up event does not strand active work.

## Operator qualification

The production-owned, JSON-output demo CLI is available as
`python -m hamsterdan.operator` or `scripts/hamsterdan-demo`. Start with the
non-mutating `preflight`; scenario creation and broker preparation are explicit
human operator actions and never merge, force-push, or bypass protection.

The complete private App registration, supervised host, selected-repository
installation, broker cutover, inspection, rotation, and isolated rollback
sequence is in [the HBNetwork operator runbook](docs/operator/README.md). Live
HBNetwork acceptance is intentionally not marked complete by this tooling.
