---
status: Completed
captured: 2026-08-24
pulled: 2026-08-24
completed: 2026-08-25
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

Status: Done

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

The Navigator pulled this Refinement Story as the prerequisite to strengthening
the repository quality gate. Import-direction rules now have one relative-aware
owner in `tests/test_architecture.py`; the credential-free agent request-field
assertion remains in the host unit area.

Focused architecture and check-command validation passed 16 tests. The default
and path-scoped quick profiles passed, including 10 architecture checks.
Independent review found one dropped positive composition assertion, missing
`contracts` protection, broad module-prefix matching, and weak command-interface
coverage; all four findings were corrected and revalidated. The Navigator accepted the result on 2026-08-25.
