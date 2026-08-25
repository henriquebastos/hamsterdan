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
  `deployment/ansible/runtime.yml` against an already qualified image.
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

Install the locked development tools with `uv sync --frozen`. The deployment
requires these project secrets in its environment:

- `EXE_DEV_API_TOKEN`, allowed to run `ls` and `new`;
- `EXE_DEV_SSH_PRIVATE_KEY_B64`, an unencrypted SSH private key encoded as one
  base64 line.

Register the matching public key with exe.dev and scope it to the VM ownership
tag:

```shell
cat /path/to/key.pub | ssh exe.dev ssh-key add --tag=hamsterdan
```

For a key held in 1Password, request OpenSSH format before encoding it:

```shell
op read 'op://VAULT/ITEM/private key?ssh-format=openssh' | base64 | tr -d '\n'
```

Do not print or persist that output. Send it directly to the environment or
secret manager.

The owned VM contract is `hamsterdan-prod`, tag `hamsterdan`, two CPUs, 4 GiB
RAM, 20 GiB disk, and exe.dev's default exeuntu image. Creation requires the
exact confirmation value and has no automatic deletion counterpart:

```shell
uv run --frozen python deployment/exe_vm.py ensure --confirm-create hamsterdan-prod
```

Deploy an already verified clean candidate by its manifest:

```shell
uv run --frozen python deployment/deploy.py \
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

Runtime provisioning consumes the same role-named App, installation,
repository, readiness, and agent-provider inputs used by `.agents/setup`, plus
the exe.dev API and SSH inputs above. Values remain in temporary controller
files and private VM files; secret values do not enter Ansible arguments or the
generated environment file.

Select the exact previously qualified manifest:

```shell
uv run --frozen python deployment/runtime.py \
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

The current executable boundary still accepts one installation account and the
provisioner refuses changed runtime inputs. The accepted next slice replaces
that limit with one restart-applied configuration portfolio containing multiple
installation accounts and repositories. Until that slice qualifies, do not
manually replace files under `/etc/hamsterdan`.

## CI and publication boundary

The **OCI image candidate** workflow is manual and runs the clean build and
verification commands above. It deliberately has no package-write permission
and does not publish an image.

GHCR publication is deliberately absent from this slice. The later publication
command must consume an already verified clean candidate without rebuilding,
push it under an immutable revision identity, and record the registry-returned
digest for deployment. Building must never push, and publishing must never
rebuild.
