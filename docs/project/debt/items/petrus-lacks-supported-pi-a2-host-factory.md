# Petrus Pi A2 host factory was previously unavailable

**Status:** Resolved by Petrus `aa5a9152f0c9b36358c0a3019716f47511f64802`

**Raised:** 2026-08-05

**Related:** CV16.DS11

Hamsterdan now consumes the supported production factory that assembles the
authority-capable A2 topology without copying Petrus machinery.

The delivered Petrus surface is public `PiA2RuntimeHostConfig`, a
credential-free `PiA2RuntimeStart` value, an owned `PiA2RuntimeHost` exposing
`probe()`, `start(request) -> RuntimeOperation`, and `close()`, and a
`compose_pi_a2_runtime(...) -> PiA2RuntimeHost` factory. Petrus must own
`PiConnectionCustody`, Motus binding and territory, `EpisodeAttachment`, Hands
gateway, continuation and turn-operation stores/codecs, partial-construction
rollback, and verified teardown. The host supplies bounded configuration, a
private state root, and a narrow direct API-key authority callback; probe must
not invoke that callback, and start may materialize it only once.

Petrus and receiving-host tests cover exact A2 descriptors/topology, authority-free probe,
single start-time authority materialization, restart/continuation recovery,
cancellation, cleanup verification, partial-construction teardown, exact-once
collaborator closure, lookup-first recovery after close-before-History restart,
and refusal to substitute AgentNet/A5. Hamsterdan must not
run a live gate before the remaining receiving-host changed-work policy is
deterministically qualified.
