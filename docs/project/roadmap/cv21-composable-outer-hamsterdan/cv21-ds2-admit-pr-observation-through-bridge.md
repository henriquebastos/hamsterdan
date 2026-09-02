---
code: CV21.DS2
level: Delivery Story
status: Completed
status_reason: the Navigator accepted the glossary-aligned Webhook Inbox, semantic Intake, and History-owned completion behavior after final qualification
updated: 2026-09-02
related:
  - index.md
  - cv21-ds1-first-bridged-pr-lifecycle.md
  - contract-inheritance.md
  - ../../decisions/records/2026-09-01T1159Z-webhook-inbox-hands-novel-observations-to-history.md
---

# CV21.DS2 — Admit one PR observation through the bridge

## Outcome

Retain every bounded, correctly signed GitHub delivery in the
[Webhook Inbox](../../glossary/webhook-inbox.md) before parsing it. A later
host-owned `WebhookInboxWorker` normalizes that raw evidence, derives a focused
observation, rejects or deduplicates it before History, and offers only a novel
observation to the one-PR Petrus Engine. The HTTP request, Inbox processing,
History acceptance, and History-owned completion are separate recoverable
stages.

## Vertical path

```text
POST /github/webhooks
  -> bound headers/body -> verify HMAC -> save raw delivery -> HTTP 200

later WebhookInboxWorker turn
  -> parse/normalize -> bind configured route -> derive PR Identity
  -> project canonical HeadObservation + ObservationKey
  -> classify duplicate/rejected or authorize novel Intake
  -> Engine.accept_delivery -> mark Inbox row recorded

later PR authority turn
  -> inspect exact one-PR History -> recover oldest unfinished Intake
  -> Engine.complete_delivery -> current Net folds HeadSeen
```

The `WebhookInboxWorker` is a host application role, not a Motus Worker. DS2
executes no Activity, creates no Dispatch task, and runs no provider, agent, or
other external effect.

## Storage topology

Fresh CV21 state has exactly three shared SQLite files regardless of PR count:

| File | Owner and contents |
|---|---|
| `hamsterdan.sqlite3` | Hamsterdan application state: exactly `pr_workflows` and `webhook_inbox` |
| `history.sqlite3` | Petrus History for every workflow, partitioned by durable workflow identity |
| `dispatch.sqlite3` | Motus Dispatch state |

`pr_workflows` binds one immutable
[PR Identity](../../glossary/pr-identity.md) to its workflow identity and
generation. `webhook_inbox` retains raw delivery evidence, later normalized
evidence, semantic authorization, and the Intake outcome. There is no catalog,
per-PR database, readiness-ingress database, manifest, grant, staging table,
accepted pointer, fold table, or host completion receipt.

The separate application and History files are intentional. An Inbox turn may
hold one `BEGIN IMMEDIATE` application transaction while Petrus commits through
its own connection. Sharing that transaction domain would create self-blocking
instead of atomicity across the two owners.

## HTTP and transport identity

The HTTP boundary reads at most 1 MiB of body and a bounded protected-header
projection, validates content length/media type/delivery UUID/event/signature,
and verifies the HMAC over the exact body bytes. It does not parse JSON. A
success response is HTTP 200 with:

```json
{
  "inbox": "durable",
  "delivery_id": "<uuid>",
  "inbox_sequence": 1,
  "disposition": "received|duplicate|collision"
}
```

`DeliveryId` is transport identity:

- a first signed ID/body retains the exact raw body as `received`;
- the same ID/event/body returns `duplicate` and reuses the row and sequence;
- the same ID with changed evidence returns `collision`, preserves the original
  raw body, and records at most one changed-body digest.

A collision before semantic authorization rejects that pending delivery. A
collision after durable semantic authorization cannot revoke or rewrite the
already authorized original. Invalid signatures and malformed transport never
enter the Inbox. Validly signed malformed JSON and unsupported events do enter
the Inbox and are rejected only by the later worker.

## Normalization and semantic Intake

The later worker parses through the sole GitHubKit boundary and produces an
immutable provider snapshot plus provenance. It then projects one
source-neutral `HeadObservation` containing:

- exact PR Identity and current local generation 1;
- exact head and base repository/ref/SHA tips;
- open/closed lifecycle, draft, merged, and tri-state mergeability.

Provider update time, delivery ID, event, action, route, policy, and acquisition
order are excluded from canonical observation bytes and `ObservationKey`.
Therefore a later delivery with only a changed provider timestamp is a semantic
duplicate, while a changed head is a different observation for the same PR.
PR Identity is part of the observation: two PRs with identical tips remain
different observations.

Before calling Petrus, the Inbox transaction durably chooses exactly one owner
for a novel `ObservationKey`. A second delivery with the same key and bytes is
`duplicate`; a key/bytes mismatch is `rejected`. Unsupported lifecycle evidence
is rejected. An observation for an unknown PR remains pending so registration
can occur before a retry. The closed Intake outcomes are:

```text
NULL       pending or authorized but not yet acknowledged after History
recorded   the exact authorized observation exists in History
duplicate  another Inbox delivery already owns the same observation
rejected   transport collision, malformed/unsupported evidence, route refusal,
           or semantic-key collision
```

Durable authorization stores the exact normalized evidence, canonical
observation/key, policy revision, bridge identity, and History delivery
identity in the original Inbox row. It survives process loss and later
configuration changes. It is pre-History authority, not a second workflow
ledger.

## Bridge and History ownership

The first bridge family is
`workflow-bridge/head-seen-intake@4`. It accepts only generation 1, lifecycle
`open`, `draft=False`, and `merged=False`, then maps:

```text
source = on_head
head = observation.head.sha
base = observation.base.sha
mergeable = observation.mergeable is True
policy = authorized policy revision
strict_base = True
base_current = False
```

`HistoryDeliveryIdentity` v2 hashes bridge identity, observation key, and policy
revision. Only a novel, durably authorized observation calls public
`Engine.accept_delivery` without scope. Fresh acceptance appends adjacent
`ExternalEventDelivered` and `FiringBegun`; exact reoffer appends nothing and
recovers the same occurrence. Multiple different observations for one PR are
different source occurrences and may be unfinished together.

The Inbox's responsibility ends when that exact acceptance is proven and the
row becomes `recorded`. It does not track whether the retained Net later folded
the occurrence. A PR authority turn reads one bounded History page, selects the
oldest unfinished bridged occurrence, exact-reoffers it, and calls public
`Engine.complete_delivery` only for that carrier. Completion must produce the
exact `HeadSeen` at `life.heads` and the exact successful terminal. If all
observations are already finished, retry returns `already_completed` from
History alone. No host completion write follows.

## Recovery and bounds

The qualified process-loss scenarios are:

1. loss after Inbox commit but before HTTP response start: redelivery returns
   the same sequence as `duplicate`;
2. loss after History acceptance but before the application transaction marks
   `recorded`: the application write rolls back, History survives, exact reoffer
   recovers the occurrence, and the Inbox becomes `recorded` without append;
3. loss after History completion but before caller acknowledgement: fresh PR
   authority returns `already_completed` without append.

The application database retains at most 10,000 Inbox rows and 10,000 PR
workflows by default and enforces 131,072 SQLite pages. Canonical normalized
content is at most 16 KiB; a canonical observation is at most 8 KiB. Shared
History is bounded to 128 MiB, inspected through at most 4,096 records per
workflow, and reserves 1 MiB before a fresh acceptance or completion write.
Every durable reconstruction revalidates raw-body digest, canonical normalized
content, normalized-to-observation projection, key, delivery identity, PR
binding, bridge payload, acceptance pair, and successful terminal.

## Excludes

DS2 makes no provider exact read, currentness or ancestry claim, lifecycle
successor, Activity, Dispatch work item, Worker execution, provider effect,
agent call, broad Engine drain, new workflow fold, migration, or compatibility
reader. Fresh CV21 roots only are supported.

## Acceptance

- HTTP response requires only verified durable raw Inbox retention and never
  invokes normalization, readiness, History, Dispatch, or a Worker;
- delivery identity handles transport redelivery while observation equality
  handles semantic deduplication before History;
- one PR may contribute many distinct observations but one semantic observation
  reaches History only once;
- the exact three-file/two-application-table topology remains invariant as PRs
  grow;
- History is the sole owner of unfinished and completed workflow occurrences;
- all three process-loss boundaries reconstruct without duplicate History work;
  and
- architecture, concurrency, corruption, and finite-resource checks pass under
  the isolated replacement gate.

The Navigator accepted the glossary-aligned implementation and its Experience
Report on 2026-09-02. CV21.DS2 is complete. DS3 remains planned and unpulled.
