# Hamsterdan deployment

This directory owns the deployment axis. It builds one `linux/amd64` OCI image,
qualifies that exact image on the owned exe.dev VM, and provisions private
runtime custody for no-launch App validation. No deployment command starts the
Hamsterdan service.

## Release contract

- `deployment/Containerfile` is the image definition.
- `deployment/release.py` is the canonical build and verification interface.
- `deployment/pi/package-lock.json` is the shared Pi dependency graph used by
  both the image and the Amp orb setup.
- `deployment/exe_vm.py` selects or explicitly creates the exact-name,
  `hamsterdan`-tagged exe.dev VM.
- `deployment/deploy.py` exports a verified clean candidate and drives
  `deployment/ansible/candidate.yml` over fingerprint-pinned SSH.
- `deployment/runtime.py` transfers temporary private runtime inputs and drives
  initial provisioning or configuration-only application against the owned VM.
- `deployment/config/installations.toml` is the tracked authority allow-list of
  GitHub installation accounts and repositories. It is runtime configuration,
  not an image input.
- `.github/workflows/image.yml` is a manual CI adapter over the same commands.
  CI does not contain a second build implementation.

The build uses a BuildKit secret named `petrus_github_token` to install the
private, commit-pinned Petrus dependency. The secret is not a build argument or
an image layer.

## Build locally or in a Docker-enabled Amp orb

Prerequisites are Python 3.11 or newer, Docker with Buildx, and
`PETRUS_GITHUB_TOKEN` in the environment. In an Amp orb, run Docker as a
supervised orb service rather than a background shell process.

A release candidate must come from a clean commit:

```shell
python deployment/release.py build
python deployment/release.py verify
```

During development, an explicit local-only build may include uncommitted files:

```shell
python deployment/release.py build --development
python deployment/release.py verify
```

The build prints the generated manifest path under `dist/deployment/`. The
manifest binds the candidate to its source revision, pinned input hashes, image
digest, and loaded image ID. Verification checks that exact loaded image, its
OCI revision and version labels, the host CLI, the Hamsterdan package version,
the qualified Pi and Node runtimes, and writable durable-state ownership. A
dirty candidate is permanently marked as unpublishable.

Pass `--manifest PATH` to verify a candidate other than the one inferred from
the current checkout.

## Qualify a candidate on exe.dev

Install the locked development tools with `uv sync --frozen`. Every deployment
command runs through `scripts/ops`, which resolves the committed `env-ops.tpl`
with `op run` for that one command and never writes a rendered file:

```shell
scripts/ops uv run --frozen python deployment/exe_vm.py ...
```

The template resolves only from the `hamsterdan-ops` vault, which holds the
deployment authority the running service must never be able to read: the exe.dev
API token, the exe.dev SSH key as one base64 line, the App identity, the agent
key, and the target's own service-account token. Neither `hamsterdan-dev` nor
`hamsterdan-prod` carries any of it, so a stolen sandbox token cannot reach the
production host and the production host cannot reprovision itself.

Authority comes from one of two places and nothing else. A workstation exports
no service account, so `op run` authenticates personally and every deployment
from a laptop costs a deliberate Touch ID confirmation. A headless environment
exports `OP_SA_HAMSTERDAN_OPS`, and `scripts/ops` substitutes it for the
duration of the command. That single variable is the only difference between the
two, so the command a human types is the command automation runs.

Register the exe.dev public key and scope it to the VM ownership tag:

```shell
cat /path/to/key.pub | ssh exe.dev ssh-key add --tag=hamsterdan
```

To replace the stored key, encode it as one line before writing the item, and do
not print or persist that output:

```shell
op read 'op://example-ops/example-ssh-key/credential' | base64 -d   # recover
```

The owned VM contract is `hamsterdan-prod`, tag `hamsterdan`, two CPUs, 4 GiB
RAM, 20 GiB disk, and exe.dev's default exeuntu image. Creation requires the
exact confirmation value and has no automatic deletion counterpart:

```shell
scripts/ops uv run --frozen python deployment/exe_vm.py ensure --confirm-create hamsterdan-prod
```

Deploy an already verified clean candidate by its manifest:

```shell
scripts/ops uv run --frozen python deployment/deploy.py \
  --manifest dist/deployment/<revision>/release.json
```

The deployment checks the local image ID, exports a gzip-compressed Docker
archive, verifies its SHA-256 after transfer, and loads it without rebuilding.
The playbook then checks the loaded image ID, host CLI, Hamsterdan package
version, Node and Pi commands, and writable state ownership. A second run must
report `changed=0`. SSH host keys are accepted only when they match exe.dev's
[published fingerprint](https://exe.dev/docs/faq/host-key).

This qualification creates no systemd unit, opens no application port, sends no
GitHub credential, and does not start the Hamsterdan host.

## Provision and validate an inactive runtime

Runtime provisioning consumes the installation and repository inputs from
`deployment/config/installations.toml` plus everything `env-ops.tpl` resolves,
including `OP_SERVICE_ACCOUNT_TOKEN_VPS`: the target's own 1Password
service-account token, persisted on the VM as owner-only
`/etc/hamsterdan/op-token`.

The App private key, the webhook secret, and the runtime environment are no
longer produced by the deploy. Provisioning installs a pinned, checksum-verified
`op` CLI, the target token, and the committed `env-prod.tpl` at
`/etc/hamsterdan/env-prod.tpl`. The systemd unit's `ExecStartPre` steps then run
as root before every `docker run`: they read the token from its file, render
`/etc/hamsterdan/hamsterdan.env` with `op inject`, fetch `github-app.pem`, and
write the webhook secret, all from the `hamsterdan-prod` vault. That is the
rotation contract — change the item in 1Password, run
`systemctl restart hamsterdan`, and the new credentials are live. The token
never appears in a command argument.

`GITHUB_APP_PRIVATE_KEY_PEM`, `GITHUB_APP_WEBHOOK_SECRET`,
`GITHUB_APP_CLIENT_ID`, `READINESS_WORKFLOW_PATH`, and
`READINESS_REMINDER_SECONDS` are therefore no longer read by this command; the
last four are declared in `env-prod.tpl` instead.

The agent-provider key is deployment authority rather than runtime authority:
the target cannot fetch it for itself, so `env-ops.tpl` resolves it and the
controller carries it as a temporary private file into
`/etc/hamsterdan/secrets/agent-api-key` under the existing
no-implicit-replacement guard. Provisioning refuses to start
when the selected provider key disagrees with the `HAMSTERDAN_PI_PROVIDER` and
`HAMSTERDAN_PI_MODEL` pair `env-prod.tpl` declares. Values remain in temporary
controller files and private VM files; secret values do not enter Ansible
arguments.

No-launch validation still needs App credentials, so the playbook resolves a
throwaway copy of the environment, private key, and webhook secret into a
private temporary directory, runs the one-shot validation container against it,
and deletes it on both the success and failure paths. Nothing secret is
published to `/etc/hamsterdan/` by the deploy.

Select the exact previously qualified manifest:

```shell
scripts/ops uv run --frozen python deployment/runtime.py \
  provision \
  --manifest dist/deployment/<revision>/release.json
```

The playbook refuses an active service or separately running exact-name
container. It validates the App registration, required permissions and events,
configured installation, and selected repositories from a hardened one-shot
container. Only after validation does it install a systemd unit pinned to the
exact image ID. The unit is disabled and inactive, binds only to
`127.0.0.1:8000` when separately authorized to start, and runs the image
read-only as its unprivileged user with all capabilities dropped. A repeated run
with the same inputs must report `changed=0`.

## Apply installation configuration without redeploying

Add or remove account blocks and repository lines in
`deployment/config/installations.toml`, then apply only that file:

```shell
scripts/ops uv run --frozen python deployment/runtime.py configure \
  --file deployment/config/installations.toml
```

It requires a provisioned runtime but not a started one. Like provisioning, it
resolves a throwaway environment, App private key, and webhook secret from
`env-prod.tpl` and the installed target token, validates the proposed
configuration against them, and deletes them on both the success and failure
paths. Nothing it validates against depends on a previous service start, and the
authoritative fetch remains the unit's `ExecStartPre`.

This command does not build, transfer, or replace an OCI image; change the
systemd unit; rotate secrets; or alter VM infrastructure. It uses the exact
currently installed image to validate the complete proposed file against the
App registration, every configured installation, and every configured
repository in isolated temporary state. A validation failure before publication
leaves the current file and service untouched. Success atomically replaces only
`/etc/hamsterdan/config/installations.toml`; an active service restarts, while
an inactive service remains inactive. A repeated unchanged application reports
`changed=0` and does not restart the service.

If publication succeeds but an active service cannot restart, the validated new
file remains installed and the service fails closed; the command reports failure
instead of restoring an older authority snapshot. Correct or restore the tracked
file, reapply it, and inspect the service before attempting another restart.

Directly replacing the VM file and running `systemctl restart hamsterdan` uses
the same startup contract, but the configuration command is the reproducible
route: the tracked file remains the source of truth and malformed or
provider-invalid input cannot replace the working copy.

## CI and publication boundary

The **OCI image candidate** workflow is manual and runs the clean build and
verification commands above. It deliberately has no package-write permission
and does not publish an image.

GHCR publication is deliberately absent from this slice. The later publication
command must consume an already verified clean candidate without rebuilding,
push it under an immutable revision identity, and record the registry-returned
digest for deployment. Building must never push, and publishing must never
rebuild.
