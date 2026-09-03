# Project Agent Instructions

<!-- ariad-entrypoint: docs/ariad/index.md -->
@docs/ariad/index.md
If the @path directive is not expanded by this runtime, read `docs/ariad/index.md` directly before meaningful work.

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

- Current operational `src/hamsterdan` remains the V5-only system described in
  the project briefing until final cutover. For current-runtime fixes, `host` is
  the only composition root and owns Petrus runtime custody; `github_app`,
  `agents`, and `readiness` remain isolated siblings over neutral contracts; and
  the Net under `readiness/net_v5` owns workflow decisions.
- Non-selectable `src/hamsterdan2` construction follows the
  [CV21 outer-system architecture](docs/project/roadmap/cv21-composable-outer-hamsterdan/architecture.md)
  and [CV22 workflow architecture](docs/project/roadmap/cv22-decomposable-readiness-workflow/architecture.md).
  There, `host` remains the only concrete application composition root,
  `readiness` owns one-PR Petrus execution and the sole temporary current-Net
  bridge, and `workflow` owns pure boundary language before CV22 adds the
  replacement Net. No other new module may import current `hamsterdan` code.
- GitHub and agent effects execute as typed Motus Activities. No GitHub
  credential may enter agent territory.
- Import Petrus concepts from their defining modules. There is no root facade
  and no `impetus` compatibility package.

## Navigator communication

The chat response is the primary deliverable; files are references for
later. Whenever the Driver introduces a coined concept, label, or
shortcut — or asks the Navigator to rule a decision — the response
itself must explain it with at least one concrete scenario. Never
assume the Navigator will open a markdown file to decode a term the
response invented. Every decision presented for ruling must state: the
question in plain words, one concrete example, the options with their
consequences, and a recommendation.

## Safety

Never commit App private keys, installation tokens, webhook secrets, PATs,
payload dumps, or local runtime state. External effects remain at-least-once
and require operation identity, lookup-first recovery, and current-authority
fencing.

Follow `docs/process/development-guide.md` for commands, validation, and local
project policy.

## Secrets

Secrets resolve from 1Password via the committed `env.tpl`; direnv injects them
into the shell automatically (no rendered file on dev machines). Orbs and
servers render `env.tpl` to `.env` once at boot with `op-env-refresh` (auth via
`OP_SERVICE_ACCOUNT_TOKEN`). After rotating a credential in 1Password, re-enter
the directory (`direnv reload`) or re-run `op-env-refresh`.
