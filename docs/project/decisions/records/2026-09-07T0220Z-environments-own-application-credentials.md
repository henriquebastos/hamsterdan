---
status: Decided
raised: 2026-09-06
decided: 2026-09-06
deciders:
  - Henrique (Navigator)
supersedes:
  - 2026-09-02T1941Z-operator-credentials-live-in-a-standing-config-store.md
related:
  - ../../workbench/rs-037-single-authority-secrets.md
---

# 1. Application Environments and separate tool vaults

Development and production use the same application configuration schema and
startup behavior. Their independent 1Password Environments hold App identity,
private-key PEM, webhook secret, and AI key. The host reads values directly.
Editing the selected Environment and restarting its consumer is the update
workflow. Retrieval failure or a missing required value prevents a new start.

The Navigator rejected shared AI, build, and operations Environments. Builds
read one Petrus token item in a separate build vault. Operations retain exe.dev
and bootstrap recovery items in the operations vault. The Navigator considered
putting the build token in operations, then chose separation because CI's vault
grant would otherwise expose the deployment SSH key.

The official CLI performs retrieval. The shared shell launcher clears inherited
credential inputs before retrieval and excludes the loader token from the child.
Production runs this loader inside its container to preserve multiline values
and avoid storing application secrets in Docker configuration metadata. The
CLI's verified Environment support currently requires a pinned beta release.

Petrus must refresh installation authority before new work after reconstruction.
Its retained encrypted connection cannot become an old-key fallback. Use its
supported custody operations and preserve workflow and operation history.

The existing development-tool vault remains the authority for optional coding
tools. It is distinct from the application Environment with the same name. No
shared runtime authority or cross-Environment synchronization is introduced.

Existing issuer credentials and identities remain intact during migration.
Private recovery copies are retained outside active loaders. Actual migration,
reader grants, expiry, dependency publication, and production cutover are tracked
in RS-037; this decision does not claim those operations have completed.
