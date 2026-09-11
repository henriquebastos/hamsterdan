# Hamsterdan deployment

This directory owns the deployment axis. It builds one `linux/amd64` OCI image,
qualifies that exact image on the owned exe.dev VM, and provisions private
runtime custody for no-launch App validation. Initial provisioning leaves the
service inactive. A configuration update restarts an already active service.

Production runs `1eef74a` with Petrus `913acb0`. The
[PR85 proof](../docs/project/roadmap/cv19-private-v0-1-production/proof/pr85.md)
records deployment, the fresh hero journey, and two open findings. RS-037 first
deployed the Environment contract at `85c109e`; its Workbench record owns the
earlier startup-failure checks, PR84 comparison, and remaining remote Amp work.

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

The build installs the public, commit-pinned Petrus dependency with ordinary
frozen uv synchronization. It requires no GitHub, 1Password, or BuildKit secret.

## Build locally or in a Docker-enabled Amp orb

Prerequisites are Python 3.11 or newer and Docker with Buildx. In an Amp orb,
run Docker as a supervised orb service rather than a background shell process.

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

The operations vault supplies the exe.dev API token and SSH key. Application
credentials live in the selected Environment. `scripts/ops --provision`
additionally retrieves the production Environment-reader bootstrap from its
operations recovery item. Ordinary deployment and observation commands never
receive that bootstrap.

A workstation can use personal desktop authentication. For unattended commands,
set `HAMSTERDAN_OPS_TOKEN_FILE` to its protected operations-reader file, or supply
`OP_SA_HAMSTERDAN_OPS`. The wrapper removes loader tokens before executing the
command. This reader must belong to the machine running the command; copying a
production reader onto a development sandbox is unnecessary.

Register the exe.dev public key and scope it to the VM ownership tag:

```shell
cat /path/to/key.pub | ssh exe.dev ssh-key add --tag=hamsterdan
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

Runtime provisioning installs the selected Environment ID, its bootstrap,
the checksum-pinned 1Password CLI, and the installation allowlist. It transfers
no application credential. `deployment/config/runtime.env` supplies non-secret
settings shared by development and production. The installed
`/etc/hamsterdan/runtime.env` adds the selected Environment ID and container paths.

Both validation and service startup mount the CLI and bootstrap into the image
and run `/opt/hamsterdan/with-runtime-secrets`. This uses the official
`op run --environment` command, clears inherited credential variables before
retrieval, and removes the bootstrap from the application environment. Values
never pass through Docker's environment-file parser or stored environment
metadata. The host accepts multiline PEM, webhook-secret, and AI-key values
directly; it removes those variables after parsing so agent children cannot
inherit them.

The image sets `OP_CONFIG_DIR=/tmp/hamsterdan-op` on the existing private tmpfs.
The launcher passes this non-secret path as a CLI option, then removes the
variable before starting the application. The CLI can initialize without a
writable home directory or persistent configuration cache.

The bootstrap is stored at `/etc/hamsterdan/op-token`, mode 0400 and UID 10001,
inside the root-only runtime directory. Its read-only container mount remains
readable to that container UID. Removing the environment variable does not make
the mounted file inaccessible to code with that UID. Agent file tools are
restricted to their workspace and do not receive the mount or bootstrap as a
capability.

The pinned Environment CLI is `2.39.1-beta.01`. Its Linux amd64 archive SHA-256
is `57a5d7637e1f508194b48732136de57e53efcc447877a5dbcaed7801abeb7f49`.
The evaluated stable CLI does not support Environment retrieval.

The Amp project pre-setup script installs that exact archive under
`$HOME/.local/bin`, creating the directory when absent. It checks the amd64
architecture, archive checksum, installed version, and `op run --environment`
support; another executable named `op` does not satisfy the check. The script
installs only the CLI. Readers remain Amp project secrets and no login cache or
application value enters a reusable setup snapshot.

Select the exact previously qualified manifest:

```shell
HAMSTERDAN_ENVIRONMENT_ID=EXAMPLE_PROD_ENVIRONMENT_ID \
  scripts/ops --provision uv run --frozen python deployment/runtime.py \
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

It requires a provisioned runtime but not a started one. The validation
container retrieves the selected Environment through the same launcher as the
service, using isolated temporary state and the proposed installation file.
It never reads previously generated application credentials.

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

## 1. Inspect production without starting a host

Load the project `.envrc` so `HAMSTERDAN_OPS_TOKEN_FILE` selects the reader, then export
one PR's runtime metadata:

```shell
scripts/ops uv run --frozen python -m deployment.observe \
  --installation 150464548 --repository 1316665126 --pr 78 > /tmp/pr78.jsonl
jq 'select(.result_variant == "ReplyBlocked")' /tmp/pr78.jsonl
jq 'select(.layer == "dispatch")' /tmp/pr78.jsonl
```

`--layer history|dispatch|inbox|host` selects a layer; `--transition conv.reply`
selects a History transition. Each line carries the collection timestamp.
History sequence and Activity occurrence connect workflow decisions to Motus
dispatch state. Inbox rows expose delivery IDs, attempts, and error classes.
Host health exposes status and scheduler error classes. Stores are sampled
sequentially, so a running Activity may change between those reads.

The command uses fingerprint-pinned, batch-mode SSH with `IdentityAgent=none`.
The private key supplied by `scripts/ops` signs directly; an installed
1Password SSH agent cannot turn that operation into a fingerprint prompt.
Without the operations service-account environment, `scripts/ops` still uses
personal 1Password authentication. No credential value belongs in output.

The collector reads the existing stores without replay, writes, or service
changes. It requires the pinned LocalDispatch schema 3 and bounds History to
64 MiB. It omits prompts, Activity inputs and result bodies, webhook payloads,
claimant identities, and provider error prose. These metadata snapshots do not
replace agent transcripts or a complete offline proof package.

## 2. Application credentials and recovery

The two application Environments use the same schema:

| Variable | Value |
| --- | --- |
| `HAMSTERDAN_GITHUB_APP_ID` | App numeric ID |
| `HAMSTERDAN_GITHUB_APP_SLUG` | App slug |
| `HAMSTERDAN_GITHUB_CLIENT_ID` | App client ID |
| `HAMSTERDAN_GITHUB_PRIVATE_KEY` | Complete private-key PEM |
| `HAMSTERDAN_GITHUB_WEBHOOK_SECRET` | Webhook signing secret |
| `HAMSTERDAN_PI_API_KEY` | Selected provider's API key |

Development selects `hamsterdan-dev`, ID `EXAMPLE_DEV_ENVIRONMENT_ID`.
Production selects `hamsterdan-prod`, ID `EXAMPLE_PROD_ENVIRONMENT_ID`.
Each has its own read-only service account. Creation, grants, expiry and recovery
details are recorded in RS-037. Both Environments contain the six variables and
have passed read-only provider validation. The development reader is installed
locally; the production reader is installed on the VM and its service cutover
and supervised restart passed on 2026-09-07.

For development, select the Environment and protected bootstrap path in the
local ignored `.envrc`, then run `scripts/hamsterdan-host`. The local loader does
not render or read a `.env`. The hero journey's two human GitHub identities use
`scripts/demo-github ROLE COMMAND` and remain separate from the application's
selected Environment.
In an Amp orb, project environment variable `HAMSTERDAN_ENVIRONMENT_ID` selects
the development Environment and secret `OP_SA_HAMSTERDAN_DEV`
supplies its Environment-only reader. The managed service continues through
`scripts/hamsterdan-host` and fetches on every service start. Dependency setup,
requires no reader. Operations and demo identities retain separate readers;
every wrapper removes unrelated inherited credential families before retrieval.

For an application credential change, edit its selected Environment and restart
that application. In production use `systemctl restart hamsterdan`; in development
stop and rerun `scripts/hamsterdan-host`. A failed retrieval or missing required
value prevents startup. An already running process keeps its acquired values.
A Docker restart must execute the configured loader again; never substitute
stored environment values from an old container definition.

Recovery restores a valid Environment-reader bootstrap from protected recovery
custody, or restores the intended value in the selected Environment, then repeats
the same startup. Backups are never automatic fallbacks. Keep operation and
workflow state intact. The accompanying Petrus fix refreshes current AI authority
before new work after a crash. The dependency is published and pinned at
`913acb0a82928f34281d9ed15aaaf5c44de34617` and deployed in production.
No issuer-side key rotation or identity revocation is part of this migration.

## 3. CI and publication boundary

Public Actions are currently disabled. The historical workflow results below
do not qualify the current release through public CI.

Both workflows now install the exact public Petrus revision without GitHub or
1Password credentials. The prior build-reader and temporary Git-authentication
wiring is retired. Historical release `85c109eb0099ce1aad32d041c9ca69492f3b1272`
used the former reader; no service account or provider token was revoked by this
source migration.

The OCI image candidate workflow remains manual and has no package-write
permission. GHCR publication remains outside this deployment interface.
