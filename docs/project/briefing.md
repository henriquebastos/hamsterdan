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

## Current delivery

CV1 establishes an independently visible Hamsterdan GitHub identity and proves
the complete PR-readiness workflow through an HBNetwork-owned private GitHub App
and selected-repository installation. The qualified Petrus CV9 implementation
is behavioral evidence, not a package dependency.
