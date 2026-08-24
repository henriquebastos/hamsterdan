# Hamsterdan deployment

This directory owns the deployment axis. The first slice produces and verifies
one `linux/amd64` OCI image; it does not create an exe.dev VM or configure a
running service.

## Release contract

- `deployment/Containerfile` is the image definition.
- `deployment/release.py` is the canonical build and verification interface.
- `deployment/pi/package-lock.json` is the shared Pi dependency graph used by
  both the image and the Amp orb setup.
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

## CI and publication boundary

The **OCI image candidate** workflow is manual and runs the clean build and
verification commands above. It deliberately has no package-write permission
and does not publish an image.

GHCR publication is deliberately absent from this slice. The later publication
command must consume an already verified clean candidate without rebuilding,
push it under an immutable revision identity, and record the registry-returned
digest for deployment. Building must never push, and publishing must never
rebuild.
