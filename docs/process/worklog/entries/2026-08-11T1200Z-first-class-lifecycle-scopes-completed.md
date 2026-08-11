# First-class lifecycle scopes completed

Hamsterdan pinned Petrus
`b0bb336a077b70b6d702aef26acbf8ad1381f9b3` and replaced stale-generation Petri
retirement topology with exact `readiness-generation` lifecycle scopes. The Net
moved from 40 places, 138 transitions, 412 arcs, and 91 retirements to 43 places,
67 transitions, 266 arcs, and 17 retirements. Retained retirements decide
same-generation operation ownership, admission, and invalid basis/recovery.

Generation start and stop now use a crash-safe staged command, exact Petrus
reset/close, and matching commit protocol. Reconciliation repairs interrupted
boundaries before processing provider state, including crashes between initial
Engine creation and scope open and seed-only termination before admission.
Scope-cancelled Activity occurrences settle host publisher and unresolved-work
indexes; exact late terminals remain fenced by Petrus quarantine semantics.

Terminal publication capability failure retains an immutable request and can
be retried only by an explicit authorized recovery naming the exact target and
blocked operation. One recovery creates one fresh Activity occurrence while
preserving stable provider-effect identity for lookup-first reconciliation.
Unknown terminal failures project nonrecoverable publication faults instead of
wedging lifecycle close or becoming implicit retries.

The final gate passed Ruff, formatting, ty, JavaScript tests, source and wheel
builds, nine relay tests, and 524 Python tests with one explicit external-provider route skipped.
Adversarial review approved the result after all identified lifecycle crash
windows were closed. No live GitHub or agent-provider effect was required.
