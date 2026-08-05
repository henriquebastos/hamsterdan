# Project Briefing

Hamsterdan is a GitHub-native PR-readiness application built on Petrus. It is a
separate application project, not a Petrus component and not the identity of the
Petrus runtime.

The source project lives in the private `henriquebastos/hamsterdan` repository.
An organization may operate its own App registration, installation, host
deployment, secrets, and durable state from the same code. HBNetwork is the
first sandbox organization for real-provider validation.

## Settled architecture

- Petrus supplies the one-Instance Engine, Impetus Net/History infrastructure,
  and Motus Activity/Dispatch infrastructure.
- Hamsterdan's outer host is the sole concrete composition root.
- GitHub App, agent, and PR-readiness subsystems are siblings communicating only
  through neutral typed contracts and host/Engine dispatch.
- The readiness Net owns workflow decisions. Activities perform external work.
- GitHub credentials stay host-side and never enter agent territories.
- External effects are at-least-once, operation-identified, fenced, and
  lookup-first on recovery.

## Delivered baseline

CV1 established an independently visible Hamsterdan GitHub identity and proved
the complete PR-readiness workflow through an HBNetwork-owned private GitHub App
and selected-repository installation. The accepted baseline includes App-owned
commit and comment attribution, strict bot-authorized rerun brokerage, durable
restart/redelivery behavior, and a passing private-source CI path to the pinned
Petrus repository. The qualified Petrus CV9 application remains behavioral
evidence, not a Hamsterdan package dependency.

CV16.DS11 resolves a host-owned Pi native A2 Local Agenticus profile, fences
every operation to its persisted mode/profile/snapshot, and adapts the unchanged
product protocol to the Petrus-owned probe-qualified A2 host. AgentNetRunner is
excluded because its A5 topology is not the selected A2 route. Composition,
probe, continuation workspace/session chaining, replay, conflicts, cancellation,
rollback, restart indeterminacy, and teardown are qualified without authority.
Schema-2 binds every operation to its exact PR-head archive and effective policy.
A private host receiver now rejects unsafe settled archives and replaces model
patch claims with a reproduced canonical binary patch before the existing
publication fences. `legacy-amp` is rollback only and live authority is deferred.
