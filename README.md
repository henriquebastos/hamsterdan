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

The standalone project boundary is being established. GitHub App credentials,
webhook ingress, PR-readiness behavior, and live effects are not implemented in
this repository yet. The qualified source behavior remains in Petrus's
`examples/pr_readiness_next` package until it is transferred under parity
tests.

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

Python 3.14 and [uv](https://docs.astral.sh/uv/) are required.

```sh
uv sync --frozen
scripts/check full
```

The Petrus dependency is pinned to the accepted namespace-migration commit.
Canonical environments never float on Petrus `main` or depend on a local
checkout.
