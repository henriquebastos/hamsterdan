# V5 typed readiness topology promoted

The Navigator accepted [ES-008](../../../project/exploration/es8-typed-readiness-topology/index.md),
promoting the bounded production refactor and its design rule. Readiness now
expresses state, checks, review, findings, human review, mutation lifecycle,
and operation faults as specialized colors, places, and named folds rather
than dispatching one open `GateFact` envelope in Python.

The change exposed ordering that the former shared FIFO had supplied
implicitly. Authority now folds before incarnation-scoped evidence, mutation
pending before settlement, and recovery fault-clear before a same-drive
re-fault. Authorization and deferred wake require all readiness mailboxes to
be quiet. The dashboard deliberately retains the open envelope because it is
an event projection rather than a decision model.

Cross-version recovery remains explicit: `ready.facts` is input-only, and nine
filtered transitions migrate retained pre-promotion envelopes into the typed
topology. Both a quiescent `origin/main` history and a deliberately interrupted
history retaining a checks token loaded under the promoted net; the latter
migrated, drained, and yielded the expected successful-checks snapshot. The
[durable decision](../../../project/decisions/records/2026-08-22T0107Z-v5-durable-decisions-are-explicit-topology.md)
records the compatibility boundary and removal condition.

Focused production-loop verification passed 163 tests, the complete V5 plus
host oracle passed 484 tests, and `scripts/check full` passed 1,250 Python
tests, 53 Bun tests, static checks, and source/wheel builds. The promoted net
measures 108 places, 137 transitions, 570 arcs, 17 migration-only filters, and
38 inhibitors. No deployment or live provider operation was performed; this
milestone promotes the production source and recorded architecture.
