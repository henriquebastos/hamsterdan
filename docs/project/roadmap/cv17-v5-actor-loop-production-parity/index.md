---
code: CV17
level: Value
status: Active
status_reason: Decision recorded; DS1 net rewrite is the first slice
updated: 2026-08-15
---

# CV17 — V5 actor-loop production parity

## Intent

Bring the ES-007 V5 actor-loop workflow model to production parity as a
parallel implementation: real contract types, real host composition,
durable history, real dispatch, restart recovery — selectable at
composition time while production remains the untouched default. Produce
the parity evidence a future replacement ruling would require, without
making that ruling.

## Delivery

- [CV17.DS1 — The V5 net as first-class code](cv17-ds1-v5-net-first-class.md)
- CV17.DS2 — Host composition: webhook custody into ingress doors, activity
  binding to the existing dispatcher stack, one fail-closed topology switch.
- CV17.DS3 — Durable recovery: V5 on the durable history store with
  kill/restart/converge scenarios.
- CV17.DS4 — Parity harness: ES-005 chapter-17 boundary scenarios executed
  through the real host against both topologies, compared on selected
  outcomes.

DS2–DS4 records are scaffolded when their slice begins.

## Done condition

CV17 is complete when every boundary scenario in the parity harness runs
green through real host composition on both topologies, restart recovery is
demonstrated for V5, and the evidence is captured for a future replacement
decision — which stays outside this Value.

## Boundaries

- Production topology, wiring, and behavior are not modified.
- `readiness/net_v5` knows no GitHub or agent provider; the host remains the
  only composition root.
- Sharding, the courier, and Petrus promotion are out of scope.
- Live GitHub qualification stays under CV16 custody discipline.
