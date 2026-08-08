---
status: Decided
raised: 2026-08-08
decided: 2026-08-08
deciders:
  - Henrique (Navigator, direct authorization)
related:
  - CV16
  - CV16.DS11
---

# Empty qualification targets require atomic smart-HTTP initialization

## Decision

A future CV16.DS11 qualification repository that is empty and uninitialized
must receive its deterministic base and qualification head through one
non-forced atomic Git smart-HTTP push. The push contains exactly the base commit
at `main` and its one-child qualification commit at the declared head branch.
Git Database REST object creation is not an initialization route for an empty
repository.

Before remote authority is admitted, a local bare repository must prove the exact
two-ref command admits both refs together and a rejected push admits neither.
The credential remains outside project history in a fresh one-shot handoff. A
failed or uncertain remote push is terminal: no retry, repair, force-push,
alternate repository, or partial continuation is allowed. Exact readback must
prove both expected object identities before the one declared PR and
current/stale exact-CAS checks may run.

Clean-slate finalization superseded the first authorization for this route
before secret access or any GitHub mutation. The rehearsal passed, but no remote
push, PR, or CAS operation began. A future restart requires a new explicit
Navigator authorization and a completely fresh credential handoff. Provider
authority remains separate and cannot be inferred from setup authorization.

## Rationale

The exact disposable target was proven public, active, empty, and zero-branch.
The prior Git Database setup stopped at the closed `base_object_write` category.
A separately authorized one-call diagnostic sent the exact deterministic blob
request and retained only `validation`. GitHub's documented empty-repository
restriction explains that category without reconstructing the deliberately
discarded response or changing the historical evidence. The earlier
token-permission hypothesis is withdrawn.

Atomic smart HTTP is the smallest initialization path that preserves the
required all-or-nothing base/head shape without weakening exact object,
current-authority, CAS, or idempotency fences.

## Consequences

- The retained `validation` diagnostic remains closed and coordinate-neutral.
- Setup and provider actions require separate, one-shot authorizations.
- A restart begins from exact Hamsterdan and Petrus revisions, a clean checkout,
  a fresh deterministic fixture, a fresh credential handoff, and an exact-target
  state check; no previous setup or authority material may be reused.
- Cancellation before remote mutation erases all setup, credential-isolation,
  fixture, and unopened direct-key material.
- Exact-target deletion remains a distinct explicit mutation. Until authorized,
  its coordinate must not enter Git history or evidence.
- Exact-target deletion and not-found verification are externally deferred to
  the Puck custody workflow. Any future cleanup authorization must be newly
  granted and may permit no repository enumeration or unrelated mutation.
- No setup, provider, or cleanup authority remains after finalization.
- DS11 remains Qualified Locally and BLOCKED. This decision neither authorizes a
  provider attempt nor begins DS12.
