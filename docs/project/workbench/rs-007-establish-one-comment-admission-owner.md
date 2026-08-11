---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-007 — Establish one comment-admission owner

## Existing field refined

RS-005 admitted GitHub comments in `HostService`, then passed raw normalized
fields to `PrReadinessApplication`, which independently repeated bot, actor
type, association, and exact-mention policy. The two copies already had
different configuration shapes: the service used a fixed trusted set while the
application accepted a configurable set. The second check could drift but did
not defend against a compromised composition root.

## Accepted security boundary

The Navigator selected one authoritative provider-ingress policy. Raw signed
GitHub observations remain canonical in durable webhook custody. When an
observation becomes eligible for work, `github_app.webhooks.admit_conversation`
either rejects it or creates one strict neutral value:

```python
class AdmittedConversation(WorkflowModel):
    delivery_id: str
    comment_id: int
    actor_id: int
    actor_login: str
    association: str
    text: str  # exact mention removed
```

The policy owns event/action, bot exclusion, exact `User` type, trusted
association, case-insensitive exact configured mention, whitespace
normalization, and raw-type rejection. `AdmittedConversation` is strict,
frozen, extra-forbidden, and carries no provider policy fields or raw mention
text.

## Delivered call stack

```text
authenticated raw Observation in WebhookCustody
  -> admit_conversation(item, app_slug, bot_login)
       -> None: terminal custody, no application construction
       -> AdmittedConversation: carry once with selected observation
  -> HostService._activate_instance under the PR lock
  -> PrReadinessApplication.activate(trigger, conversation)
       -> reconcile provider truth exactly once
       -> bind current epoch/head
       -> deliver ConversationObservation
```

Retries reconstruct admission from raw durable custody, while the stable
`github-delivery:<delivery_id>` History identity preserves logical delivery.
Route revalidation, pre/post settlement, runnable posture, and acknowledgment
ordering are unchanged.

## Validation and review

Focused contract, GitHub App, application, service, payload, and architecture
evidence passed 162 tests. Coverage includes bare and mixed-case mentions,
outer/multiple whitespace, lookalikes, tab boundaries, embedded mentions,
non-comment spoofing, edited comments, bot/non-user/untrusted actors, strict
contract fields, stripped text carriage, one reconciliation, and terminal
handling of authenticated malformed IDs without retry loops.

After integration with current `main`, the full Python suite passed 574 tests
with one external route deselected. Static,
format, type, package, and relay gates passed. Independent adversarial review
returned `APPROVE` after raw-type admission became total and fail-closed.

## Consequences

- Provider trust policy has one implementation and one test matrix.
- The application no longer knows actor types, configured mentions, or trusted
  association policy; it receives an admitted business command.
- Host application/service code lost 45 net lines. The neutral contract and
  fail-closed provider validation make the overall production diff seven net
  lines larger, exchanging duplication for one explicit checked boundary.
- No custody schema, lifecycle, Activity, authority-fence, scheduler, Net, or
  Petrus behavior changed. The Net remains 46 places, 69 transitions, 309 arcs,
  and 17 retirements.
