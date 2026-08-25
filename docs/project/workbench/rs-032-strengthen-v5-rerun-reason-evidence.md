---
status: Candidate
captured: 2026-08-25
navigator: Henrique
source: rs-029-broaden-non-blocking-quality-evidence.md
---

# RS-032 — Strengthen V5 rerun reason evidence

## Existing field to refine

The first curated mutation probe targets the pure error-reason projection used
by `V5RerunGate`. All three generated mutants survived:

- `hamsterdan.host.v5.rerun.x__reason__mutmut_1`;
- `hamsterdan.host.v5.rerun.x__reason__mutmut_2`; and
- `hamsterdan.host.v5.rerun.x__reason__mutmut_3`.

Current rerun tests prove that failures retain the exact request and route to
`RerunFault`, but they do not distinguish every non-empty, empty, and repr-based
reason projection. The mutation profile remains informational and has no score
threshold.

## Candidate boundary

Inspect each mutant and decide which reason distinctions are part of the durable
operator-facing contract. Add direct tests only for meaningful distinctions;
classify equivalent mutants rather than adding assertions that merely mirror the
implementation.

## Change Request

### CR-001 — Classify the three rerun reason mutants

Status: Parked
