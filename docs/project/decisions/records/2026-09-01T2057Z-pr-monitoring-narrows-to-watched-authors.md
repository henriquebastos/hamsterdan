---
status: Decided
raised: 2026-09-01
decided: 2026-09-01
recorded: 2026-09-01T2057Z
deciders:
  - Henrique (Navigator)
related:
  - 2026-08-25T1042Z-operator-installation-portfolios-are-restart-applied-configuration.md
  - 2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
  - 2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
---

# PR monitoring narrows to watched authors

## Decision

Hamsterdan watches every pull request in a watchlisted repository by
default. The operator may narrow monitoring to watched authors with
`HAMSTERDAN_WATCH_AUTHORS`: a comma-separated list of GitHub logins,
compared casefolded, validated loudly at startup. Unset or empty keeps
today's watch-everyone behavior.

The watch decision executes at Instance activation against the
authoritative pull request snapshot's author, never against webhook
payloads. An unwatched PR starts no journey and receives no comments;
its deliveries acknowledge terminally with reason `author not watched`,
alongside the existing `inactive route` and `comment not addressed`
dispositions. Because a PR's author is immutable, the verdict persists
per subject so later deliveries for an unwatched PR dispose without a
provider read.

An admitted mention — `@app-slug` from an OWNER, MEMBER, or
COLLABORATOR, through the existing conversation admission — on an
unwatched PR overrides the narrowing and opts that one PR into
monitoring for its lifetime.

## Rationale

The driving scenario is adopting Hamsterdan on a large shared
repository without disturbing the whole team: the operator narrows to
their own login, and monitoring stays invisible to everyone else. The
mention override turns that narrowing into invitation-based adoption —
any collaborator can summon monitoring onto their own PR without an
operator config change.

Activation is the only sound decision point. Webhook Observations carry
the PR author for `pull_request` events only; `workflow_run`,
`check_run`, and comment events do not, so a payload-time filter would
leak journeys through non-`pull_request` events. Every event for a
subject funnels through activation, and the journey already reads the
snapshot there.

The terminal-disposition pattern keeps the narrowing honest: an ignored
PR is fully diagnosable from the webhook inbox reason without any
team-visible output, which is the point of the feature.

The retired `HAMSTERDAN_ALLOWED_REPOSITORIES` precedent was considered:
repository scope outgrew an env var and moved to the installations
file. Author scope is deployment-wide operator policy, so one env var
is the honest minimum now. If per-repository author rules are ever
needed, they belong in the installations file and supersede this
record.

## Consequences

- Existing deployments are untouched; the variable is absent everywhere
  today.
- Watched-author changes are restart-applied configuration, like
  installation portfolios. A newly watched author's PRs join on their
  next delivery or recovery sweep.
- Configured-repository recovery honors the same narrowing: discovery
  must not resurrect journeys the filter excludes.
- A mention opt-in is per PR, not per author, and persists for that
  PR's lifetime.
