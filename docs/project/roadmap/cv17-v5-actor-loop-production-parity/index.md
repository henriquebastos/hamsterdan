---
code: CV17
level: Value
status: Active
status_reason: DS2 is complete; DS3 durable recovery has proven publication and inline-effect convergence
updated: 2026-08-16
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
  is complete.
- [CV17.DS2 — Host composition](cv17-ds2-host-composition.md) is complete:
  provider-backed gates, durable webhook ingress, authority ordering, and
  canonical host timer custody are complete. DS2.3a adds the fail-closed
  topology descriptor, topology-owned state roots, and safe revoked-route
  V5 publication settlement; DS2.3b adds stable identified synthetic
  reconciliation and proves the selected V5 custodied webhook route. Production
  remains untouched and default.
- [CV17.DS3 — Durable recovery](cv17-ds3-durable-recovery.md) is active. Its
  first slice proves a killed durable publication worker converges to the
  exact typed blocked terminal after restart, without an automatic retry.
  Its second slice proves unresolved inline review, findings, rerun, and
  mutation Activities redispatch the exact operation, reconcile provider and
  Agenticus ledgers, and converge without duplicate effects.
- CV17.DS4 — Parity harness: ES-005 chapter-17 boundary scenarios executed
  through the real host against both topologies, compared on selected
  outcomes.

The DS4 record is scaffolded when its slice begins.

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
