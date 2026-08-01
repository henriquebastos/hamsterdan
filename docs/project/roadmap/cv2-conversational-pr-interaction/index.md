---
code: CV2
level: Value
status: In Progress
status_reason: CV2.DS1 is accepted live; any subsequent conversational Delivery Story requires explicit scope
updated: 2026-08-01
---

# CV2 — Conversational PR interaction

## Intent

Let trusted pull-request participants ask Hamsterdan about readiness and request
guarded workflow changes through natural GitHub comments explicitly addressing
the installed App identity. The dashboard remains the durable source of truth;
conversation interprets and explains that state rather than replacing it.

## Scope and sequence

1. [CV2.DS1 — Mention-first readiness conversation](cv2-ds1-mention-first-readiness-conversation.md)
   establishes the exact `@hamster-dan` public interface, natural readiness
   explanations, and conversational confirmation of digest-bound mutations.
   It is accepted live on the private HBNetwork App instance.

## Done condition

Given an active pull request admitted to Hamsterdan
When an authorized human explicitly addresses the configured App mention
Then Hamsterdan can explain current readiness and stage guarded requests through
typed host intents
And every visible reply is attributed to the App bot
And no conversation bypasses durable dashboard state, exact authority fencing,
or lookup-first effect recovery.

## Out of scope

- A public slash-command interface or generalized agent tool plane.
- Petrus, AgentRunner, Motus Dispatch, or execution-environment redesign.
- Public or multi-tenant GitHub App distribution.
