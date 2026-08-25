---
status: Candidate
captured: 2026-08-25
navigator: Henrique
source: rs-029-broaden-non-blocking-quality-evidence.md
---

# RS-033 — Fail fast on toolchain version drift

## Existing field to refine

Hamsterdan declares Bun 1.3.10 and pins it in hosted CI, but `scripts/check full`
starts Bun work without verifying the local version. During RS-028 and RS-029,
local Bun 1.4.0 reached the demo-video suite and one Playwright timeout closed the
shared browser, producing seven follow-on failures. The output looked like a
product regression before the version mismatch was inspected separately.

## Candidate boundary

Add a fast, side-effect-free toolchain preflight that checks required Python,
uv, and Bun versions before full or release work. Error output should name the
observed and required versions and the documented installation route. Quick
Python feedback should remain available when Bun is absent or mismatched.

## Change Request

### CR-001 — Add exact full-gate toolchain preflight

Status: Parked
