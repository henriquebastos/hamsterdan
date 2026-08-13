# AX0 — Boundary inventory and topology-independent experience map

## Question

Can the Hamsterdan experience be specified from boundary evidence alone —
product docs, contracts, and host/github_app code — without reading the
net topology? What is verifiable, what is corrected, and what turns out
to live only inside the net?

## Method

Two read-only passes, topology blacked out:

1. **Product-intent pass** — `docs/project/briefing.md`,
   `docs/product/principles.md`, `README.md`, and the five decision
   records most relevant to observable behavior.
2. **Boundary-code pass** — `host/`, `github_app/`, `contracts/`,
   `agents/`, `readiness/payloads.py`. `readiness/net/` never opened.

Every seed scenario from [experience-map.md](../experience-map.md) was
confirmed, corrected, or marked **NET-DECIDED** (the boundary provides
mechanics but the decision is made inside the net). The promoted map now
lives in [experience-map.md](../experience-map.md); this record keeps the
method, corrections, and findings.

## Finding 1 — the boundary owns safety; the net owns decisions

The sharpest result of the blackout. Boundary code fully specifies *how*
effects happen safely; it almost never specifies *when* work is chosen:

| Experience decision | Boundary evidence | Locus |
| --- | --- | --- |
| When a review is requested | `ReviewRequest` shape + activity only (`contracts/readiness.py:311-323`) | **NET-DECIDED** |
| When `readiness_publish` fires | gate predicate exists at boundary (`contracts/readiness.py:763-797`) but nothing emits the command | **NET-DECIDED** |
| Whether discarded H1 work restarts against H2 | fencing confirmed; restart decision absent | **NET-DECIDED** |
| Rerun vs repair vs wait on failed CI | both activities exist; selection absent | **NET-DECIDED** |
| When the dashboard republishes | currency digest defined (`contracts/readiness.py:675-714`); trigger absent | **NET-DECIDED** |
| What each intent kind *does* | classification + reply mechanics confirmed; workflow action absent | **NET-DECIDED** |
| How effects execute safely | fencing, CAS, lookup-first, operation identity — fully specified | **BOUNDARY** |

And the product docs are silent on the same points (29 recorded gaps;
see Finding 4). Consequence: **the decision layer of Hamsterdan exists
only as topology** — there is no independent specification of when work
happens. This is direct evidence for the motivating hunch: whatever
complexity `topology.py` carries, nobody can currently check it against
an external contract. AX1's subnet contracts must therefore re-derive
the decision layer from product intent, not transcribe it.

## Finding 2 — corrections to the seed scenarios

```text
SEED  : synchronize H1→H2 → "authority advances (new epoch/head)"
VERIFIED: epoch advances ONLY on head change or dormant resume
          (host/application.py:312-321). A base-only move does NOT
          bump epoch and does NOT start a generation — it emits a
          same-epoch verified_admission (host/application.py:173-204),
          while base_head still participates in the effect fence
          (host/runtime.py:234-247). Base moves are fence-relevant
          but not generation-relevant.
```

```text
SEED  : PR closed/merged → "Terminal and no further effects"
VERIFIED: GenerationStop(merged|closed) + commit confirmed
          (host/application.py:130-138, 360-394). "No further effects"
          is too strong: published effects remain, late terminals are
          still collected/quarantined, bookkeeping continues. Correct
          claim: no NEW provider effect can pass the fence.
```

```text
SEED  : intents "execute under authority"
VERIFIED: 3 of 12 kinds are mutations (change, update_base,
          resolve_conflict) — blocking repository mutations
          (host/activities.py:630-668). mutation=True does NOT imply
          an epoch bump. `status` is normalized to `reply`
          (host/activities.py:297-301). Zero-or-multiple classified
          intents → safe immutable "no workflow change" reply.
```

```text
SEED  : (absent) — draft PRs unmodeled
VERIFIED: draft → GenerationStop to Dormant; open non-draft later →
          resume with relation="resumed", epoch = last_epoch + 1
          (host/application.py:139-154, 318-330). Terminal has no
          boundary reactivation route.
```

## Finding 3 — boundary concepts the scaffold missed

Discovered during verification; each must appear in AX1 contracts:

- **Provisional authority.** A successful `change`/`repair` returns a
  `provisional_head`; while mutation state is provisional all further
  effects are fenced and readiness waits for verified head admission
  (`contracts/readiness.py:157-166`, `host/runtime.py:224-250`).
- **Generation relations.** Starts are `new | resumed | confirmed |
  superseded`; only `confirmed` (provisional head verified) preserves
  repair lineage (`host/application.py:328-353`).
- **Staged, repairable generation boundaries.** Start/stop token, scope
  operation, and commit are separate events; startup repairs interrupted
  boundaries before ordinary reconciliation (`host/application.py:354-358`,
  `396-435`).
- **Quarantine doctrine.** Proven-stale ingress is acknowledged and
  dropped; uncertain-generation ingress is quarantined, never
  reinterpreted as current (lifecycle decision record).
- **Failure classification at the boundary.** GitHub/deadline capability
  failures stay recoverable; unknown terminal failures become explicit
  nonrecoverable faults requiring an exact `recover_publication` intent
  (`host/runtime.py:115-149`; briefing `:73-78`).
- **Two publication species.** Mutable singleton (dashboard) vs
  immutable operation publications (replies, findings, readiness,
  reminders) (`github_app/effects.py:89-208`).

## Finding 4 — documentation gap inventory

The product-intent pass produced 29 open questions where docs promise
nothing (intent-by-intent semantics, review trigger policy, readiness
gate ownership, reminder cadence, dormancy rules…). Curated survivors are
now the open-questions table in [experience-map.md](../experience-map.md);
the full list is preserved below for future doc work.

<details>
<summary>All 29 documentation gaps (verbatim from the product-intent pass)</summary>

1. Which exact PR events admit an instance (opened, reopened, draft
   conversion, first synchronize, periodic discovery)?
2. Does opening a draft PR create active work, a Dormant instance, or
   no instance?
3. What happens on closed-without-merge vs merged?
4. Does reopening a closed PR resume an old instance or create a new
   generation?
5. Does every head SHA change trigger review, or can policy
   suppress/reuse review?
6. Which authority facts cause a business epoch bump vs a lifecycle
   generation change?
7. Do change/update_base/resolve_conflict mutate authority immediately,
   provisionally, or only after the resulting head is observed?
8. Exact semantics of each non-mutation intent?
9. What durable objects do acknowledge/dismiss/defer/reassign act upon?
10. defer vs snooze distinction; does either suppress readiness?
11. What ends a snooze?
12. Who can issue each intent; what establishes authorization?
13. When/where are findings published; edited, replaced, or appended?
14. What happens to published findings after a new head/base/policy?
15. Is CI rerun automatic, policy-driven, or conversation-authorized?
16. When is code repair chosen over rerun?
17. What gates define "ready"; which component decides publication?
18. Is readiness publication a check, status, comment, or review?
19. What makes a dashboard stale beyond digest inequality; when is
    refresh scheduled?
20. Reminder cadence, audience, eligibility, escalation, stop conditions?
21. Does every base move close the generation, or can work be
    revalidated?
22. Does a policy change discard in-flight work; how is policy versioned?
23. Are completed effects from superseded authority retained,
    compensated, hidden, or reflected?
24. Definitions and transitions of Dormant and Terminal?
25. What reactivates Dormant?
26. Is Terminal permanent; can recover_publication act on it?
27. User-visible outcome of unauthorized/unsupported intents?
28. How are duplicate conversational intents deduplicated?
29. Exact conditions classifying publication failure as recoverable vs
    nonrecoverable?

</details>

## Answers to the workbench questions

| # | Question | Answer | Evidence |
| --- | --- | --- | --- |
| 1 | What triggers a review? | **NET-DECIDED**; docs silent | request shape only at boundary |
| 2 | Which intents mutate authority? | 3 mutation kinds; none proven to bump epoch — epoch moves only on head change/resume | `host/activities.py:630-668`, `host/application.py:312-321` |
| 3 | When does readiness fire? | gate predicate at boundary; emission **NET-DECIDED** | `contracts/readiness.py:763-797` |
| 4 | Base move effect? | fence-relevant, not generation-relevant; same-epoch `verified_admission` | `host/application.py:168-204` |
| 5 | Dormant reactivation? | draft→Dormant; non-draft resume, epoch+1; Terminal has no route back | `host/application.py:133-154`, `318-330` |

## Conclusion

**Promising; continue.** The blackout method works: the boundary yields a
verifiable safety specification and precise corrections, and it cleanly
isolates what only the net knows. The decision layer is unspecified
outside topology — so AX1 should draft subnet contracts whose *decision
rules come from product intent* (with the gap list as the honest
uncertainty), then AX5 can compare those against what topology actually
decided.
