# Project Agent Instructions

This is **Hamsterdan**, a GitHub-native PR-readiness application built on
Petrus. This project uses **Ariad**.

The agent is the **Driver**. The human is the **Navigator**. The Driver owns
repository operation, implementation, and verification; the Navigator owns
direction, product judgment, trade-offs, and acceptance.

## Required orientation

Before meaningful work, read the files that exist in this project:

- `README.md`
- `docs/project/briefing.md`
- `docs/project/decisions/index.md`
- `docs/project/roadmap/index.md`
- `docs/project/debt/index.md`
- `docs/process/development-guide.md`
- `docs/process/engineering-conventions.md`
- `docs/process/worklog/index.md`
- `docs/product/principles.md`
- `docs/references/index.md`
- `docs/project/exploration/index.md`

Read each index first, then only the records relevant to the current work.

## Delivery lifecycle

For non-trivial work:

1. Read and orient.
2. Present a Plan Checkpoint and wait for Navigator confirmation.
3. Implement with tests.
4. Present an Experience Report and wait for acceptance.
5. Present review, refactoring, and debt assessment and wait for confirmation.
6. Update documentation and run the coherence check.
7. Propose the history action and wait before committing or pushing.

Everything meaningful is tracked, including exploration, decisions, spikes,
and operational evidence. Prefer small reviewable changes. Do not silently add
scope.

## Architecture contract

- `host` is the only runtime composition root. It owns webhook custody,
  configuration, secrets, Petrus Engine lifecycle, dispatch binding,
  correlation, and observability.
- `github_app`, `agents`, and `readiness` are siblings. They may import neutral
  values from `contracts`; they must not import or hold concrete references to
  one another.
- The PR-readiness Net lives under `readiness/net`. It owns workflow decisions
  and knows no GitHub or agent provider.
- GitHub and agent effects execute as typed Motus Activities. No GitHub
  credential may enter agent territory.
- Import Petrus concepts from their defining modules. There is no root facade
  and no `impetus` compatibility package.

## Safety

Never commit App private keys, installation tokens, webhook secrets, PATs,
payload dumps, or local runtime state. External effects remain at-least-once
and require operation identity, lookup-first recovery, and current-authority
fencing.

Follow `docs/process/development-guide.md` for commands, validation, and local
project policy.
