---
code: CV2.DS1
level: Delivery Story
status: In Progress
status_reason: Experience accepted and implementation reviewed; source CI and live App acceptance remain
updated: 2026-08-01
related:
  - docs/project/decisions/records/2026-08-01T0203Z-hamsterdan-is-a-standalone-petrus-application.md
  - docs/project/decisions/records/2026-08-01T0335Z-githubkit-and-a-durable-relay-own-provider-ingress.md
---

# CV2.DS1 — Mention-first readiness conversation

## In scope

- Exact configured App-mention admission for trusted human PR participants.
- Mention stripping before credential-free comment prose reaches the agent.
- Natural readiness explanations grounded in the current durable dashboard,
  findings, gates, and exact PR generation.
- Internal typed host intents for bounded workflow controls.
- Two-comment conversational mutation confirmation bound to the pending intent
  digest, head, base, and policy.
- App-bot reply attribution, immutable operation markers, lookup-first recovery,
  and bounded publication retries.

## Acceptance behavior

Given an authorized owner, member, or collaborator comments on an active pull
request beginning with the exact configured App mention, such as
`@hamster-dan explain the current blockers`
When Hamsterdan handles the comment
Then the mention is removed before the natural prose reaches the agent
And the agent receives credential-free PR identity and current durable control
state
And exactly one correlated reply is published as `hamster-dan[bot]`
And the reply explains observed readiness without inventing workflow state.

Given an unaddressed comment, a lookalike mention, a bot-authored comment, or a
`/hamsterdan` comment
When webhook admission runs
Then no conversation agent or conversation effect runs.

Given an authorized human naturally requests a repository mutation
When the agent emits the matching typed host intent
Then the exact request is staged but not executed
And a second explicitly confirming mention can authorize execution only while
the pending kind, arguments digest, head, base, and policy still match.

Given duplicate delivery, restart, or uncertain publication outcome
When the same operation resumes
Then immutable lookup-first recovery prevents duplicate replies and bot-authored
comments cannot trigger a self-loop.

## Out of scope

- Public or compatibility behavior for slash commands.
- A formal or generalized tool plane.
- Changes to dashboard ownership, publication retry topology, Petrus,
  AgentRunner, Motus Dispatch, or execution environments.
- GitHub App multi-tenancy or public distribution.

## Acceptance evidence

Local qualification passes 183 Python tests with one opt-in real-provider skip,
nine Bun relay tests, Ruff, formatting, ty, wheel/sdist build, and
`git diff --check`. Tests prove exact mention stripping and trusted-human
admission, slash/lookalike/bot rejection, current dashboard delivery, one raw
agent intent, host-verified digest confirmation, unchanged pending state after
false confirmation, exact second-comment mutation authorization, and preserved
bounded publication recovery.

Private-source CI and live acceptance remain. Live acceptance will use
[HBNetwork/demo-pr-readiness#14](https://github.com/HBNetwork/demo-pr-readiness/pull/14)
without replacing its durable dashboard or runtime history.
