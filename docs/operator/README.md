# HBNetwork qualification operator runbook

This runbook operates the **private, HBNetwork-owned GitHub App** used only on
the public `HBNetwork/demo-pr-readiness` fixture. GitHub requires an App owner
or organization owner to approve registration, increased permissions,
installation, and private-key creation. Trusted operator automation may use the
human's existing repository authority for PR creation or merge, but App effects
never use that credential and never impersonate the human.

## 0. Create the private source repository and durable relay

The canonical private source repository and Amp project already exist at
`henriquebastos/hamsterdan` and `@henriquebastos/hamsterdan`. A new deployment
should verify that source ownership before publishing prepared history:

```sh
git remote get-url origin  # must be https://github.com/henriquebastos/hamsterdan.git
git push -u origin main
```

Open the repository through its existing Hamsterdan Amp project. The committed
project plugin registers one stable durable webhook for that Amp thread and
stores its capability URL in mode `0600` `.amp/runtime/github-webhook.json`.
Treat that URL like a credential: paste it only into GitHub's App settings and
never commit, log, or send it through chat. This is the App webhook URL itself;
do **not** append `/github/webhooks`. The relay can be registered before the App
host has credentials. It queues deliveries, wakes the orb, and forwards exact
signed bytes to loopback once the host is available.

An ordinary Amp portal is not webhook ingress: portals require a signed-in
viewer. The durable relay is deliberately separate from browser access.

## 1. Register the private App

While signed in as an HBNetwork organization owner, open **Organization
settings → Developer settings → GitHub Apps → New GitHub App**. Name it
`Hamsterdan` (record the assigned slug), set the homepage to this project's
repository, make it **private / only on this account**, disable user
authorization, enable webhooks, and use the capability URL from step 0. GitHub's registration guide is
authoritative: <https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app>.

A private App can be installed only on its owner, so this HBNetwork-owned App is
correct for the HBNetwork sandbox. GitHub permits changing an App's visibility
later under **Advanced → Make public**. A public App could then be installed by
multiple organizations. The accepted self-hosted contract uses one App
registration across an operator-configured portfolio of installation accounts
and repositories, applied first by supervised restart without SaaS accounts or
an administration UI. Changing this App's visibility or installing it on
another account remains a separately approved provider action; editing runtime
configuration alone does not create a GitHub installation.

Configure exactly this repository-permission/event contract (no organization or
account permissions):

| Repository permission | Access |
|---|---|
| Administration | Read — effective branch rules and branch-protection fallback |
| Actions | Read — workflow runs, attempts, jobs, and bounded failure evidence |
| Contents | Read and write — compare/refs plus host-created Git objects and exact ref CAS |
| Issues | Read and write — PR conversation lookup, dashboard, findings, reminders, and broker marker |
| Pull requests | Read and write — PR authority, reviews, requested reviewers, review threads, and PR-thread comments |

Subscribe to exactly: **Issue comment**, **Pull request**, **Pull request
review**, **Pull request review comment**, **Pull request review thread**, and
**Workflow run**. The review-thread event is required to observe native thread
resolution without inventing a review-comment edit. Metadata read is implicit.
The live provider denied PR-thread comment creation to an installation token
carrying `issues=write` and `pull_requests=read`; its accepted-permissions
response required `pull_requests=write`. Host code still exposes no merge,
formal-review, or PR-edit operation, and every admitted comment effect retains
its current-head/operation fence. GitHub also sends App lifecycle **Ping**,
**Installation**, and **Installation repositories** deliveries; they are
verified and applied but do not appear in the selectable startup event set.
These values are startup-validated against the provider. No Checks, statuses,
formal-review writes, Actions writes, Workflows writes, merge, bypass,
organization, or user permission belongs in this first App. Permission
semantics: <https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps>;
webhook events: <https://docs.github.com/en/webhooks/webhook-events-and-payloads>.

Record the App ID, client ID, slug, private-key PEM and webhook secret in the
selected 1Password application Environment, using the
[shared six-variable schema](../../deployment/README.md#2-application-credentials-and-recovery).
The provider's webhook secret must match that Environment value. Existing
registrations retain their credentials during the migration; generating new
issuer credentials is a separate operation. Never commit credential files.
GitHub key guidance:
<https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps>;
webhook security: <https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries>.

## 2. Configure and install

Development selects `hamsterdan-dev`; production selects `hamsterdan-prod`.
Both use the same launcher and variable names. Supply an Environment-only
reader and the pinned beta CLI as described in
[deployment custody](../../deployment/README.md). The selected Environment
owns App identity and AI credentials. Shared non-secret policy lives in
`deployment/config/runtime.env`.

Remote Amp settings still need migration to separate application and build
readers. The old direct-secret project entries do not satisfy the current
launcher. RS-037 owns that unfinished operation and fresh-orb qualification.

The optional qualification identities retain their project settings:

```sh
printf %s henriquebastos | amp secrets set GITHUB_DEMO_AUTHOR_LOGIN --project --env --data-file -
printf %s crisbastos | amp secrets set GITHUB_DEMO_REVIEWER_LOGIN --project --env --data-file -
```

Installation accounts and repositories live in the tracked
`deployment/config/installations.toml`, not project environment variables. Each
`[[accounts]]` block names one GitHub account by stable ID and expected login;
its repository lines name stable repository IDs and expected full names. Edit
that file to change routing authority. The development launcher reads the
tracked file directly on every start. The VM configuration-only command
validates and applies it without rebuilding or redeploying the application:

```sh
scripts/ops uv run --frozen python deployment/runtime.py configure \
  --file deployment/config/installations.toml
```

The App must already be installed on every listed account with access to every
listed repository. The current private App is installable only on HBNetwork;
changing its visibility or installing it on another account remains a separate
operator-approved GitHub action.

The pinned Petrus source repository is private. Install dependencies with
`scripts/build-secrets scripts/sync-dependencies`. Its reader grants access only
to `hamsterdan-build`, where the read-only GitHub token lives. Temporary build
authority is removed after installation and kept out of the application child.

The two demo-human identities are optional and do not gate production setup.
Only for the controlled three-actor fixture, set both login variables above and
store their `gh` `hosts.yml` documents as `GITHUB_DEMO_AUTHOR_HOSTS` and
`GITHUB_DEMO_REVIEWER_HOSTS`. Setup accepts the pair only when both exact,
distinct logins validate; otherwise it retires both identity roots while still
allowing a fully configured App/provider runtime. Role names are deliberate:
changing the people later changes project settings, not source code.

On each new orb, `.agents/setup` installs dependencies through the build reader,
verifies the optional demo identities through the trusted GitHub CLI, and
installs the pinned Pi runtime. It does not generate application credential
files or a runtime `.env`. `scripts/hamsterdan-host` retrieves current values
from the selected Environment on each start. Missing access or required values
prevent startup. Edit the Environment and restart the application to refresh
credentials while preserving runtime history.

GitHub assigned this registration the slug `hamster-dan`, so its bot login is
`hamster-dan[bot]` and its exact public mention is `@hamster-dan`. Trusted PR
participants interact through natural comments beginning with that mention,
for example `@hamster-dan explain the current blockers`. The lookalike
`@hamsterdan` is not a GitHub alias and is intentionally not accepted.

From the App settings choose **Install App**, select HBNetwork, choose **Only
select repositories**, and select only `demo-pr-readiness`. Installation docs:
<https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app>.

## 3. Validate, serve, and prove ingress

The shared launcher clears inherited credentials, invokes the pinned 1Password
CLI for the selected Environment, and removes its loader token from the
application child. The host accepts credential values directly and removes
GitHub credentials before agent composition. The host's Git publication boundary
separately runs every Git command with global/system config, prompts, hooks, askpass, SSH-agent, and
ambient credential helpers unavailable. Validate the App registration and
selected-repository installation through that boundary. Non-sharded V5 is the
production topology after every setup:

```sh
scripts/hamsterdan-host validate
amp orb services ensure
```

`amp orb services ensure` starts the supervised host. On a root with retained
webhook custody, startup can process GitHub work and cause App effects. Run the
non-mutating `validate` step first and obtain the required deployment approval
before starting a production candidate.

The former `scripts/hamsterdan-host topology ...` switch is retired and fails
closed. Setup removes its stale private selector. Existing topology-labeled
state still cannot be opened under a different topology; a root containing the
former production topology must be migrated or replaced deliberately rather
than silently reinterpreted as V5 state.

The supervised service listens only for the local durable relay; it does not
need a browser portal. Ensure the App's webhook URL is the exact capability from
`.amp/runtime/github-webhook.json`, select **Active**, save, and request a
GitHub ping/redelivery. Re-run `validate`, check loopback health from inside the
orb, and run:

```sh
scripts/hamsterdan-demo preflight --health-url http://127.0.0.1:8000
```

The health result is bounded and secret-free. A successful ping returns 202 from
the host with `custody=durable`; the relay treats anything else as uncertain and
retries. Keep `.amp/runtime/` host-only; credentials, the relay capability, and
installation tokens never enter an agent request or checkout.

GitHub installation tokens expire after one hour. GitHubKit mints, caches, and
remints them in process; restart discards the cache and mints again. Hamsterdan
does not persist a token. Logs expose only method, API path, GitHub request ID,
status, rate-limit facts, delivery UUID, installation/repository/PR IDs,
disposition, and bounded error class—not authorization headers, tokens, webhook
signatures, comment prose, or raw payloads.

## 4. Broker cutover and qualification

The HBNetwork broker now recognizes only the Hamsterdan App identity. On an
uncut fixture, prepare (but do not merge) the one-file strict-grammar cutover;
on HBNetwork this command reports the broker as already current:

```sh
scripts/hamsterdan-demo prepare-broker
```

On an historical uncut fixture, preparation changes only
`.github/workflows/rerun-broker.yml`, including the event prefix, full-match
regex, and human-association gate. The current HBNetwork broker keeps the exact
`hamster-dan[bot]` actor and `hamsterdan-rerun` prefix in the workflow while
delegating exact marker and run/head/repository/PR/workflow binding to
`tools/rerun_broker.py`; the workflow performs one rerun POST only after that
validation. Preflight validates both files as one contract while retaining the
accepted historical legacy and inline-Hamsterdan shapes. **Merge a prepared
cutover PR only after** host validation, healthy webhook ingress,
selected-repository routing, and App installation are all confirmed. Never
count an old marker as Hamsterdan evidence. Never run the legacy PAT service and
Hamsterdan as concurrent writers.

After cutover, create controlled PRs with the current human operator's `gh` and
git credentials (credentials remain outside agent territory):

```sh
gh auth status
gh auth setup-git  # one-time human operator workstation setup
scripts/hamsterdan-demo create --scenario clean-green
scripts/hamsterdan-demo create --scenario first-attempt-flake
scripts/hamsterdan-demo create --scenario hero-review
scripts/hamsterdan-demo inspect --pr <number>
scripts/hamsterdan-demo inspect --pr <hero-number> --expect-hero-review --expect-readiness absent
```

Qualification orbs receive the two human operator sessions from the role-based
Amp project secrets when that optional pair is configured. `.agents/setup`
writes them only to ignored, mode-`0700`
identity roots under `.amp/runtime/`, with mode-`0600` files. Human commands
must bypass Amp's injected `gh` wrapper and select one identity explicitly:

```sh
GH_BIN=/usr/bin/gh
[[ -x "$GH_BIN" ]] || GH_BIN="$HOME/.local/bin/gh"

# Author/operator
/usr/bin/env -i HOME="$HOME" PATH="/usr/bin:/bin" \
  XDG_CONFIG_HOME="$PWD/.amp/runtime/gh-demo-author" "$GH_BIN" api user

# Distinct reviewer
/usr/bin/env -i HOME="$HOME" PATH="/usr/bin:/bin" \
  XDG_CONFIG_HOME="$PWD/.amp/runtime/gh-demo-reviewer" "$GH_BIN" api user
```

Never print, copy into source, or pass either session into the host or agent
checkout. `henriquebastos` owns fixture branches, PR lifecycle, and operator
actions; `crisbastos` owns distinct-human reviews. GitHub renamed this same
reviewer account from `hsbastos` after CV3 acceptance; historical evidence keeps
the login observed at the time. The App remains the only product effect
identity. Rotate the project secrets when either OAuth session is revoked or
replaced.

Creation branches from fresh `origin/main`, changes only paths admitted by the
fixture's closed schema, validates them, and creates—but never merges—the PR.
The `hero-review` route also requests `crisbastos` immediately so human review
authority is present before readiness can settle. Inspection covers both PR
conversation comments and native inline review comments. It requires an
App-owned dashboard, no legacy marker, exact workflow heads, and App ownership
for every recognized comment. Readiness is required by default; pass
`--expect-readiness absent` only at a deliberately blocked checkpoint, such as
the initial hero findings. Output contains only recognized marker
identities/IDs/URLs, bounded workflow/job and finding-shape facts, and
attribution. GitHub's App bot may be the **authenticated pusher** exposed in
REST `author`/`committer` user objects, while the nested Git commit `author` and
`committer` are explicit commit metadata; neither proves the other. See
<https://docs.github.com/en/rest/commits/commits#get-a-commit> and
<https://docs.github.com/en/rest/git/commits#create-a-commit>.

### Cohesive three-actor hero rehearsal

The hero fixture is the largest single-PR review story. It keeps CI green while
seeding three independently discoverable defects: one safe one-line replacement,
one conceptual policy issue, and one invariant broken at two non-contiguous
locations. Dan must discover them from the diff. Scenario controls never inject
comment prose or provider state.

Rehearse with three identities: `henriquebastos` is the author, `crisbastos` is
the team reviewer, and `hamster-dan[bot]` is the App. Coordinate any host stop or
restart with the operations thread that owns runtime custody. A host stop before
creation is optional for ordinary use, but useful for a deterministic recording:
the relay durably queues the opened and review events while the humans establish
the first review state.

1. Stop the supervised host without deleting its unit state, then use Henrique's
   explicit identity to run `scripts/hamsterdan-demo create --scenario
   hero-review`. The command opens the PR and requests Cris automatically.
2. While the host remains stopped, use Cris's explicit identity to submit one
   `REQUEST_CHANGES` review on the original head. Keep its text short and
   human-authored; do not copy Dan's expected findings into it.
3. Restart the supervised host. Production renders three native comments in
   **Files changed**. Selected V5 renders one complete App-owned findings batch
   in **Conversation**. In either presentation, capture the lease replacement,
   conceptual approval-policy defect, cache-key defect with its related
   location, and the updating dashboard. Dan's blocking review may then launch
   the ordinary fenced App repair and advance the head.
4. After the repaired head settles, Henrique posts `@hamster-dan status`. Capture
   Dan's concise current-gate reply and the refreshed dashboard. If demonstrating
   a conversational mutation, post one explicit bounded instruction. Dan executes
   an unambiguous authorized instruction directly; an ambiguous request must ask
   for clarification without changing the repository.
5. Cris reviews the current head and submits `APPROVE`. Resolve any human inline
   thread if one was created. Capture the final dashboard and readiness advisory,
   then close the rehearsal PR unmerged unless a separately approved demo calls
   for merge.

At the blocked finding checkpoint, `inspect --expect-hero-review
--expect-readiness absent` adds redacted, topology-neutral checks for the three
fixture defects. Production's three native comments and V5's one findings batch
must both expose the lease suggestion, conceptual approval-policy finding, and
cache finding with its related location. The command reports semantic shape
counts and provider URLs but never finding prose.

For a cohesive recording, use three pinned browser tabs rather than repeatedly
scrolling one growing conversation: **Conversation** anchored at the dashboard,
**Files changed** filtered to unresolved comments, and **Actions** on the current
run. Record short checkpoint clips and cut between them. Refresh only the active
tab, keep the same browser zoom, and open each comment's permalink before the
next event. This prevents appended comments from moving the subject under the
cursor while preserving an honest chronological story.

Finding publication is lookup-first and fenced to the exact current head.
Production uses native comments, where suggestions apply only at the primary
anchor and a multi-location finding remains one operation with links to its
other locations. V5 uses one immutable batch carrying the complete validated
finding content and one digest-bound operation. If GitHub definitively rejects
a production changed-line anchor as unavailable, Dan falls back to one immutable
conversation comment; authorization failures and malformed payloads fail closed
rather than disguising themselves as fallback success.
Review and conversation agents receive Dan's canonical voice rules. Deterministic
status, dashboard, reminder, readiness, malformed-request, and mutation messages
follow the same register without changing stable markers or operation identities.
Security and protocol
failures remain plain and joke-free.

The accepted HBNetwork portfolio is PR 14 at head
`4e4f411c0ef352d7b39f7c7071380c433aa63a3b`. CI run `30699749460` failed on
attempt 1, the App-owned exact rerun marker activated the strict broker, attempt
2 passed, and the App-owned readiness advisory followed at the same head.
`scripts/hamsterdan-demo inspect --pr 14` passes every ownership, marker,
workflow-head, and attribution check. Preserve future PR URLs, numbers, heads,
run attempts, and redacted inspection JSON in the same way; the CLI does not
declare a partial run accepted.

Repeat the flake scenario while restarting `hamsterdan-host` after the rerun is
requested. Durable inbox replay and the one-minute persisted-Instance sweep must
converge without duplicate comments. Retryable delivery failures back off from
one second to five minutes and park after 20 attempts; `/healthz` exposes a
`failed` inbox count for diagnosis. GitHub does not automatically redeliver a
delivery missed before first PR admission, so use the App's **Recent deliveries
→ Redeliver** action after an outage.

## 5. Authority and collaboration portfolio

Authority qualification uses real GitHub state. Never add draft, stale,
conflict, review, approval, or thread fields to `.pr-lab/scenario.json`,
`.pr-lab/scenarios/**`, or `scenario-fixtures/**`. The Net retains only its
normalized workflow facts; the operator command below reads richer provider
evidence without writing it to History:

```sh
scripts/hamsterdan-demo inspect-authority --pr <number> --expect <expectation>
```

The accepted expectations are `non-draft`, `strict-stale`, `conflict`,
`review-requested`, `changes-requested`, `required-approval`,
`unresolved-thread`, and `collaboration-clear`. The command revalidates the head,
base branch, and current base SHA after collection. It fails closed when
mergeability is still calculating, a bounded provider collection may be
incomplete, or authority changes during inspection. Retry an indeterminate read;
never reinterpret it as acceptance.

### Isolated fixture topology

Create a unique same-repository base branch from current `main`, then apply a
ruleset targeting only that exact branch. The ruleset requires the existing
`lint`, `type`, `unit`, `build`, and `integration` checks to be strict, one
approval, and review-thread resolution. Do not edit the `main` ruleset. Record
the base ref, initial SHA, ruleset ID, operator login, and distinct reviewer
login before creating PRs.

From the initial authority-base SHA, prepare three branches:

1. **base advance** replaces only the first module docstring in
   `src/pr_fixture/__init__.py`;
2. **strict stale** appends a unique documentation-only line to `README.md`;
3. **true conflict** replaces the same original module docstring with text
   different from the base-advance branch.

Each branch must pass the fixture's full checks. Obtain a real distinct human
approval for the base-advance PR and merge that PR with the ruleset's allowed
squash method. This is the portfolio's only planned merge. GitHub must then
report the README PR behind but cleanly mergeable and the same-line PR as a real
conflict.

After the base advance, create two more branches from the new authority-base
SHA using unique neutral README additions:

4. create **draft/ready** as a draft PR, inspect `draft=true` through the REST
   PR fact, then mark it ready and inspect `non-draft`;
5. create **collaboration** as ready, request the distinct reviewer, and inspect
   `review-requested`.

On the collaboration PR, the reviewer submits a real inline
`CHANGES_REQUESTED` review. Record both `changes-requested` and
`unresolved-thread`. The reviewer then submits an approval: accept
`required-approval` only when GitHub GraphQL reports `reviewDecision=APPROVED`.
The unresolved thread must continue to block until the reviewer resolves it;
then inspect `collaboration-clear`.

On the stale and conflict PRs, address `@hamster-dan` with the respective base
update or conflict-resolution instruction. Each explicit authorized instruction
executes directly; ambiguous wording must clarify without mutation. Record the
operation identity, old and new head, App-authored commit attribution,
successful exact-head checks, and the final authority inspection. Hamsterdan
must use a credential-free agent
checkout and host-owned compare-and-swap publication; never update either branch
manually, force-push, bypass protection, or edit History.

For every transition preserve PR and visible effect URLs, exact SHAs, bounded
inspection JSON, Actions run IDs/conclusions, History projection, unresolved
Activity count, and duplicate-effect assessment. Keep PR14/15 and PR23-28
untouched. PR20's historical retry churn was resolved under CV3.DS3; its drained
state alone was not used as acceptance evidence.

The accepted CV3.DS2 portfolio used branch-only ruleset `20242556` and PR29-33.
PR29 was the one reviewed base merge. PR30 proved strict stale-base update, PR31
proved true conflict resolution, PR32 proved draft silence followed by ready
admission, and PR33 proved the complete requested-review, changes-requested,
approval, and thread-resolution sequence. PR30-33 remain open and unmerged. The
accepted exact heads and durable evidence are recorded in the CV3.DS2 roadmap
item and worklog; do not reuse these PRs for later lifecycle fault injection.

For an exhausted delivery, inspect only its bounded identifiers/error class and
then explicitly requeue it after correcting the provider or configuration
failure:

```sh
scripts/hamsterdan-host inbox
scripts/hamsterdan-host requeue --delivery <canonical-delivery-uuid>
```

Requeue resets the retry schedule for the already verified, sanitized durable
observation; it does not bypass signature verification, duplicate custody,
repository admission, current-authority fencing, or effect lookup.

## 6. Lifecycle and recovery qualification

Use fresh isolated PRs for CV3.DS3. Do not mutate accepted PR14/15, PR23-28, or
PR29-33, and do not use historical PR20 as a fault fixture. Coordinate deploy,
restart, and runtime inspection with the thread that owns the supervised host;
never start a competing writer.

Inspect a persisted Instance without replaying or editing it:

```sh
scripts/hamsterdan-host inspect-instance \
  --installation <installation-id> --repository <repository-id> --pr <number>
```

The command requires positive canonical IDs, rejects symlinked or nonregular
state paths, bounds both state files, verifies a stable snapshot and exact
Instance binding, and emits no payload, prompt, result, error prose, or
credential. Preserve its JSON before and after each controlled transition.

Fault injection is disabled when `HAMSTERDAN_QUALIFICATION_FAULT` is absent. To
arm one process-local failure, place exactly one compact JSON object in the
supervised service environment and restart it:

```sh
HAMSTERDAN_QUALIFICATION_FAULT='{"repository":"HBNetwork/demo-pr-readiness","pull_request":<number>,"boundary":"agent","phase":"timed_out","kind":"review","operation":"next"}'
```

The exact keys are `repository`, `pull_request`, `boundary`, `phase`, `kind`,
and `operation`. Agent phases are `timed_out` or `malformed`; immutable-comment
phases are `before_call` or `after_call` with boundary `comment`. Prefer an
already observed exact operation. `next` is permitted only for a fresh isolated
PR and latches the first matching operation. The fault is one-shot per process;
remove the variable and restart after capturing evidence. Do not combine fault
phases in one run.

Qualify four fresh routes: lifecycle (head supersession, exact delivery UUID
redelivery, supervised restart, then unmerged closure), agent timeout and
malformed result, provider failure before call, and ambiguous provider outcome
after call. For every route preserve exact PR/head, delivery UUID where used,
latched operation, visible App effect URL, inbox disposition, Actions outcome,
terminal History counts, and duplicate assessment. Before and after deployment,
inspect PR20 read-only through existing runtime custody; allow only a normal
sweep and do not edit its History or provider state.

## 7. DS11 empty-target qualification setup

`qualification-setup` is a separately authorized, one-shot initializer for one
public, active, empty GitHub qualification target. It accepts no credential or
repository coordinate on the command line. Prepare three absolute paths beneath
an operator-owned mode `0700` custody directory:

- a mode `0600` credential file containing one PAT and no surrounding
  whitespace;
- a mode `0600` target file containing exactly
  `{"repository":"OWNER/REPOSITORY","account_id":123,"repository_id":456}`;
- a nonexistent spent-marker path whose parent is the mode `0700` custody
  directory.

Run only after exact setup authorization:

```sh
scripts/hamsterdan-demo qualification-setup \
  --credential-file /absolute/private/credential \
  --target-file /absolute/private/target.json \
  --spent-marker /absolute/private/setup-spent
```

The command consumes and removes both input files, strips ambient credential
authority, supplies the admitted PAT only to its bounded child environment,
and verifies authenticated account ID, exact repository ID/name, public active
empty state, and push permission. It then creates the deterministic two-commit
fixture and durably spends the marker before exactly one non-forced atomic push
of `main` and `hamsterdan/ds11-live-v4`. An attempted or uncertain push may run
one complete ref readback but can never push again. Exact readback must contain
only those two expected refs before read-only PR/current-CAS/stale-CAS setup
observations run. The command does not create a PR or perform a CAS mutation.

The JSON result contains only closed phases, categories, booleans, and cleanup
evidence. Keep the spent marker: deleting it discards the durable no-retry
fence. A failed or uncertain result is terminal for that target and credential;
do not repair, retry, force, or substitute another repository.

## Rotation, suspension, removal, and rollback

For key rotation, generate and deploy a second private key, restart and
validate, then delete the old key only after successful traffic. Rotate the
webhook secret as a coordinated GitHub/host change with a brief ingress stop;
GitHub supports one configured secret, so there is no silent overlap. Preserve
state with mode `0700` and back it up before replacement.

On installation suspension or removal, stop the host and verify no further
writes. Remove repository access in GitHub, then revoke/delete secrets and keys
when retiring the instance. GitHub App maintenance guidance:
<https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app-registration>
and installation suspension API semantics:
<https://docs.github.com/en/rest/apps/installations>.

Rollback is an **isolated handoff**: stop Hamsterdan, confirm its process is
down, restore the broker grammar expected by the known PAT service in a reviewed
one-file PR, and only then start that separately configured PAT service. Reverse
the sequence to return. Do not share state or credentials and never permit dual
writers. A rollback protects availability; it does not qualify Hamsterdan App
identity evidence.
