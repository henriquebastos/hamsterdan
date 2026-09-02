---
status: Decided
raised: 2026-09-01
decided: 2026-09-01
recorded: 2026-09-01T1159Z
deciders:
  - Henrique (Navigator)
supersedes:
  - 2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
related:
  - CV21.DS2
  - ../../glossary/webhook-inbox.md
  - ../../glossary/intake.md
---

# Webhook Inbox hands novel observations to History

## Decision

Webhook transport, observation equality, and workflow completion have three
different owners.

The HTTP boundary bounds exact headers/body, verifies the GitHub HMAC, and
stores every valid signed delivery's raw body in the Webhook Inbox before JSON
parsing. It then returns HTTP 200. `DeliveryId` handles transport redelivery:
same ID and evidence is a duplicate; changed evidence is a collision that never
overwrites the original.

A later host-owned `WebhookInboxWorker` parses and normalizes the retained raw
evidence. It is an application role, not a Motus Worker. The worker projects a
source-neutral observation, computes its complete semantic key, and decides
novel, duplicate, or rejected before Petrus. It must not deduplicate by PR
Identity alone because one PR produces many observations over time.

For one novel observation, the Inbox durably stores pre-History authorization,
then calls public `Engine.accept_delivery`. The Inbox outcome is
`NULL|recorded|duplicate|rejected`; `recorded` means only that the exact
observation exists in History. It does not mean the workflow folded it.

After acceptance, responsibility belongs to Petrus History. A later PR
authority derives unfinished occurrences only from History and calls public
`Engine.complete_delivery` for the selected exact carrier. Hamsterdan stores no
completion receipt or second fold ledger.

Fresh CV21 state uses exactly three shared SQLite files independent of PR
count: `hamsterdan.sqlite3` with only `pr_workflows` and `webhook_inbox`, shared
`history.sqlite3` for all Petrus workflow identities, and shared
`dispatch.sqlite3` for Motus. There are no per-PR database files, catalog,
readiness-ingress database, manifests, grants, staging decisions, or completion
tables. Fresh roots only are supported; no migration or compatibility reader
is added.

## Concrete scenario

GitHub delivery A for PR 7 is signed and retained raw, so HTTP returns 200. The
later worker normalizes head SHA `aaa`, sees no prior semantic owner, stores its
authorization, and accepts occurrence 1 in History. Delivery B for PR 7 with
only a changed provider timestamp computes the same observation and becomes
`duplicate`. Delivery C for PR 7 with head SHA `ccc` is a new observation and
can become occurrence 2. If the process dies after occurrence 1 enters History
but before A becomes `recorded`, retry exact-reoffers A, recovers occurrence 1,
and marks A `recorded` without another History append. Completion of occurrences
1 and 2 is reconstructed from History only.

## Consequences

- Signature verification remains synchronous; parsing, provider normalization,
  route binding, semantic deduplication, and History acceptance are later Inbox
  work.
- Valid signed malformed JSON remains durable evidence and later becomes a
  rejected Intake. Invalid signatures never enter the Inbox.
- Observation equality includes PR Identity and complete focused semantics but
  excludes provider timestamp, provenance, delivery identity, route, policy,
  and receipt order.
- Durable authorization prevents a concurrent duplicate from reaching History
  while the first owner's History result is uncertain.
- A changed policy configuration after authorization cannot reinterpret the
  pending observation; the exact persisted authorization is retried.
- Application and History use separate SQLite transaction domains so an
  application writer can call Petrus without blocking itself. Process death
  rolls back the application transaction while preserving a committed History
  acceptance.
- History is the sole workflow acceptance/fold ledger. The Inbox keeps one
  handoff acknowledgement because it owns queue progress; no later completion
  mark is required.
- The previous manifest/grant/staging/completion design and its task worklogs
  remain historical evidence, not current CV21 architecture.

## Review trigger

Return to the Navigator if a later source cannot produce a stable semantic
observation before History, if shared History cannot preserve bounded per-
workflow authority, or if operational Inbox scheduling requires Motus Activity
semantics rather than host application scheduling.
