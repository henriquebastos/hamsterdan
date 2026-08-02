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
multiple organizations. Hamsterdan intentionally runs one installation account
per deployment today; another organization can either operate its own private
App instance or wait for a future multi-account/public deployment contract.

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
review**, **Pull request review comment**, and **Workflow run**. Metadata read is
implicit. The live provider denied PR-thread comment creation to an installation
token carrying `issues=write` and `pull_requests=read`; its accepted-permissions
response required `pull_requests=write`. Host code still exposes no merge,
formal-review, or PR-edit operation, and every admitted comment effect retains
its current-head/operation fence. GitHub also sends App lifecycle **Ping**, **Installation**, and
**Installation repositories** deliveries; they are verified and applied but do
not appear in the selectable startup event set. These values are
startup-validated against the provider. No Checks, statuses, formal-review
writes, Actions writes, Workflows writes, merge, bypass, organization, or user
permission belongs in this first App. Permission
semantics: <https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps>;
webhook events: <https://docs.github.com/en/webhooks/webhook-events-and-payloads>.

Record the App ID, client ID, and slug shown by GitHub. Generate one private key
from the App settings. Generate a high-entropy webhook secret locally without
putting it in shell history, for example:

```sh
install -d -m 700 .amp/runtime
install -m 600 ~/Downloads/hamsterdan.private-key.pem .amp/runtime/github-app.pem
python - <<'PY'
import secrets
from pathlib import Path
p = Path('.amp/runtime/webhook-secret')
p.write_text(secrets.token_urlsafe(48) + '\n')
p.chmod(0o600)
PY
```

Paste the webhook-secret file's value into GitHub's App webhook secret field
without logging it. Never commit either file. GitHub key guidance:
<https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps>;
webhook security: <https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries>.

## 2. Configure and install

Create mode `0600` `.amp/runtime/hamsterdan.env`. It contains IDs and paths,
not secret values:

```sh
HAMSTERDAN_GITHUB_APP_ID=<app-id>
HAMSTERDAN_GITHUB_APP_SLUG=hamster-dan
HAMSTERDAN_GITHUB_CLIENT_ID=<client-id>
HAMSTERDAN_GITHUB_ACCOUNT_ID=108842540
HAMSTERDAN_GITHUB_ACCOUNT_LOGIN=HBNetwork
HAMSTERDAN_ALLOWED_REPOSITORIES=1316665126:HBNetwork/demo-pr-readiness
HAMSTERDAN_STATE_PATH=.amp/runtime/state
HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE=.amp/runtime/github-app.pem
HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE=.amp/runtime/webhook-secret
```

GitHub assigned this registration the slug `hamster-dan`, so its bot login is
`hamster-dan[bot]` and its exact public mention is `@hamster-dan`. Trusted PR
participants interact through natural comments beginning with that mention,
for example `@hamster-dan explain the current blockers`. The lookalike
`@hamsterdan` is not a GitHub alias and is intentionally not accepted.

Run `chmod 600 .amp/runtime/hamsterdan.env`. From the App settings choose
**Install App**, select HBNetwork, choose **Only select repositories**, and
select only `demo-pr-readiness`. Installation docs:
<https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app>.

## 3. Validate, serve, and prove ingress

Source the ID/path file only into the trusted host process, then validate the
App registration and selected-repository installation:

```sh
set -a; . .amp/runtime/hamsterdan.env; set +a
uv run --frozen python -m hamsterdan.host validate
amp orb services ensure
```

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

It changes only `.github/workflows/rerun-broker.yml`, including the event prefix,
full-match regex, and human-association gate. The replacement accepts only an
exact `hamster-dan[bot]` actor of type `Bot`. **Merge that PR only after** host validation,
healthy webhook ingress, selected-repository routing, and App installation are
all confirmed. Never count an old marker as Hamsterdan evidence. Never run the
legacy PAT service and Hamsterdan as concurrent writers.

After cutover, create controlled PRs with the current human operator's `gh` and
git credentials (credentials remain outside agent territory):

```sh
gh auth status
gh auth setup-git  # one-time human operator workstation setup
scripts/hamsterdan-demo create --scenario clean-green
scripts/hamsterdan-demo create --scenario first-attempt-flake
scripts/hamsterdan-demo inspect --pr <number>
```

Creation branches from fresh `origin/main`, changes only the fixture's closed
schema control, validates it, and creates—but never merges—the PR. Inspection
requires an App-owned dashboard, readiness advisory, no legacy marker, exact
workflow heads, and App ownership for every recognized comment. It reports only
recognized marker identities/IDs/URLs, bounded workflow/job facts, and
attribution. GitHub's App bot may be the **authenticated pusher** exposed in
REST `author`/`committer` user objects, while the nested Git commit `author` and
`committer` are explicit commit metadata; neither proves the other. See
<https://docs.github.com/en/rest/commits/commits#get-a-commit> and
<https://docs.github.com/en/rest/git/commits#create-a-commit>.

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
update or conflict-resolution request. Each mutation requires the exact pending
digest in a second human confirmation. Record the operation identity, old and
new head, App-authored commit attribution, successful exact-head checks, and
the final authority inspection. Hamsterdan must use a credential-free agent
checkout and host-owned compare-and-swap publication; never update either branch
manually, force-push, bypass protection, or edit History.

For every transition preserve PR and visible effect URLs, exact SHAs, bounded
inspection JSON, Actions run IDs/conclusions, History projection, unresolved
Activity count, and duplicate-effect assessment. Keep PR14/15 and PR23-28
untouched. PR20 retry churn remains CV3.DS3 debt and is not acceptance evidence.

For an exhausted delivery, inspect only its bounded identifiers/error class and
then explicitly requeue it after correcting the provider or configuration
failure:

```sh
set -a; . .amp/runtime/hamsterdan.env; set +a
uv run --frozen python -m hamsterdan.host inbox
uv run --frozen python -m hamsterdan.host requeue --delivery <canonical-delivery-uuid>
```

Requeue resets the retry schedule for the already verified, sanitized durable
observation; it does not bypass signature verification, duplicate custody,
repository admission, current-authority fencing, or effect lookup.

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
