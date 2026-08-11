# False host-runtime surfaces removed

Hamsterdan removed dynamic optional treatment of mandatory application terminal
settlement and unresolved-publication inspection. The service now states its
actual production invariant directly: every loaded PR application settles
frozen terminals before provider reconciliation, again after activation, and
during bounded shutdown; publication repair always inspects durable unresolved
work.

Two production-unused `AgentRouteStore` wrappers were also removed. Idempotent
`claim()` remains the single route claim/reconstruction operation, and
`settle()` remains the single terminal ownership operation.

Focused evidence passed 56 service and 18 route-custody tests. Quick and full
static/type/format/package/relay gates passed; the Python suite passed 577 tests
with one external route deselected. Independent adversarial review approved the
runtime and restart-fencing boundaries without a release blocker.
