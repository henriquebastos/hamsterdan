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
- The readiness Net owns workflow decisions through one centralized `Authority`
  token and independent Actions, review, human, mutation, finding-publication,
  conversation-publication, dashboard-publication, and readiness-publication
  concern tokens. `ReadinessSnapshot` is a relational projection, never a place
  color or mutable aggregate; internal recovery requests are not projected.
- Activities perform external work through exact strict Pydantic request/result
  contracts. Conversation, dashboard, and readiness publication use one
  immutable logical Motus execution with classified bounded retry in shared
  durable Worker custody; the Net retains authorization, exact operation
  ownership, and current terminal acceptance.
- Each PR retains an independent Engine and History. The host resolves scoped
  Activity implementations for one shared Worker, serializes advancement per
  PR, and stores only reconstructible scheduling hints outside canonical
  webhook, History, and Dispatch custody.
- Webhook delivery, runnable timers, Activity terminals, and repair sweeps enter
  one per-Instance host activation boundary. It settles frozen terminals before
  provider observation, records final runnable posture, and only then
  acknowledges webhook custody. Subject-filtered custody and strict-bound
  inactive repair prevent deferred work or lost hints from bypassing recovery.
  Settlement and unresolved-publication inspection are mandatory application
  operations rather than optional compatibility capabilities.
- `PrReadinessApplication.activate(...) -> None` is the sole application
  reconciliation command. Canonical state is the typed Engine marking and
  `ReadinessSnapshot`; the application exposes no parallel dictionary
  projection or compatibility reconciliation path.
- GitHub comment admission is provider-owned and fail-closed. Durable custody
  retains the authenticated raw observation; `github_app` emits a strict
  `AdmittedConversation` with mention-stripped text, and the application only
  binds current workflow authority and delivers it.
- GitHub Actions assessment is provider-owned. Exact-run selection remains an
  explicit read; one typed `ActionsEvidence` operation attaches required jobs,
  normalizes queued/in-progress state, and identifies failed required jobs.
  Reconciliation and Activities add their own workflow identity and authority
  context without duplicating provider interpretation.
- GitHub App registration evidence is provider-owned. One validated immutable
  `RegistrationInventory` crosses into the host; only then does the host
  atomically replace admitted routes and record the selected installation.
- Agent execution identity is explicit. Activities pass one logical operation
  and Attempt to a host-owned routed runner, which claims durable composition
  ownership before provider execution. Pi alone derives its stable per-Attempt
  runtime identity; no ambient execution-selection scope or two-call handshake
  remains.
- Each active PR generation has one exact Petrus lifecycle scope. Unscoped
  lifecycle commands survive generation cleanup; a staged command, exact scope
  reset/close, and matching commit form a restart-repairable boundary. Scope
  cancellation replaces stale-generation cleanup topology while the Net keeps
  same-generation operation ownership and current-authority decisions.
- Terminal publication capability failure can be retried only by an explicit
  authorized recovery intent naming the exact blocked operation. It creates one
  fresh Activity occurrence with the stable provider-effect identity. Unknown
  terminal publication failures become nonrecoverable workflow faults rather
  than automatic retries or projection wedges. Each publication channel owns
  its exact optional operation and typed retained recovery request independently.
- Explicit authorized mutation instructions execute directly. Ambiguous
  instructions clarify without mutation; there is no confirmation ceremony.
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
publication fences. Production now requires explicit absolute Pi installation
paths and lazily transfers a direct key from an owned `0600` file through the
one-shot supplier. `legacy-amp` remains rollback only. The first
authority-bearing live attempt proved one-shot direct-key custody and
fail-closed rejection but did not publish: the real host publisher rejected the
controlled coding candidate at its Git publication boundary. Live support
therefore remains unaccepted and no fallback profile is permitted. A subsequent
credential-free diagnostic proved the complete canonical-patch publication and
replay path against a bounded local authority, but also proved that the live
harness overwrote the original rejected fence with a secondary empty-replay
error. The original cause is therefore unclassified rather than inferred. A
closed publication-category contract now retains the first cause before replay,
suppresses publication assertions after zero publication, and keeps replay and
cleanup failures separate. A separately authorized second attempt completed one
production runtime operation with one accepted output append and six Hands
calls, but no changed coding result crossed admission. It therefore produced no
mutation candidate, publisher call, publication, or replay. The retained safe
category is `agent_result_unaccepted`; the exact subcause is deliberately not
inferred from erased provider output. Direct-key, DS2, runtime, workspace, and
remote qualification cleanup all passed. DS11 remains Qualified Locally, and
closed future agent-result evidence now distinguishes runtime lifecycle, output
schema, correlation, unchanged, unable, and workspace reconciliation outcomes
without retaining prose or coordinates. Cleanup uncertainty remains separate;
categorized outcomes cannot retry or publish, while accepted changed results
retain the existing canonical publication path. This does not reclassify the
historical attempt. The code may request a fresh separately bounded provider
attempt, but none is authorized by this qualification and DS12 remains excluded.

A later clean-slate qualification cycle prepared one new public empty disposable
target but never reached provider authority. Its first setup stopped at the
closed `base_object_write` boundary; a one-call exact blob diagnostic retained
only `validation`. GitHub's documented empty-repository Git Database restriction
explains that result without recovering discarded diagnostics, and the earlier
token-permission hypothesis is withdrawn. A corrected atomic smart-HTTP
two-ref setup passed credential-free local rehearsal, then was cancelled before
secret access or remote mutation. All setup and unopened direct-key material was
retired. Exact-target deletion and not-found verification are externally
deferred to the Puck custody workflow. No setup, provider, or cleanup authority
survives clean-slate finalization.

A fresh separately authorized setup restart passed the full deterministic gate,
fresh credential and exact empty-target admission, and local atomic two-ref
rehearsal. Its final current-state read timed out before the push-spent fence, so
no push, ref, PR, CAS, direct-key, provider, publication, or retry began. A
transient qualification traceback rendered the private target coordinate,
violating the coordinate-free evidence contract without causing remote mutation.
All local authority and target material was erased after fresh RSA-OAEP transfer
to durable Puck cleanup custody. The exact-target deletion obligation remains
open and no cleanup or provider authority survives.

The resulting credential-free hardening slice now provides one reusable setup
boundary for private target observations and the exact atomic two-ref push.
Observation, fence, runner, timeout, and arbitrary ordinary exceptions collapse
to closed coordinate-free evidence. The push admits only one canonical GitHub
remote and two exact lowercase object IDs, durably spends a mode-`0600` marker
through a held mode-`0700` directory descriptor before execution, and refuses
every subsequent call. File/directory sync, symlink, restrictive-umask, short
write, parent-substitution, noncanonical URL, hostile string-subclass, and
diagnostic canaries are qualified deterministically. This enables a future newly
authorized setup attempt; it does not authorize one or establish live support.

That boundary is now composed as the production `qualification-setup` operator
command. It consumes private credential and target files, excludes ambient
authority, verifies exact authenticated identity and target state, creates the
deterministic fixture, performs at most one durably spent atomic push, and gates
read-only PR/CAS observations on complete exact readback. Managed private and
configuration material is removed with cleanup uncertainty retained separately.
Credential-free local integration passes; no live setup or provider authority
was used, so DS11 remains Qualified Locally and live support remains unaccepted.
