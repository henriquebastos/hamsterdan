---
status: Candidate
captured: 2026-08-25
navigator: Henrique
source: rs-029-broaden-non-blocking-quality-evidence.md
---

# RS-031 — Review reflective V5 loop assembly

## Existing field to refine

The structural-practice audit reports two reflective reads in
`readiness/net_v5/topology.py`: optional `GATES` and `DERIVED` module exports are
collected with `getattr(..., {})`. This is the only finding in the initial
ast-grep rule.

For example, a loop module that accidentally renames `GATES` silently contributes
no gates. Direct module contracts would make that omission fail during import,
but optional exports may also be a deliberate way to keep loops without gates
small.

## Candidate boundary

Decide whether every V5 loop module should export explicit empty or populated
`GATES` and `DERIVED` mappings. If yes, replace reflective defaults with direct
reads and add a topology assembly test. If optional exports remain deliberate,
record the exception in the audit rule without weakening reflection checks for
other contract and readiness code.

## Change Request

### CR-001 — Choose explicit exports or one narrow audit exception

Status: Parked
