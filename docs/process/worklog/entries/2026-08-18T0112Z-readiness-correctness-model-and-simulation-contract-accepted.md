# Readiness correctness model and simulation contract accepted

The Navigator accepted CV18.DS1's independent expected-readiness model and the
contract for the later debugger-like deterministic World/Timeline. The model
derives authority, CI, review, collaboration, change, effect, timer, and
lifecycle outcomes from strict normalized external facts without importing the
host, either readiness topology, Petrus runtime state, or production folds.
Production and V5's existing clean-green real-host paths independently normalize
to the same expected `ready` result; production remains the default.

The contract fixes one Petrus interpreter for authored Timeline stories,
generated commands, and strict replay; separate provider truth mutation,
webhook emission, and delivery; deterministic IDs/time/order; bounded run-until
checkpoints; named event, fault, ambiguity, and crash cuts; fair-environment
liveness; explicit bounds/dispositions; strict replay identities; and semantic
coverage dimensions. DS2 owns the executable Hamsterdan World, boundary-faithful
provider adapters, true HostService generation drop/reload, and the first
vertical replay. DS3 owns generated schedules and shrinking.

Petrus commit `1936ae8b78e6840fba043e06e5d886cdd27ccd4d` is pinned for the
supported `petrus.testing.dst/v1` surface and `petrus-dst-world` v1 artifact.
The documented v1 inability to retain a failed attempted operation blocks DS3
failure shrinking/replay, not DS2's successful vertical artifact; Hamsterdan
will not create a second runner.

Slice-boundary review rejected the model's first boolean authorization verdict.
The accepted model instead requires an independently admitted human grant bound
to its exact delivery identity, operation, intent digest, full current active
authority, mutation head, and coding/Git effect reference. Follow-up review
returned `clear to commit`.

Focused model/parity verification passed 29 tests. `scripts/check full` passed
1,210 Python tests, 44 media tests, nine webhook-relay tests, static checks, and
source/wheel builds. No production behavior, CV17 evidence, topology default,
Petrus repository, or sharded V5 changed.

Historical scope note: those topology and Petrus-version statements describe
DS1 at acceptance. The Navigator later selected non-sharded V5 as production,
and CV18 now pins the supported Petrus v4 test kit; the superseding decision and
current CV18 roadmap own present behavior.
