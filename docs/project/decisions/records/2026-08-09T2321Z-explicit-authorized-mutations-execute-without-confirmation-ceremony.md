---
status: Decided
raised: 2026-08-09
decided: 2026-08-09
deciders:
  - Henrique (Navigator)
related:
  - RS-001
  - CR-005
---

# Explicit authorized mutations execute without confirmation ceremony

## Decision

An authorized human's explicit, unambiguous mutation instruction in a PR
conversation authorizes immediate execution. An ambiguous or incomplete
instruction produces a clarification reply and no mutation.

The host still accepts only a declared typed intent and fences every mutation
against the current PR generation, base, policy, and operation identity. Agent
output is not authority, an unauthorized actor cannot mutate, and Hamsterdan
never merges.

This supersedes the product rule introduced by the conversational-change
delivery slices that required a second comment containing a digest-bound
confirmation. Those roadmap and worklog records remain accurate historical
evidence; they no longer describe current behavior.

## Rationale

The second comment duplicated a clear human decision without strengthening the
host's real safety boundaries. It added pending-intent state, confirmation
parsing, and extra Net transitions, making both the conversation and workflow
harder to understand. Clarification is the appropriate response when intent is
not clear; current-authority fencing is the appropriate defense when it is.

## Consequences

- Conversation classification must choose exactly one declared intent.
- Mutation intents require an explicit request with concrete scope.
- Ambiguous mutation language must resolve to a non-mutating clarification.
- No pending mutation, confirmation digest, or confirmation transition is
  retained in durable workflow state.
- Existing History and old confirmation token schemas are not migrated during
  this pre-use design phase.
