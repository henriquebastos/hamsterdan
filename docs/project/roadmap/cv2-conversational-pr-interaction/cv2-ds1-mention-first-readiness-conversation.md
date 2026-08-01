---
code: CV2.DS1
level: Delivery Story
status: Completed
status_reason: Exact mention conversation and corrected current-gate reply are accepted live on PR 14
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

Local qualification passes 184 Python tests with one opt-in real-provider skip,
nine Bun relay tests, Ruff, formatting, ty, wheel/sdist build, and
`git diff --check`. Tests prove exact mention stripping and trusted-human
admission, slash/lookalike/bot rejection, current dashboard delivery, one raw
agent intent, host-verified digest confirmation, unchanged pending state after
false confirmation, exact second-comment mutation authorization, and preserved
bounded publication recovery.

The first live request proved webhook custody, exact App reply attribution,
single publication, self-loop rejection, and terminal failure-free recovery,
but its free-form answer contradicted the ready dashboard by treating a latched
rerun flag as current work. The corrected request now includes host-derived
authoritative gates and routes blocker/status questions through deterministic
current-gate rendering. A credential-free real Amp probe against that exact
conflicting shape selected the status intent. Corrective commit
`a99ffff238b915f1490570806d6e07147e0f7396` passed private-source CI run
`30708149931` and was deployed without replacing runtime custody or History.

Final live acceptance on
[HBNetwork/demo-pr-readiness#14](https://github.com/HBNetwork/demo-pr-readiness/pull/14)
used exact human request
[5152324682](https://github.com/HBNetwork/demo-pr-readiness/pull/14#issuecomment-5152324682).
Hamsterdan published exactly one correlated App reply
[5152326755](https://github.com/HBNetwork/demo-pr-readiness/pull/14#issuecomment-5152326755):
“Readiness is ready; no current blockers are observed.” Operation
`conversation-reply:8448833ff45dab76d35aed429cbfa5f8ce91d7a7324fe96d2be56896bfaa1108`
is fenced to the unchanged PR head. The dashboard remained current and ready;
History advanced from 550 to 642 records, inbox custody advanced from 87 to 95
terminal deliveries with zero pending/failures, and exactly one bot reply was
created. The bot reply delivery was rejected from conversation admission, so no
self-loop or duplicate publication occurred. Prior comments, SQLite state, and
credential-free logs remained intact.
