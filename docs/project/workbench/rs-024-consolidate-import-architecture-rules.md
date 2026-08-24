---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/candidate-review.md
---

# RS-024 — Give import architecture rules one test owner

## Existing field to refine

Two test modules scan production imports:

- `tests/test_architecture.py` resolves relative imports and checks sibling and
  host-only composition rules; and
- `tests/unit/host/test_host_architecture.py` repeats the sibling rule with a
  scanner that does not resolve relative imports, while also owning unique
  architecture assertions.

The duplicate scanners do not interpret all Python syntax the same way. For
example, `from ..agents import X` resolves to `hamsterdan.agents` in the root
scanner but appears only as `agents` in the host-unit scanner.

This is executable architecture-policy locality, not a production architecture
change.

## Candidate boundary

Make `tests/test_architecture.py` the one owner of source import-direction rules
using its relative-aware scanner. Move the unique import assertions from the
host unit test into that owner. Keep the credential-free agent request-field
assertion in the host unit area because it checks a contract rather than source
imports.

Do not introduce a production import-analysis module or change current package
relationships merely to test them.

## Change Request

### CR-001 — Consolidate repository import scans and preserve every rule

Status: Parked

Likely files:

- `tests/test_architecture.py`
- `tests/unit/host/test_host_architecture.py`

Validation seeds:

- add or use a fixture proving relative imports resolve consistently;
- preserve sibling isolation, host-only concrete composition, no sibling import
  of `host`, no `examples` import from `host`, and the current
  `petrus.agenticus` ownership rule;
- keep credential-free request-field coverage in the host unit test;
- run both architecture test modules and `scripts/check quick`.

## Pull state

This candidate is captured but not pulled. No test consolidation, production
import, architecture decision, commit, or release action is authorized by this
record. ES-009 remains a learning session.
