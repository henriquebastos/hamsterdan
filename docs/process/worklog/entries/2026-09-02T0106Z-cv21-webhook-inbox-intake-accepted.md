# CV21 Webhook Inbox and Intake accepted

The Navigator accepted CV21.DS2 after its earlier multi-ledger staging design
was replaced with the glossary-aligned Webhook Inbox and Intake flow. The HTTP
boundary now verifies the GitHub HMAC and saves exact raw evidence before JSON
parsing. A later host-owned `WebhookInboxWorker` normalizes the retained
delivery, classifies semantic equality, and offers only a durably authorized
novel observation to public `Engine.accept_delivery`.

Fresh CV21 state has three shared SQLite files regardless of PR count.
`hamsterdan.sqlite3` contains exactly `pr_workflows` and `webhook_inbox`;
`history.sqlite3` contains all Petrus workflow histories; and
`dispatch.sqlite3` contains Motus state. The earlier catalog, per-PR History,
readiness-ingress, manifest, grant, staging, fold, accepted-pointer, and host
completion stores were removed. Fresh roots are required; no migration or
compatibility reader was added.

`DeliveryId` owns transport redelivery. `ObservationKey` includes PR Identity
and the complete focused observation, so two deliveries for the same PR and
tips deduplicate before History while a later head becomes another source
occurrence. The Inbox's `recorded` result proves only History acceptance.
Petrus History owns unfinished and completed occurrences, and a later PR
authority calls public `Engine.complete_delivery` for the oldest unfinished
bridged occurrence without writing a host completion mark.

Process-loss tests cover History creation before the PR workflow row, Inbox
commit before HTTP acknowledgement, History acceptance before the Inbox becomes
`recorded`, and History completion before caller acknowledgement. The isolated
replacement gate passed strict Ruff, formatting, `ty`, seven ast-grep rules,
architecture checks, and 43 tests. The final `scripts/check full` run passed
quick, replacement, relay, demo-video, and distribution-build stages. Its
cumulative Python stage passed 1,178 tests and reproduced only the 14 inherited
`tests/unit/test_orb_setup.py` failures caused by unset `$USER` at
`.agents/setup:229`. Two unchanged generated V5 campaign cases that failed
during a preceding four-worker contention run each passed independently and in
the final full run.

CV21.DS2 is complete. CV21 remains active as the quality track, and DS3 through
DS12 remain planned. DS3 was not pulled by this acceptance.
