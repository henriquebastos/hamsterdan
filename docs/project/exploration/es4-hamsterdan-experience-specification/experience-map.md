# Experience map — behavior scenarios workbench

The topology-independent behavioral model. Each scenario follows:

```text
given durable situation S
when input X arrives
then observable effect / outcome Y
```

Scenarios describe **what a PR-owner or reviewer experiences**, not how
the net routes tokens. Seeded entries below are hypotheses derived from
[source-boundaries.md](source-boundaries.md); verify against boundary code
(never topology) before promoting. Blank rows are deliberate — this file
is a manual workbench.

## Lifecycle scenarios (seed hypotheses)

```text
given no durable instance for PR #N
when a pull_request "opened" webhook arrives
then an instance github:{inst}:{repo}:pr:N exists with Authority(epoch=1)
     and a dashboard comment is created

given an active instance at head H1
when a pull_request "synchronize" webhook moves head to H2
then authority advances (new epoch/head)
     and in-flight work fenced on H1 cannot publish
     and review/CI observation restarts against H2

given an active instance
when the PR is closed or merged
then the instance reaches Terminal and no further effects are published
```

## Review & findings scenarios (seed hypotheses)

```text
given an active instance with fresh authority at head H
when review evidence is needed (new head admitted)
then the review agent runs against H
     and findings are published inline where possible
     and the dashboard reflects ReviewState

given a review computed against head H1
when authority moved to H2 before publication
then the computed review is DISCARDED (not published, not merged forward)
     and a fresh review starts against H2        # simplicity over saved work
```

## CI / Actions scenarios (seed hypotheses)

```text
given an active instance at head H
when workflow_run / check_* webhooks arrive for exactly head H
then ActionsState updates and the dashboard reflects it

given required checks failed at head H
when repair is warranted (policy)
then the coding agent produces a patch
     and a commit is CAS-advanced to the PR branch with operation trailers
     — or, if the branch moved, the whole attempt is discarded and restarted
```

## Conversation scenarios (seed hypotheses)

```text
given an active instance
when a collaborator comments "@app <something>" on the PR
then the conversation agent classifies exactly one Intent (of 12 kinds)
     and the intent executes under authority
     and an immutable reply comment is posted
```

## Timer / sweep scenarios (seed hypotheses)

```text
given a reminder deferred until time T
when T matures (durable timer)
then a reminder comment is posted, once

given any durable instance
when the periodic sweep runs
then the instance reconciles against live GitHub state
     (repairs missed webhooks and restarts)
```

## Workbench — unmapped questions

| # | Question | Owner | Status |
| --- | --- | --- | --- |
| 1 | What exactly triggers a review: every head change, or policy-gated? | | open |
| 2 | Which intents mutate authority (epoch bump) vs act within it? | | open |
| 3 | When does readiness_publish fire — who decides "gates ready"? | | open |
| 4 | What does a base-branch move (base_head change) do to in-flight work? | | open |
| 5 | Dormant vs Terminal: what re-activates a Dormant instance? | | open |
| 6 | | | |
| 7 | | | |
