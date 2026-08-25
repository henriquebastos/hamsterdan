# Project Briefing

Hamsterdan is a GitHub-native PR-readiness application built on Petrus. It is a
separate application project, not a Petrus component or runtime identity.

The source project lives in the private `henriquebastos/hamsterdan` repository.
HBNetwork owns the first private GitHub App used for real-provider validation.
An operator may run the code with one App registration, host deployment,
secrets, and durable state. The accepted first-release direction admits a
configured portfolio of installation accounts and repositories without SaaS
accounts or an administration UI. The executable host and operator tooling now
implement that restart-applied portfolio, and the owned inactive exe.dev
runtime has qualified the same tracked configuration-only operation.

## Settled architecture

- Non-sharded V5 is the only runtime topology. `HostService` constructs it
  directly. The former production composition, topology selector, and sharded
  prototype are unavailable.
- The durable topology identity remains `v5`. Explicit V5 roots may resume;
  former-production and unlabeled roots fail closed without mutation. Resumable
  V5 histories retain only the V5-internal input migration lane.
- Petrus supplies the one-instance Engine, Impetus Net/History, and Motus
  Activity/Dispatch infrastructure. Hamsterdan imports concepts from their
  defining modules.
- `host` is the sole concrete composition root. `github_app`, `agents`, and
  `readiness` are siblings and share only neutral contracts.
- Each PR has an independent Engine and History. V5 cohabits nine concern loops
  plus lifecycle control in that instance; typed mailboxes and specialized
  readiness facts express durable decisions explicitly.
- GitHub and agent effects execute as strict typed Motus Activities. Durable
  conversation, dashboard, and readiness publications share one Worker custody
  boundary and one centralized durable-publication allowlist.
- Webhook custody, Dispatch, timers, runnable hints, and canonical History are
  reconstructible. Startup and periodic reconciliation converge frozen or
  ambiguous operations lookup-first without claiming exactly-once effects.
- Current installation/repository/PR/head/base/policy/lifecycle authority fences
  every external effect immediately before execution. Operation identity and
  content digests survive retries and restarts.
- GitHub credentials and installation tokens stay host-side. Agent territories
  receive bounded credential-free snapshots and never repository authority.
- Explicit authorized mutation instructions execute directly; ambiguous
  instructions clarify without mutation. Hamsterdan never merges.

## Accepted evidence

CV1–CV4 established the private App identity, durable webhook host,
conversation, guarded changes, scenario portfolio, and complete three-actor
hero. CV16 established the sole Pi native A2 agent route. CV17 then proved V5
across eleven semantic journeys and fresh real-GitHub clean-green,
transient-CI, and complete repair journeys. PR61 exercised changed coding,
App-authored Git object publication, exact ref CAS, operation-scoped
lookup-first recovery, repaired-head admission, approval, and readiness.

CV18 accepted an independent readiness model, deterministic real-host World,
generated authority/lifecycle, reminder-timer and Git-ambiguity campaigns,
checker-sensitivity/resource counterexamples, exact replay, and strict semantic
coverage accounting. Broader adapters and campaign operations are paused until
after private production qualification.

## Current movement

[CV19](roadmap/cv19-private-v0-1-production/index.md) owns the private `0.1.0`
production checkpoint. The V5-only candidate is locally green and its exact
archive and image identity qualify idempotently on the owned `hamsterdan-prod`
exe.dev VM. Private runtime custody validates the HBNetwork App installation and
`HBNetwork/demo-pr-readiness` from the exact image. The exact-image systemd unit
is installed but disabled and inactive; no container or application listener
exists. Restart-applied configuration for multiple installation accounts and
repositories is accepted locally: the host validates one complete tracked
snapshot, atomically reconciles all routes before workers start, and the VM
operation applies only that file without an image deployment. Clean commit
`7df4426` and its exact image now qualify idempotently on `hamsterdan-prod`;
changed and unchanged configuration-only applications both preserved the
disabled and inactive service posture. The next movement is an explicitly
approved supervised launch and one bounded monitoring proof. Launch still
requires explicit approval because durable webhook state can cause GitHub
effects.

The pinned Petrus source dependency is currently private. Orb installation uses
a dedicated project-scoped `PETRUS_GITHUB_TOKEN`, removes temporary Git
authority on every outcome, and does not put that token in host runtime state.
Optional demo author/reviewer identities do not gate production setup.

GitHub-hosted Actions currently fails before job start because of the account's
payment/spending state. Local full-gate evidence remains valid but does not
replace hosted CI.

After CV19's production proof, a dedicated debt item owns the repository-wide
open-source audit, community/security documents, dependency-publication
contract, historical experiment disposition, and decision to retain or remove
the secondary Remotion studio. No repository visibility or public publication
change is authorized.
