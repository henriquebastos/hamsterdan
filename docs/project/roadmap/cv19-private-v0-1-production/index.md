---
code: CV19
level: Value
status: Paused
status_reason: Navigator paused private production before launch to focus delivery on CV21; the qualified inactive candidate and remaining launch proof are retained
updated: 2026-08-28
related:
  - ../../decisions/records/2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
  - ../../decisions/records/2026-08-25T1042Z-operator-installation-portfolios-are-restart-applied-configuration.md
  - ../../debt/items/exe-dev-default-exeuntu-image-cannot-be-pinned.md
---

# CV19 — Private v0.1 production

> **Paused 2026-08-28:** The Navigator stopped this delivery work before
> production launch to focus on CV21. This is a roadmap pause, not a live
> runtime operation; the last recorded systemd posture was disabled and
> inactive. The qualified candidate and remaining launch, monitoring, and
> private-release work remain resumable.

## Intent

Review and release one private `0.1.0` V5-only Hamsterdan candidate, then run it
under the existing GitHub App boundary to monitor one explicitly selected
repository. This is production qualification, not public package publication or
open-source release.

## Current state

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
