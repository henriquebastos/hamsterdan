---
status: Decided
raised: 2026-09-01
decided: 2026-09-01
recorded: 2026-09-02T1941Z
deciders:
  - Henrique (Navigator)
related:
  - CV19
  - ../../roadmap/cv19-private-v0-1-production/launch-runbook.md
---

# Operator credentials live in a standing config store

## Decision

The operator's Hamsterdan credentials live permanently in
`~/.config/hamsterdan/` (directory mode 0700, files 0600), replacing the
earlier ephemeral stage-and-delete handover directory. `env` is a
dotenv-style `KEY=VALUE` file carrying the App identity, exe.dev API token,
agent key, Petrus install token, and installation metadata. File-shaped
secrets are sibling files referenced from `env` by `*_FILE` variables: the
App private key PEM, the webhook secret, and the exe.dev SSH key, plus the
demo actor host files. No credential value is ever committed or printed;
records refer to secrets by prefix, size, or hash only.

## Rationale

Deploy and operations sessions repeatedly asked Henrique to re-stage
secrets under the ephemeral protocol. A standing store matches his existing
`~/.config/orbital/env` convention, and keeping file-shaped secrets as
byte-exact sibling files avoids shell-quoting hazards for multi-line key
material.

## Consequences

- Tools parse `env` line by line on the first `=`; sourcing it in a shell
  is forbidden because values are unquoted and may contain quotes.
- Provisioning consumes exact file bytes: the webhook secret includes its
  trailing newline, and stripping it trips the playbook's refuse-implicit-
  secret-replacement guard.
- File-shaped consumers take the `*_FILE` paths directly; they already
  match the host configuration's file-path shape.
