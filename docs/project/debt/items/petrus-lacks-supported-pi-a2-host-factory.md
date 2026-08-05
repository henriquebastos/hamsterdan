# Petrus lacks a supported authority-capable Pi A2 host factory

**Status:** Accepted external dependency

**Raised:** 2026-08-05

**Related:** CV16.DS11

Hamsterdan can deterministically resolve and probe `PI_NATIVE_A2_LOCAL`, and its
unchanged product protocol now adapts to narrow injected Pi operation lifecycle
collaborators. Petrus does not yet expose a supported production factory that
assembles the authority-capable A2 topology without making the consumer copy
test-only wiring.

The smallest required Petrus surface is a public `PiA2RuntimeHostConfig`, a
credential-free `PiA2RuntimeStart` value, an owned `PiA2RuntimeHost` exposing
`probe()`, `start(request) -> RuntimeOperation`, and `close()`, and a
`compose_pi_a2_runtime(...) -> PiA2RuntimeHost` factory. Petrus must own
`PiConnectionCustody`, Motus binding and territory, `EpisodeAttachment`, Hands
gateway, continuation and turn-operation stores/codecs, partial-construction
rollback, and verified teardown. The host supplies bounded configuration, a
private state root, and a narrow direct API-key authority callback; probe must
not invoke that callback, and start may materialize it only once.

Petrus tests must cover exact A2 descriptors/topology, authority-free probe,
single start-time authority materialization, restart/continuation recovery,
cancellation, cleanup verification, partial-construction teardown, exact-once
collaborator closure, lookup-first recovery after close-before-History restart,
and refusal to substitute AgentNet/A5. Hamsterdan must not
run a live gate or reproduce this machinery locally before that surface is
available and deterministically qualified.
