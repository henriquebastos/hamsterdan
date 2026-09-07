---
status: Active
captured: 2026-09-06
navigator: Henrique
source: Navigator request to review secret management and use 1Password Environments where consumers fit
---

# 1. RS-037: Give each credential one editing authority

## 1a. Recommendation and checkpoint

Use two application Environments, `hamsterdan-dev` and `hamsterdan-prod`, with
the same application variable names and startup behavior. Include the GitHub App
identity, private-key PEM, webhook secret, and AI credential in each selected
Environment. Change the host configuration to accept credential values directly.
No independent saved credential may become a fallback for a new process.

The Navigator rejected the initial shared AI, build, and operations Environment
split on 2026-09-06 as unnecessary optimization. Development and production
should use the same application contract. The existing file interface is owned
code and does not constrain the design. This revision replaces that proposal;
the initial inventory and experiments below remain useful evidence.

The Navigator accepted the implementation plan on 2026-09-06: “We can make it
work now. Let's close it.” Implementation and migration are authorized. History
actions remain subject to the repository checkpoint. Both application
Environments are populated and their scoped readers are created. Production
cutover remains pending; current evidence is recorded below.

Success means editing one authoritative entry and restarting or rerunning its
consumer applies the new value. Each application instance reads exactly its
selected Environment. A missing value or retrieval failure prevents a new
consumer from starting. Existing workflow and operation history must survive
credential refresh. Provider/model selection remains OpenAI/gpt-5.6-sol.

## 1b. Current flow and observed gaps

Review baseline: `main` at `8be06bc`. Read-only SSH inspection found production
active, with no systemd drop-ins, and the unit matching the repository template.

| Consumer | Current source and delivery | Consequence |
| --- | --- | --- |
| Mac development shell | `hamsterdan-dev` vault -> `env-dev.tpl` -> `.envrc` renders `.env` -> direnv loads it | Renders only when absent or the template is newer. A 1Password edit is not a refresh trigger. |
| Deployment commands | `scripts/ops` -> `op run --env-file=env-ops.tpl` -> command | Fetches on each invocation, but injects the whole bundle and retains bootstrap variables in children. |
| Production GitHub credentials | VM token -> `op inject`, `op document get`, `op read` in systemd pre-start -> private files -> new Docker container | Mandatory retrieval precedes each systemd start; files remain under `/etc/hamsterdan` after stop. |
| Production OpenAI credential | `hamsterdan-ops/openai` -> controller temporary file -> provisioning -> `/etc/hamsterdan/secrets/agent-api-key` | Service restart never refreshes this file. Provisioning rejects a changed value under its no-implicit-replacement guard. |
| CI dependency install and image build | GitHub Actions `secrets.PETRUS_GITHUB_TOKEN` -> temporary Git auth or BuildKit secret | GitHub is another independently edited credential source. |
| Optional Amp host | `.agents/setup` consumes environment, generates `.amp/runtime` files; `.amp/services.yaml` launches `scripts/hamsterdan-host` | Launcher replaces ambient runtime configuration with the generated file. Restart does not repeat setup or retrieve credentials. `.agents/resume` only checks tooling. |

The development and operations OpenAI entries have byte-identical values. Their
Petrus-token entries are also byte-identical. Comparison occurred in memory and
printed only equality results. Equality does not establish that the Navigator
wants development and production configurations linked. The September 4 worklog
identifies the operations OpenAI entry as the production credential source;
this review did not compare the live VM's key bytes with that entry.

`HostConfig.from_environment` requires regular protected files for the GitHub
App key and webhook secret. `PiA2InstallationConfig` requires a protected regular
file for the AI key. The host does not load dotenv or integrate with 1Password.
A desktop Environment mount is a named pipe and cannot be substituted for those
regular files. The production container currently receives configuration and
file paths, with no 1Password token in its Docker environment.

The local `.envrc` exports both development and operations service-account
tokens into the project shell. A harmless child launched through `scripts/ops`
confirmed inheritance of `OP_SA_HAMSTERDAN_OPS`,
`OP_SERVICE_ACCOUNT_TOKEN`, and `OP_SERVICE_ACCOUNT_TOKEN_VPS`. The first two
serve the secret loader, not the deployment child. The target token is needed
only for provisioning, not every operation.

No Compose configuration or GitHub scheduled workflow was found in maintained
startup paths. Application workers and reminder timers run within host custody;
they do not have separate secret-loading configuration. Optional Amp runtime
was not configured on this Mac. Remote Amp settings and machine-wide scheduled
jobs were not inspected.

## 1c. Credential retained after a crash

The pinned installed Petrus implementation introduces a second OpenAI source:
encrypted connection state plus its local encryption key. Hamsterdan composes
this under `pi-a2/runtime-host/connection.sqlite3` and `pi-a2/keys`.

In `petrus/agenticus/runtime/pi_a2_host.py`, `_connection` returns an existing
READY connection before calling the current credential supplier. Constructor
recovery reconciles leases but does not refresh a READY credential. Normal
`close()` revokes the local connection and erases its encryption key. These are
local custody operations, distinct from revoking the credential at its issuer.

A disposable experiment reused the public scripted runtime and fixtures in
`tests/integration/host/test_pi_a2_factory.py`. A subprocess completed an
operation and called `os._exit(0)` without closing its host. The parent reopened
the same temporary state with a different fake-key supplier and started a new
operation. It then repeated after clean shutdown.

| Scenario | New operation | Current supplier calls |
| --- | --- | --- |
| Reconstruct after abrupt exit | Completed | 0 |
| Reconstruct after clean shutdown | Completed | 1 |

No real model, GitHub mutation, production state, or credential was used. All
temporary experiment state was removed. This verifies local pinned-library
behavior, not a production crash experiment.

Configuration alone cannot promise fresh AI authority after every restart.
Implementation needs a bounded supported lifecycle change that reconciles
retained connection authority with the current credential before new work.
Preserve operation settlement and workflow history. Investigate the public
Petrus custody operations and factory boundary before selecting the exact
change; do not edit SQLite internals, delete `pi-a2`, or put custom 1Password
retrieval in application code. If the public factory cannot express this,
propose the smallest upstream extension before changing the dependency.

## 1d. Verified vendor capabilities

Started with the official [documentation home](https://www.1password.dev/) and
[index](https://www.1password.dev/llms.txt). The preferred native-search helper
failed because `@earendil-works/pi-ai` was unavailable; official pages were read
directly instead.

1. Installed Mac CLI `2.34.1` and live VM CLI `2.35.0` lack `--environment`.
   Official Mac arm64 archives were executed in isolated temporary directories:
   stable `2.39.0` lacks the flag; `2.39.1-beta.01` exposes it. Existing
   installations were unchanged. The [Environment access guide](https://www.1password.dev/environments/read-environment-variables)
   still specifies beta CLI support. The [release notes](https://app-updates.agilebits.com/product_history/CLI2)
   list both versions. Linux beta execution remains untested.
2. `op run` precedence is Environment, env-file, then inherited shell. Missing
   Environment keys can therefore leave inherited values available. Clear
   credential inputs before retrieval and validate required names afterward.
   This is separate from successful retrieval. See the
   [injection guide](https://www.1password.dev/cli/secrets-environment-variables)
   and [run reference](https://www.1password.dev/cli/reference/commands/run).
3. [Local Environment mounts](https://www.1password.dev/environments/local-env-file)
   support Mac and Linux, use named pipes, and require the desktop app and
   authorization. They can serve interactive dotenv readers, but reading once
   through direnv would still leave an old shell snapshot. Prefer command-scoped
   retrieval for the common Mac/headless workflow.
4. [Service accounts](https://www.1password.dev/service-accounts/get-started)
   can read Environments. Grants are immutable; Environment grants currently
   require the web creation wizard. Existing vault readers cannot simply be
   retargeted. [Security](https://www.1password.dev/service-accounts/security)
   and [management](https://www.1password.dev/service-accounts/manage-service-accounts)
   document the separate bootstrap dependency and controlled replacement.
5. [SDKs](https://www.1password.dev/sdks/functionality) support reading
   Environments, but would add retrieval code where the CLI suffices.
   [Connect](https://www.1password.dev/connect/concepts) adds two containers,
   storage, and credentials to serve vault items. Neither solves an unmet
   requirement here.
6. The documented [GitHub Action](https://www.1password.dev/ci-cd/github-actions)
   loads vault references. Use a pinned CLI directly for an Environment-backed
   build rather than assuming that action reads Environment IDs.
7. [MCP](https://www.1password.dev/environments/mcp-server) supports desktop
   administration with authorization. It is not the runtime loader. One
   authentication and metadata listing succeeded: the connected account showed
   only `example-unrelated-environment`, with no Hamsterdan Environment. No Environment
   values or configuration were changed.
8. Retain the existing automated SSH path, which uses a short-lived private
   file, fingerprint pinning, batch mode, and `IdentityAgent=none`. Human SSH
   and commit signing can continue using the desktop agent. Requiring desktop
   authorization would not meet the unattended deployment requirement.

The MCP bundled guide calls Environments vault collections, while the current
official overview describes them separately from vault items. Use the current
official API and grant model; do not assume a vault grant includes an Environment.

## 1e. Revised authorities and delivery

Names below are proposed and IDs must be recorded only after creation. Preserve
existing values during migration; no issuer-side changes or rotations are
authorized. Development and production select independent configurations even
when initial values happen to match. Do not introduce synchronization between
them. Independent provider credentials, if later wanted, require deliberate
issuer-side work rather than assuming different Environment names isolate an
identical provider key.

| Application input | Development authority | Production authority |
| --- | --- | --- |
| `HAMSTERDAN_GITHUB_APP_ID`, `HAMSTERDAN_GITHUB_APP_SLUG`, `HAMSTERDAN_GITHUB_CLIENT_ID` | `hamsterdan-dev` Environment | `hamsterdan-prod` Environment |
| `HAMSTERDAN_GITHUB_PRIVATE_KEY`, containing the PEM | `hamsterdan-dev` Environment | `hamsterdan-prod` Environment |
| `HAMSTERDAN_GITHUB_WEBHOOK_SECRET` | `hamsterdan-dev` Environment | `hamsterdan-prod` Environment |
| `HAMSTERDAN_PI_API_KEY` | `hamsterdan-dev` Environment | `hamsterdan-prod` Environment |

Use the same provider/model configuration and variable schema on both routes.
The selected Environment, credentials, installation allowlist, and state
location may differ. Keep deployment layout and the tracked installation
allowlist in their current owners.

```text
development Environment -> op run -> same host configuration parser -> application
production Environment  -> op run -> same host configuration parser -> application
```

`HostConfig` already holds the GitHub key and webhook secret as strings.
`GitHubAppClients` passes the key string directly into GitHubKit's
`AppAuthStrategy`; webhook verification also accepts a string. Only the input
parser insists on files. Replace those file reads with bounded environment-value
validation and retire the competing `*_FILE` credential inputs.

Petrus `PiA2DirectAuthority.supply_api_key` accepts a callable returning a
`bytearray`. Hamsterdan can supply its validated environment value through that
interface. Remove the external AI-key file requirement while retaining
Petrus-owned operation materialization, cleanup, and the needed crash-refresh
correction. A 1Password SDK or application-specific retrieval helper is not
needed.

Direct environment input is recommended over Environment-to-file startup
generation because these actual downstream consumers already accept values.
The latter remains a supported alternative if a real consumer requires a file;
it would need automatic creation, protected permissions, and cleanup. It must
not become a second editing location.

Build and deployment are commands, not additional application stages. Do not
create build, operations, or shared-AI Environments. The tooling proposal is:

| Credential | Proposed authority | Consumer and lifetime |
| --- | --- | --- |
| `PETRUS_GITHUB_TOKEN` | One item in a vault containing only build credentials | Local/orb dependency install and CI/image build; temporary Git auth or BuildKit secret, removed after use |
| exe.dev API token | Existing `hamsterdan-ops` vault item | VM lookup/provisioning commands, loaded on invocation |
| exe.dev SSH key | Existing `hamsterdan-ops` vault item | Existing fingerprint-pinned SSH loader; private temporary file removed when the command ends |
| Production Environment-reader bootstrap | Recovery item in `hamsterdan-ops`, protected installed token on the VM | Explicit provisioning installs it; runtime CLI uses it to read the production Environment |
| CI build-reader bootstrap | Recovery item in operations custody, installed as a GitHub Actions secret | CI fetches the authoritative Petrus token; the bootstrap is the only installed CI credential |

The Navigator accepted a separate build vault on 2026-09-06 after considering
placing the Petrus token in the operations vault. CI must be able to retrieve
the Petrus token without access to the deployment SSH key or other operations
credentials. 1Password service accounts grant vault access, not individual-item
access. The official GitHub Actions integration reads vault items, so this route
also avoids requiring beta Environment support in CI.

Remove the independent `PETRUS_GITHUB_TOKEN` GitHub secret after the new route
is accepted, along with active development/operations duplicate references.
All builds retrieve the same authoritative item. Keep the existing build and
deployment implementations and their temporary-file cleanup.

Remove `OPENAI_AGENT_API_KEY`, duplicate GitHub App identity fields, and the
Petrus token from the universal operations bundle. Runtime provisioning should
install the target Environment ID and bootstrap, then validate through the
target's normal configuration parser; it should not copy application secrets
from the controller. Ordinary deployment and observation commands do not need
the production-reader bootstrap injected into their child environment.

The build/operations separation and complete implementation and migration plan
are accepted. No issuer credential rotation, identity revocation, or recovery
deletion is implied.

Use the same credential parsing and required-variable checks for interactive,
Amp, validation, and production starts. Remove stale dotenv inputs and scrub
credential variables before loading the selected Environment. After parsing,
keep GitHub credentials in host-owned objects and prevent them from reaching
agent subprocesses. Keep bootstrap tokens outside application children with
standard `env -u` and explicit process environments.

Qualify the Docker launch boundary before choosing its final wiring: passing
secrets through `docker run --env` leaves values in Docker configuration metadata,
while running `op run` inside the container changes CLI packaging and bootstrap
delivery. The application-facing contract is identical in either case. Verify
multiline PEM delivery without shell interpolation or a Docker env-file parser.

The running process may continue with its already acquired credential when
1Password is unavailable. A new start must fail. The operator edits the selected
Environment and restarts that application. Use the supervised start path that
actually reruns `op run`; a restart that only reuses Docker's stored environment
does not satisfy this contract. Preserve recovery copies outside active loading
paths and never use them automatically.

## 1f. Implementation and verification boundary

1. Complete metadata inventory of grants, expiry, recovery owners, and actual
   development consumers. Verified local bootstrap files are mode 0600 under
   `~/.config/op/service-accounts/`; the development identity can list only
   `hamsterdan-dev`, and the operations identity only `hamsterdan-ops`.
   This does not prove read-only grants or expiry. The live target bootstrap
   `/etc/hamsterdan/op-token` is mode 0600. Full grant/expiry inspection remains.
2. Create only explicitly accepted Environment readers. Application production
   reads `hamsterdan-prod`; application development reads `hamsterdan-dev`.
   Keep build/deployment grants bounded to their tool needs. Retain existing
   identities and recovery backups until separately ruled.
3. Pin and checksum the beta CLI for Environment readers. Verify Linux support,
   required-variable checks, exact multiline PEM bytes, missing variables,
   denied access, retrieval failure, token and GitHub-credential exclusion from
   agent children using fake values before migration. Keep stdout/stderr free
   of secret values. Validate the same parser on both application routes.
4. Implement the supported AI connection refresh lifecycle and test a genuinely
   new operation after clean stop and process death with old/new fake credentials.
   Test incomplete operations and active leases; preserve ambiguity/fencing.
5. Migrate values without printing them. Configure command launchers, CI,
   systemd, isolated validation, and the optional Amp host consistently. Amp
   runtime startup must retrieve current credentials rather than trust setup
   files. Do not assume this Mac proves the remote Amp lifecycle.
6. Run focused behavioral checks and the required project gates. Validate
   GitHub credentials through read-only registration/repository checks and the
   AI credential through a bounded authentication check. A working health
   endpoint alone is insufficient. A paid model request or live PR journey
   requires its own explicit scope; this review performed neither.
7. After acceptance, clean superseded active templates, cached-secret loaders,
   external credential-file loaders and mounts, AI-key deployment-copy logic,
   and tests for retired implementations. Update
   AGENTS.md, deployment/operator instructions, and supersede the standing
   `~/.config/hamsterdan` decision as current authority. Preserve its rationale
   and useful operational history. Inventory ignored helpers and old files
   before classifying them; do not delete recovery material as cleanup.

Recovery is deliberate: restore the authoritative 1Password value or a valid
bootstrap from protected recovery custody, then restart through the same path.
If an old application revision must be restored, it must still use the current
authority contract. Do not silently reactivate old `.env` files or retained
connection credentials. Updating 1Password does not alter issuer-side accounts.

## 1g. Implementation evidence, 2026-09-07 UTC

The Navigator accepted the verified implementation and authorized its commit
and push. Production has not been stopped, restarted, reprovisioned, or migrated.

The host now accepts the three direct credential values, preserves multiline
PEM text, rejects retired file inputs, and removes credential variables after
parsing. Development, production and isolated validation use the same
`scripts/with-runtime-secrets` launcher. The CLI and bootstrap are mounted into
the production container; credential values never become Docker environment
metadata. The bootstrap is excluded from the application environment, while its
read-only mount remains readable by the container UID.

Provisioning no longer carries the AI key or creates GitHub credential files.
Shared non-secret settings live in `deployment/config/runtime.env`. Build and
operations wrappers have separate templates; only `scripts/ops --provision`
fetches the production-reader bootstrap. CI uses the official action with
step outputs instead of exporting secrets throughout the job. Optional developer
tools retain their existing vault items through `scripts/dev-tools`; the old
development vault is distinct from the application Environment of the same name.

The local `.envrc` now contains selectors and protected file paths only. The
prior loader and `.env` were copied to `~/.config/hamsterdan/example-recovery/`,
mode 0700 directory and 0600 files. The active `.env` was removed only after
byte equality with recovery was checked. The old global envrc recipe remains
unchanged for other projects. The project-specific Mac beta CLI is installed at
`~/.local/lib/hamsterdan/op/2.39.1-beta.01/op`.

| Verification | Result |
| --- | --- |
| `scripts/check full` | Latest run including the validation-output fix: 1,279 routine Python tests in 98.05 seconds, 9 Bun relay tests, static/architecture/replacement checks, and distribution build passed. The GNU/Linux orb module is explicitly deselected on macOS. |
| Direct GitHub/AI configuration and composition files | 137 tests passed. |
| Shared launcher with fake provider and current/missing values | 9 tests passed, including all six required variables, exact multiline PEM, loader-token exclusion, retrieval refusal, and startup without a writable home. |
| GNU/Linux orb setup in an isolated Linux amd64 container | 12 tests passed with no warnings after registering the platform marker in the standalone harness. Missing and contradictory USER values both resolve to effective process identity. |
| Deployment runtime/CI/container contracts | 16 tests passed. |
| Actual operations-vault command through `scripts/ops` | Retrieved exe.dev credentials; the child verified that loader tokens, build token and production-reader bootstrap were absent. No credential values were printed. |
| Release and host integration after the image-input update | 13 tests passed. |
| Ansible provisioning/configuration syntax, shell syntax, `git diff --check` | Passed. |
| Linux beta CLI | Official amd64 archive executed successfully; `--environment` is present. SHA-256 `57a5d7637e1f508194b48732136de57e53efcc447877a5dbcaed7801abeb7f49`. |
| Mac beta archive | SHA-256 `5a10849ea208649f1c98913d13fa13c6ca9981f21dae3b8daee874701f15d8ff`. |
| Development image build and canonical image verification | Latest build passed against published Petrus `9ad2f7a8daac7aee03ba9529f65e18894aa8f608`, using the build-vault reader. Dirty baseline `8be06bcce3e8541388a8837278ed13764bdd5fb6` remains unpublishable. |

The focused Petrus change is in the sibling checkout. Its factory rotates a
retained READY connection using the current supplier before new work; it tracks
successful refresh separately from a spent supplier, preventing later fallback
after failure. Existing custody rotation invalidates prior leases. Terminal
replay remains credential-free, and operation/workflow history is preserved.
All 27 lifecycle tests passed under Linux, including real child-process exit,
clean shutdown, new fake credentials, and failed-refresh refusal. The macOS run
passed 25 and failed two existing Hands tests; both failures were reproduced
against the unchanged baseline. The full command could not start on this Mac
without `flock`; qualification moved to native Linux arm64 with Python 3.14.7.
After supplying the full test prerequisites, canonical `scripts/check full`
passed: 2,595 tests in 53.99 seconds, no selected skips, and all static checks.
Earlier disposable runs with missing tools and Git metadata are not passing
evidence. Ruff now excludes installed agent skills without modifying them; the
upstream development guide records the required external tools and guest Python
paths.

Petrus's local checkpoint policy allowed recording the validated changes as
`f41b0c0` (check configuration and prerequisites) and
`9ad2f7a8daac7aee03ba9529f65e18894aa8f608` (credential refresh, tests and decision).
The Navigator approved pushing those two commits together with the pre-existing
glossary-only `035effb`. A normal push succeeded; remote `main` was verified at
`9ad2f7a8daac7aee03ba9529f65e18894aa8f608`. Hamsterdan now pins that exact revision
in `pyproject.toml` and `uv.lock`. Locking retained the configured resolver cutoff;
the only lockfile change is the Petrus revision. Retrieval and frozen installation
used the build-vault reader and temporary Git authentication custody. Hamsterdan's
prepared changes have since received their separate commit and push approval.

The installed distribution metadata independently confirms the published commit.
The full Hamsterdan gate passes against it. Documentation coherence review checks
the superseded decision, current decision index, rollout status and active work;
all 72 local links in changed Markdown documents resolve. No additional
refactoring is needed for this scope. The beta CLI and pending CI/production
migration remain operational limitations owned by this record.

## 1h. External state and remaining work

Two application Environments were created and populated in account
`EXAMPLE_ACCOUNT_ID`:

1. `hamsterdan-dev`: `EXAMPLE_DEV_ENVIRONMENT_ID`.
2. `hamsterdan-prod`: `EXAMPLE_PROD_ENVIRONMENT_ID`.

After the Navigator signed in, the web wizard created two application readers.
Each has Read access to exactly its application Environment, no vault grants,
and no vault-creation permission. No expiration option was presented. Both
readers list zero vaults and fail retrieval of the opposite Environment.

| Reader | Protected local file | Operations recovery item ID |
| --- | --- | --- |
| `example-dev-reader` | `~/.config/hamsterdan/example-dev-reader.token` | `EXAMPLE_DEV_RECOVERY_ITEM_ID` |
| `example-prod-reader` | `~/.config/hamsterdan/example-prod-reader.token` | `EXAMPLE_PROD_RECOVERY_ITEM_ID` |

Both bootstrap files were created mode 0600; operations recovery items contain
concealed `credential` fields. Reads through the operations reader verified both
recovery copies match their local files. The actual `scripts/ops --provision`
wrapper retrieves the new production reader while excluding the build credential
and its own loader token. Production's reader is not installed on the VM.

All six application variables were transferred privately through the official
MCP server, without rendering credential files. Development uses its existing
vault's GitHub App fields, PEM document and OpenAI item. Production uses its
existing vault's GitHub App fields and PEM, plus the operations OpenAI item that
supplied its live key. Read-only SSH comparisons confirmed production's effective
PEM, webhook secret and AI key match those sources. Migration preserves the old
parser's whitespace trimming while retaining PEM interior newlines.

Both readers retrieved all six values through the shared launcher. Comparisons
inside the child verified exact source equality and absence of the bootstrap.
An initial comparison of printed JSON encountered the CLI's output masking;
the corrected probe compares privately inside the child and prints booleans.
Both Environments passed actual GitHub App registration, permissions, events,
installation and repository checks, plus OpenAI's authenticated models-list read.
No model invocation or workflow processing occurred. The pinned Pi runtime is
installed locally, and `scripts/hamsterdan-host validate` passed with isolated
temporary state.

Hardened Linux qualification found that the CLI tried to create configuration
under `/nonexistent`, which the read-only image forbids. The image now supplies
`OP_CONFIG_DIR=/tmp/hamsterdan-op` in its existing private tmpfs. The shared
launcher passes that path as a CLI option and clears the variable before the
application child. A regression test and full Hamsterdan gate pass. The rebuilt
development image passed canonical verification; its image ID is
`sha256:f0d904879a4f16094f9b4605d9c94df3dbffbc956cc01d2fc45eb50556d06173`.
That earlier image was dirty and contained the old Petrus pin. Full-container validation with
the production Environment passed in 45 seconds under Linux amd64 emulation,
using an unprivileged user, a read-only root, no capabilities, and isolated tmpfs
state. An earlier attempt reached Python/Node but exceeded the 100-second harness
bound while other emulated checks ran. The successful rerun used the same image
and credentials with a 400-second harness bound. No production state was mounted
or changed, and the disposable container and its bootstrap tmpfs were removed.

After publishing and pinning Petrus, the development image was rebuilt and
passed canonical verification. Its image ID is
`sha256:7ebf83ac2c93fcfd260e4ace8f911c0d103d6547f034d68f14551a184a0e0760`;
the manifest is
`dist/deployment/8be06bcce3e8541388a8837278ed13764bdd5fb6-dirty/release.json`.
This supersedes the earlier image for local qualification. A clean committed
candidate, CI verification and production cutover still remain.

Personal vault listing confirmed the earlier timed-out creation had not made a
build vault. Created `hamsterdan-build`, ID `EXAMPLE_BUILD_VAULT_ID`, and its
`petrus-github-token` item, ID `EXAMPLE_BUILD_TOKEN_ITEM_ID`. Private in-memory
comparison verified that its credential equals the existing operations value.
No issuer credential changed.

Created two service accounts with exactly `hamsterdan-build:read_items`; no
scheduled expiration was requested. Each reader lists only the build vault,
retrieves its credential, and is denied access to the operations-vault source.

| Reader | Protected local file | Operations recovery item ID |
| --- | --- | --- |
| `example-build-reader` | `~/.config/hamsterdan/example-build-reader.token` | `EXAMPLE_BUILD_MAC_RECOVERY_ITEM_ID` |
| `example-ci-reader` | `~/.config/hamsterdan/example-ci-reader.token` | `EXAMPLE_BUILD_CI_RECOVERY_ITEM_ID` |

Both local files were created mode 0600, and recovery items use the reader name
and concealed `credential` field. Reading both recovery items through the
operations reader verified equality with the protected local files. Tokens
passed through captured subprocess
output and stdin, never command arguments or printed output. The actual build
launcher successfully read the private Petrus repository through GitHub's API;
its child verified loader and operations credentials were absent.

Installed the CI reader as GitHub Actions secret
`OP_SERVICE_ACCOUNT_TOKEN_BUILD`; metadata confirms update at
`2026-09-07T03:59:46Z`. The old `PETRUS_GITHUB_TOKEN` secret was retained until both
new workflow routes passed, then removed. Publication evidence follows below.

## 1i. Publication and deployment-output qualification

The accepted implementation was committed and pushed as
`bfd70e0a001acd62ff2b2625ff0a25831b8d16e9`. The
[image workflow](https://github.com/henriquebastos/hamsterdan/actions/runs/34084283245)
passed using the new build-vault reader. The
[first CI run](https://github.com/henriquebastos/hamsterdan/actions/runs/34084266727)
retrieved its build credential, installed the exact Petrus dependency, and removed
temporary Git authentication, then failed one existing scripted-runtime deadline
test: 1,271 tests passed and one failed. The scripted delay stops at the runtime
deadline and can race timeout settlement; that implementation is unchanged from
the prior Petrus pin. Eight subsequent focused local runs passed. The final CI
run below passed, including this test. The earlier failure remains recorded as
an intermittent test concern; no timeout behavior was weakened to obtain a pass.

A real-launcher check found that concealing the numeric App ID replaces an
unquoted JSON number with the CLI's masking text. The host command succeeds,
but Ansible cannot parse its evidence. The validation report now renders the
App ID as a string so masking preserves valid JSON. A regression test reproduced
the parsing failure before the fix. Both actual application Environments now
pass host validation and the deployment JSON parser, using isolated local state.
Concealment stays enabled; no Environment value was changed.

The follow-up fix was committed and pushed as
`85c109eb0099ce1aad32d041c9ca69492f3b1272`. Both
[CI](https://github.com/henriquebastos/hamsterdan/actions/runs/34084541429) and the
[image workflow](https://github.com/henriquebastos/hamsterdan/actions/runs/34084559585)
passed on that exact revision. CI verified build-vault retrieval, dependency
installation, temporary-authentication removal and all selected tests. Only
`OP_SERVICE_ACCOUNT_TOKEN_BUILD` remains in the repository's Actions secret
listing; the obsolete standalone Petrus token copy was removed after both passes.
The build-vault item, issuer credential and recovery copies remain intact.

The clean local release image also passed canonical verification. Its manifest is
`dist/deployment/85c109eb0099ce1aad32d041c9ca69492f3b1272/release.json`, with
`dirty=false` and `verified=true`. Its Docker image identity is
`sha256:de64787a2b4b39b0535bd4a3c71cdecdd306ab753f8b842bf613a63738cea071`.
Production is still unchanged. This documentation-only receipt does not change
the qualified application or image inputs.

Remaining: qualify the clean image on the VM and perform
supervised production cutover; verify restart
freshness and failure behavior; retire remaining active legacy external sources.
Remote Amp configuration remains unverified.
No issuer-side rotation, identity revocation, or recovery deletion occurred.

Review: the prepared change removes cached runtime inputs and deployment secret
copies. No new SDK, synchronization process or secret-storage service was added.
The beta CLI dependency and incomplete external migration remain explicit
operational limitations. RS-037 stays Active until those operations and the
Navigator's acceptance/history checkpoints are complete.
