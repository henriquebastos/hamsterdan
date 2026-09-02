---
status: Decided
raised: 2026-08-28
decided: 2026-08-28
recorded: 2026-08-28T2037Z
deciders:
  - Henrique (Navigator)
related:
  - CV21
  - CV21.DS3
  - CV21.DS4
  - CV21.DS5
  - CV21.DS6
  - CV21.DS7
  - CV21.DS9
  - CV21.DS11
  - CV21.DS12
  - 2026-08-05T1254Z-agenticus-routing-is-explicit-host-owned-and-fail-closed.md
  - 2026-08-11T2359Z-agenticus-pi-is-the-only-agent-execution-route.md
---

# CV21 Activities run in separately supervised Motus Workers

## Question

Should the CV21 Hamsterdan authority process execute or synchronously pump
Activities, should CV21 require remote execution infrastructure immediately,
or should durable Motus Dispatch separate one-PR Engine advancement from
Worker execution while allowing an initially local process topology?

For example, after PR 7 requests a dashboard publication, the process advancing
that PR must be able to stop while another process claims the exact Motus
Attempt, performs lookup-first GitHub publication, reports an operational
terminal, and leaves a later reconstructed Engine to record the canonical
terminal in Impetus History.

## Decision

CV21 uses separately supervised Motus Worker process roles over durable
Dispatch. The Hamsterdan authority role advances one-PR Engines and never
creates, drives, or waits inside a Worker Activity. An external deployment
supervisor owns Worker launch, restart, scaling, placement, and termination.
CV21 qualifies that topology without deploying it.

`host/composition.py` remains the sole concrete composition root, but it is not
a single-process object graph. Each executable role invokes a role-specific
constructor. Worker composition binds Motus Worker/WorkerDispatch to the
Hamsterdan Activity registry, queue routing, concrete provider or agent
capabilities, and process-local configuration. Readiness owns typed Activity
adaptation and one-PR Engine integration; it does not own Worker construction,
claims, leases, retries, execution, or operational terminal reporting.

The first real execution profile uses a separate same-host Worker over durable
Local Dispatch. SQLite and same-host placement are infrastructure choices, not
workflow semantics. A later Absurd/PostgreSQL or ZeroMQ profile may replace
that infrastructure without changing the Net, Activity declarations,
readiness boundary, or terminal path.

GitHub and agent Activities run in separate Worker roles. Only the GitHub role
receives provider mutation credentials. The agent role invokes the
credential-free Hamsterdan agent adapter and Agenticus/Pi machinery without
GitHub credentials.

The story sequence introduces the boundary progressively:

- DS1 and DS2 execute no Activity and construct no Worker;
- DS3 records one canonical request and durable pending Dispatch task, with
  scripted terminal-return evidence but no Worker or provider implementation;
- DS4 qualifies the first separate GitHub Worker process; and
- DS5 qualifies the separate agent Worker process and Agenticus/Pi route.

DS6, DS7, and DS9 reuse those role boundaries for mutation, rerun/repair, and
protected effects rather than creating new execution paths. DS12 qualifies
their independent restart, shared-Instance service, and credential isolation.

DS11 schedules fairly across PR Engines and discovery turns independently of
Motus queue, Attempt, and Worker concurrency. One Engine per durable PR does
not imply one process or Worker per PR; shared Worker roles serve many
Instances through durable Instance identity and Activity routing.

HTTP ingress, the host-owned Webhook Inbox Worker, and PR authority scheduling
remain distinct logical roles. The HTTP request ends after verified raw
evidence reaches the durable Webhook Inbox. The Webhook Inbox Worker parses,
normalizes, and offers novel observations to History; it is not a Motus Worker
and executes no Activity. This decision does not rule whether those host roles
share an OS process.

## Options Considered

- **Embed or synchronously pump Workers in the authority process.** Rejected
  because it repeats the current V5 coupling between PR scheduling and Motus
  execution, mixes failure and resource lifetimes, and makes web/process
  placement an application invariant.
- **Separately supervised Motus Workers over durable Dispatch — chosen.** It
  preserves Impetus/Motus ownership, allows independent scaling and failure,
  and starts with a bounded same-host topology without changing workflow
  semantics.
- **Require remote Worker infrastructure immediately.** Rejected because
  PostgreSQL/Absurd or ZeroMQ deployment is unnecessary to prove the process
  boundary and would add infrastructure scope before the first real Activity.

## Consequences

- Impetus History remains canonical for Activity request, occurrence, and
  terminal facts. A Worker reports only an operational terminal through Motus
  Dispatch; a later Engine turn accepts it into canonical History.
- Motus Dispatch owns task, Attempt, claim, lease, heartbeat, retry, and
  operational terminal custody. Motus Worker owns claim/execute/report
  behavior. Hamsterdan owns the typed application implementation and external
  idempotency or lookup-first operation protocol.
- Worker failures do not terminate HTTP ingress or the authority scheduler;
  authority restart does not erase Worker custody or a completed Dispatch
  terminal.
- Agenticus/Pi may create a bounded operation-local child process inside an
  agent Attempt. That child is Agenticus-owned execution machinery, not another
  long-lived Worker role or recovery authority.
- Logs may be separate per role and correlate through workflow identity,
  occurrence, operation, Attempt, and Worker generation. Logs never substitute for
  durable custody.
- CV21 remains non-selectable and undeployed. This ruling authorizes no current
  runtime change, Worker launch, provider effect, or infrastructure action.

## Review Trigger

Return to the Navigator if Local Dispatch cannot qualify a real separate
process without coupling Worker construction to readiness, if a provider
requires canonical History writes from a Worker, if agent execution cannot
remain credential-isolated, or if ingress/authority process placement must be
decided to complete an affected tracer.
