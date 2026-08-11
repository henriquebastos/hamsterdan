# Publication concern ownership separated

Hamsterdan replaced the 23-field aggregate `PublicationState` with independent
finding, conversation, dashboard, and readiness publication tokens. Each
authorization and result transition now consumes only its concrete owner.
Operation absence is explicit `None`; retained recovery uses exact Pydantic
request values and remains outside the relational `ReadinessSnapshot`.

The Net changed from 43 places, 67 transitions, 266 arcs, and 17 retirements to
46 places, 69 transitions, 309 arcs, and 17 retirements. Added topology exposes
independent ownership and three typed recovery branches; no execution or
lifecycle state machine returned.

Structural tests fix the exact transition dependencies. Integration evidence
forces capability failure and restart for conversation, dashboard, and
readiness, then proves exact typed reconstruction, one fresh occurrence with
stable provider identity and payload, selected-owner recovery, successful
clearing, and stale-recovery retirement. Independent adversarial review
approved the result with no blocker. No Petrus, HA, database, or actor-runtime
change was needed.
