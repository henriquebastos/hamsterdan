---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/candidate-review.md
---

# RS-023 — Inspect current V5 Activity identities

## Existing field to refine

The read-only `inspect-instance` operator command inventories unresolved
Activities without exposing request payloads or error text. Its current decoder
assumes that every Activity request stores its stable operation in
`input.work.operation` or `input.command.operation`.

Current V5 Activities use several work types and identity fields:

- `MutWork.op_key` for `git_gate`;
- `RoundOpen.operation` for `review_agent`;
- `Publishable.op` for `publish_gate`;
- `RerunReq.op` for `rerun_gate`;
- `RemReq.timer_id` for `reminder_gate`;
- `ReplyReq.id` for `reply_gate`;
- `DashReq.digest` for `dash_gate`; and
- `AnnounceReq.op` for `announce_gate`.

A valid unresolved V5 Activity can therefore make the documented inspection
command fail with `ValueError("Activity operation is malformed")`.

## Candidate boundary

Give inspection one bounded, sanitized decoder for the stable identity of every
current V5 Activity. Keep the output limited to occurrence, transition, Activity
name, and stable operation identity.

The refinement must:

- decode from real current V5 History rather than synthetic former `execute.*`
  records alone;
- reject unknown Activity types and malformed or colliding identities;
- preserve size, count, path, symlink, ASCII, and printable-field bounds;
- exclude request payloads, instructions, findings, patches, provider errors,
  credentials, and agent output; and
- avoid duplicating an identity grammar that can silently drift from V5 gating.

It must not mutate History, open a runtime, contact GitHub, invoke an agent, or
infer that an unresolved Activity's provider effect did or did not land.

## Change Request

### CR-001 — Decode all current V5 operation identities during inspection

Status: Parked

A future plan must choose the neutral host-owned identity decoder and define how
it shares or verifies the operation rules already used by V5 gate handlers and
agent-route settlement.

Likely files:

- `src/hamsterdan/host/__main__.py`
- a host-owned V5 Activity identity helper, if one is warranted
- `src/hamsterdan/readiness/net_v5/gating.py`, only if identity ownership can be
  shared without reversing imports
- `src/hamsterdan/host/agenticus.py`, only if existing extraction can reuse the
  same owner
- `tests/integration/host/test_service.py`
- operator documentation if output or failure wording changes

Validation seeds:

- generate real V5 JSONL History for every gate and inspect unresolved,
  completed, and failed occurrences;
- cover malformed transition/Activity pairs, duplicate occurrence identities,
  unknown work types, unsafe strings, and count/size bounds;
- prove serialized output contains no request payload or error text;
- run focused operator/host tests, `scripts/check quick`, and
  `scripts/check full`.

## Pull state

This candidate is captured but not pulled. No operator behavior, decoder,
History read, runbook, launch prerequisite, commit, or release action is
authorized by this record. ES-009 remains a learning session.
