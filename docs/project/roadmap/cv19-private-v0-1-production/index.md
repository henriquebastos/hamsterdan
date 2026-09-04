---
code: CV19
level: Value
status: Active
status_reason: PR80 passed the clean production journey; capture-package acceptance and monitoring across all personal and HBNetwork repositories remain
updated: 2026-09-04
related:
  - ../../decisions/records/2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
  - ../../decisions/records/2026-08-25T1042Z-operator-installation-portfolios-are-restart-applied-configuration.md
  - ../../debt/items/exe-dev-default-exeuntu-image-cannot-be-pinned.md
---

# CV19 — Private v0.1 production

> **Resumed 2026-08-31:** The
> [alpha decision](../../decisions/records/2026-08-31T2056Z-the-alpha-is-the-cv19-v1-launch.md)
> made the CV19 v1 launch the first production alpha and returned CV19 to the
> delivery focus. The 2026-08-28 pause note is retained below for history: the
> last recorded systemd state was disabled and inactive, and launch still
> requires separate explicit Navigator approval.

## Intent

Review and release one private `0.1.0` V5-only Hamsterdan candidate, then run it
under the existing GitHub App boundary to monitor one explicitly selected
repository. This is production qualification, not public package publication or
open-source release.

## Current state

Production is active on revision `2f1b646906bcd8e3b13f6b969eed808f6d70e905`.
[RS-036](../../workbench/rs-036-publish-initial-summary-before-review.md) added
initial summary publication before normal Activities. PR82 proved the first
summary before review, subsequent updates to the same comment, six green jobs,
and one readiness advisory with clean History. Its release gate passed 1,267
parallel and 1,267 serial tests, with 18 declared platform deselections.
Deployment and provisioning both repeated with zero changes; production is
healthy with zero restarts and the OpenAI `gpt-5.6-sol` selection retained.

[PR80 passed the clean journey](proof/pr80.md): three findings in one native
review, App-authored repair, six green repaired-head jobs, a zero-finding
rereview and automatic thread resolution before approval, one final advisory,
and clean History. Both strict inspectors passed all ten checks. The PR was
closed unmerged after capture. The [manifest](proof/pr80-manifest.json) records
artifact hashes and explicit capture limits. CV19 remains Active for Navigator
review of those captures and monitoring across the requested repository portfolio;
production still admits one repository.

PR78 and PR79 were discarded after reply-custody and source-anchor failures.
Their reproduced corrections are included in the deployed revision. Manual
provider proofs preceded local/release gates and deployment. The PR80 gate
passed 1,256 parallel and 1,256 serial tests with 18 platform deselections.
Deployment qualification and runtime provisioning both repeated with zero
changes. A full-disk interruption was recovered by deleting three old unused
candidate artifacts; [candidate retention](../../debt/items/production-candidate-retention-can-exhaust-disk.md)
remains an obligation before another deployment. Structured runtime inspection
and unattended operations-service-account SSH are available.

### 1. Earlier inactive qualification

- Non-sharded V5 is the only runtime and all retired selector values fail
  closed.
- The local full gate passes, including source and wheel builds. GitHub-hosted
  [Actions run 32543030743](https://github.com/henriquebastos/hamsterdan/actions/runs/32543030743)
  cannot start because the account reports a payment or spending-limit block;
  local evidence does not conceal that external blocker.
- Orb setup can install the private pinned Petrus dependency using the dedicated
  project-scoped `PETRUS_GITHUB_TOKEN`; it removes temporary Git authority after
  installation. Production runtime setup does not require the optional demo
  human identities.
- One deployment-owned command now builds and verifies the same pinned
  `linux/amd64` OCI image locally or through a manual GitHub Actions adapter.
  The verified image runs the V5 host as an unprivileged user with the locked
  Python, Pi, Node, and Petrus dependencies and writable durable-state custody.
  Dirty candidates fail the release boundary. GHCR publication remains a
  separate, unqualified slice.
- The exact clean candidate from commit `7df4426` is loaded on the owned
  `hamsterdan-prod` exe.dev VM after archive SHA-256 verification. The VM is
  fenced by exact name, `hamsterdan` tag, two CPUs, 4 GiB RAM, 20 GiB disk,
  reported exeuntu image, and fingerprint-pinned SSH. Remote host CLI, package,
  Node, Pi, image identity, and writable-state checks pass; a repeated
  qualification reports `changed=0`. The accepted exeuntu base-image pinning
  limit is carried by the linked debt item.
- The first production target is `HBNetwork/demo-pr-readiness`. Private App
  registration, installation, required permissions/events, and the one admitted
  repository validate from inside the exact candidate on exe.dev.
- Private environment, App key, webhook secret, agent key, and durable state now
  have mode- and owner-checked VM custody. A systemd unit pinned to the exact
  image ID is installed, disabled, and inactive. It would bind only to loopback;
  no Hamsterdan container or application listener exists. Repeated runtime
  provisioning reports `changed=0`.
- The executable host now accepts one strict tracked configuration snapshot for
  multiple installation accounts and repositories under one App registration.
  Startup validates the complete provider portfolio before atomically replacing
  every route; removed routes immediately lose authority while existing durable
  application and webhook state remains fenced. Orb setup reads the tracked file
  directly.
- The VM operation can prevalidate and atomically publish only that tracked
  configuration with the currently installed exact image. It neither rebuilds
  nor transfers an image, changes the systemd unit, rotates secrets, nor changes
  infrastructure; it restarts only a service that was already active. The real
  operation validated the App, one installation account, and one repository on
  `hamsterdan-prod`. A changed publication and the restored tracked snapshot
  both preserved the disabled and inactive posture; the final unchanged repeat
  reported `changed=0`. Live reload remains deferred.
- Although inactive VM qualification is complete, launch can process durable
  webhook state and cause GitHub effects, so it still requires separate explicit
  Navigator approval.

## Done condition

1. The accepted restart-applied configuration admits multiple installation
   accounts and repositories, validates one complete provider portfolio, and
   atomically reconciles it before workers start.
2. The Navigator explicitly authorizes the supervised production launch and one
   bounded controlled monitoring journey.
3. Webhook ingress, current-head observation, App ownership, durable custody,
   restart posture, and absence of duplicate or unresolved effects are
   inspected for that journey.
4. Accepted history is committed and pushed, the private `v0.1.0` release/tag is
   separately authorized and created, and deployment recovery/rollback facts
   are recorded without credentials.
5. *(Added 2026-09-02 by the Navigator.)* A complete offline proof package for
   one clean hero journey exists: full-screen recordings and full-page stills at
   every checkpoint, a narrative with evidence Henrique can present from, and
   the exported durable data — History records, webhook inbox rows, agent
   session transcripts, review requests, published comments with their URLs,
   Hamsterdan-authored commits, CI run outcomes, and the exact image and petrus
   pins — sufficient to reconstruct and analyze the journey without rerunning
   it.
6. *(Added 2026-09-02 by the Navigator.)* Hamsterdan monitors all of Henrique's
   personal repositories and all HBNetwork repositories through the tracked
   configuration snapshot.

## Excluded until after private production proof

- CV18's broader simulation adapters and campaign operations.
- Remotion/video work beyond keeping the existing source and locked checks
  intact.
- Public repository visibility, package publication, Marketplace publication,
  or claims that the repository is ready for external contributors.
- Live configuration reload and support for several App registrations in one
  process.
- The detailed open-source audit, owned by the linked debt item after this
  production checkpoint.
