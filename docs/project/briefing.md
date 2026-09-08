# Project Briefing

Hamsterdan is a GitHub-native PR-readiness application built on Petrus. It is a
separate application project, not a Petrus component or runtime identity.
The plain-language identity page is
[What Hamsterdan is](../product/what-hamsterdan-is.md); the canonical domain
language is the [project glossary](glossary/index.md). This briefing predates
both and still uses retired vocabulary.

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

[CV19](roadmap/cv19-private-v0-1-production/index.md) owns the current delivery
movement: the private `v0.1.0` launch of the current V5 runtime is the first
production alpha. The supervised host is active on the owned `hamsterdan-prod`
exe.dev VM, and Gate B and the `v0.1.0` tag are complete. CV19 remains active
for capture-package acceptance and repository-monitoring scope. PR83 passed the
full hero journey with initial summary first and was closed unmerged after
capture. Its roadmap and linked
worklog own current revisions, media limits, and discarded proof runs.

[CV21](roadmap/cv21-composable-outer-hamsterdan/index.md) continues as the
quality track without gating that alpha. Its non-selectable outer-system
reconstruction uses one temporary bridge to the current working Net. CV21.DS1
provides the isolated replacement gate and locally qualified host/readiness/
bridge lifecycle under `src/hamsterdan2`; CV21.DS2's glossary-aligned
replacement is accepted and complete. Signed raw webhook evidence enters one
shared Webhook Inbox, a later host worker authorizes only novel semantic
observations, and Petrus History alone owns acceptance and completion. DS3 is
not pulled. The replacement uses only fresh disposable state and has no runtime
selector or deployment.

[CV22](roadmap/cv22-decomposable-readiness-workflow/index.md) then replaces that
bridge with recursively independent production subnets and owns final cutover.
The former integrated
[CV20](roadmap/cv20-composable-reconstructible-hamsterdan/index.md) plan was
dropped before implementation and remains design history. Neither successor is
a runtime choice; V5 remains the sole runtime until a separately approved CV22
cutover.

The pinned Petrus source dependency is currently private. Dependency installation
reads the token through the separate build vault, removes temporary Git authority
on every outcome, and keeps that token out of host runtime state. Remote Amp
settings still need migration; RS-037 owns that unfinished operation.
Optional demo author/reviewer identities do not gate production setup.

GitHub-hosted CI and image qualification passed for release `85c109e`, which is
deployed on production through the new application Environment. RS-037 owns
the cutover evidence and fresh comparison with PR83.

The pinned Petrus dependency must become publicly accessible before anonymous
installation and public CI can be qualified. Public Actions remain disabled.
