---
code: CV19
level: Value
status: Active
status_reason: The exact V5-only OCI candidate now qualifies idempotently on the owned exe.dev VM without launch; registry publication, service configuration, exact target selection, approved launch, and one controlled monitoring proof remain
updated: 2026-08-25
related:
  - ../../decisions/records/2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
  - ../../debt/items/exe-dev-default-exeuntu-image-cannot-be-pinned.md
---

# CV19 — Private v0.1 production

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
- The exact clean candidate from commit `b97c7a9` is loaded on the owned
  `hamsterdan-prod` exe.dev VM after archive SHA-256 verification. The VM is
  fenced by exact name, `hamsterdan` tag, two CPUs, 4 GiB RAM, 20 GiB disk,
  reported exeuntu image, and fingerprint-pinned SSH. Remote host CLI, package,
  Node, Pi, image identity, and writable-state checks pass; a repeated
  qualification reports `changed=0`. The accepted exeuntu base-image pinning
  limit is carried by the linked debt item.
- The existing private GitHub App is HBNetwork-owned and can be installed only
  for repositories owned by HBNetwork. The production target repository has not
  yet been named.
- The OCI candidate has been exercised on exe.dev only through no-effects
  qualification commands. No service, application port, GitHub credential, or
  host process was configured. Launch can process durable webhook state and
  cause GitHub effects, so it requires a separate explicit Navigator approval
  after target selection and validation.

## Done condition

1. The Navigator reviews and accepts the V5-only candidate and names the exact
   `OWNER/REPOSITORY` to monitor.
2. The App registration and selected-repository installation match that target,
   and `scripts/hamsterdan-host validate` passes without starting the host.
3. The Navigator explicitly authorizes the supervised production launch and one
   bounded controlled monitoring journey.
4. Webhook ingress, current-head observation, App ownership, durable custody,
   restart posture, and absence of duplicate or unresolved effects are
   inspected for that journey.
5. Accepted history is committed and pushed, the private `v0.1.0` release/tag is
   separately authorized and created, and deployment recovery/rollback facts
   are recorded without credentials.

## Excluded until after private production proof

- CV18's broader simulation adapters and campaign operations.
- Remotion/video work beyond keeping the existing source and locked checks
  intact.
- Public repository visibility, package publication, Marketplace publication,
  or claims that the repository is ready for external contributors.
- The detailed open-source audit, owned by the linked debt item after this
  production checkpoint.
