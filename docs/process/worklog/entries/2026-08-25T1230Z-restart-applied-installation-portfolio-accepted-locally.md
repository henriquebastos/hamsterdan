# Restart-applied installation portfolio accepted locally

One operator-controlled Hamsterdan instance now admits a strict tracked
configuration snapshot containing multiple GitHub installation accounts and
repositories under one App registration. The host validates the App and every
configured provider portfolio before atomically replacing all installation and
repository routes. Removed routes lose current authority while durable webhook
and application state remains available for fenced recovery.

`deployment/config/installations.toml` is the shared source of truth. Orb setup
reads it directly. The exe.dev runtime operation can validate that complete file
with the currently installed exact image and isolated temporary state, then
atomically publish only the configuration. It does not rebuild or transfer an
image, change the systemd unit, rotate secrets, or alter VM infrastructure. An
active service restarts after a changed publication; an inactive service remains
inactive. Validation failure preserves the old file. Restart failure after
publication retains the validated new file and leaves the service failed closed.

The multiple-account configuration, provider inventory, cross-account lifecycle
fencing, atomic reconciliation, restart-applied route removal, VM operation,
orb direct-read path, and secret-safe failures are covered by focused tests.
`scripts/check full` passed Ruff, formatting, typing, nine relay tests, 44 media
tests, source and wheel builds, and 1,150 Python tests. Both Ansible playbooks
passed syntax checks. A dirty, unpublishable OCI development candidate built and
verified, then its read-only `validate` command confirmed the real HBNetwork App
and one admitted `demo-pr-readiness` repository without launching the service,
invoking an agent, or writing to GitHub. The orb launcher produced the same
evidence. A discovered release-adapter defect also received a failing-first
regression: repository-relative `--manifest` paths now verify and report
successfully.

No exe.dev state changed during this slice. `hamsterdan-prod` remains disabled
and inactive on the earlier exact image. The next movement is an authorized
local commit, followed by a clean exact-candidate build, inactive exe.dev
qualification and provisioning, and a real configuration-only idempotence
exercise. Production launch and any GitHub App visibility or second-installation
change still require separate approval.
