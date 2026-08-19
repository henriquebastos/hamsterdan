# Generated V5 reminder-timer campaign qualified locally

CV18.DS3 now has independent timer correctness evidence around the real
production V5 HostService. The modeled world derives reminder identity,
incarnation, sequence, authority, deadline, maturity, and status from admitted
external events, logical time, and provider acceptance. The checker compares
that schedule with detached durable V5 timer custody; it does not inspect a
Petri marking or retain a runtime handle. Deliberate wrong-head and early-
maturity mutations prove the checker rejects contradictory custody.

The generated campaign combines stable authority, new-head replacement,
draft→active resumption, and closure with crashes before maturity, after
maturity, and after reminder acceptance. Old webhook redelivery and accepted-
but-response-lost reminder publication are varied before bounded fair
convergence. Four explicit semantic anchors plus five deterministic generated
schedules cover every selected authority path and crash class; every successful
expanded schedule replays exactly through Petrus artifact v4.

The focused model, World, and campaign regressions passed. Hypothesis's five
generated schedules passed with no invalid or failing cases; the explicit
anchors retain the closed path and complete selected crash matrix. The full
project check passed 1,243 Python tests, 44 media tests, nine webhook relay
tests, lint/format/type checks, and source/wheel builds. Slice-boundary Oracle
review found no timer-oracle soundness blocker for this bounded schedule.

CV18.DS3 remains Active. This result does not cover repeated or overlapping time
advances while reminder work is deliberately pending, retry schedules, the
remaining DS1 fault adapters, broad semantic coverage reporting, or DS4
operational campaign retention.
