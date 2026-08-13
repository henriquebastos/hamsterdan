# Experience map — verified behavioral model

Promoted by [AX0](experiments/ax0-experience-map.md) from seed hypotheses
to boundary-verified scenarios. Topology never consulted. Each scenario
carries a confidence tag:

```text
CONFIRMED   — verified in boundary code and/or product docs (evidence cited)
PARTIAL     — mechanics verified; some clause corrected or unproven
NET-DECIDED — the boundary provides the mechanism, but the decision to
              use it is made inside the net. Not derivable under blackout.
```

`NET-DECIDED` markers are the map of where the decision layer lives —
they are AX1/AX5 targets, not failures of the map.

## Lifecycle

```text
CONFIRMED  given no durable instance for PR #N
           when any admitted PR-addressable webhook arrives
           then reconciliation reads LIVE PR state (never trusts the
                webhook action); an open non-draft PR yields instance
                github:{inst}:{repo}:pr:N, Seed, Admission, and
                GenerationStart(relation="new", epoch=1) + commit
           — host/service.py:525-529, host/application.py:130-167, 312-358

PARTIAL    …and a dashboard comment is created
           mechanics confirmed (singleton create-or-update, fenced:
           host/activities.py:375-395, github_app/effects.py:148-202);
           WHEN it is first requested is NET-DECIDED

CONFIRMED  given an active instance at head H1
           when the observed head becomes H2
           then a superseding generation starts: drain current work,
                GenerationStart(epoch+1), scope reset, commit; in-flight
                H1 effects cannot pass the fence
           — host/application.py:168-172, 312-358; host/runtime.py:234-267

NET-DECIDED …and review/CI observation restarts against H2
           discard is proven; the restart decision is the net's

CONFIRMED  given an active instance
           when the base branch moves (head unchanged)
           then NO generation starts and epoch does NOT advance; a
                same-epoch verified_admission is emitted, and base_head
                still participates in every effect fence
           — host/application.py:168-204; host/runtime.py:234-247

CONFIRMED  given an active instance
           when the PR becomes a draft
           then GenerationStop to Dormant (last epoch/head retained)
           — host/application.py:139-154; contracts/readiness.py:296-302

CONFIRMED  given a Dormant instance
           when the PR is open and non-draft again
           then generation resumes with relation="resumed",
                epoch = last_epoch + 1
           — host/application.py:318-330

PARTIAL    given an active instance
           when the PR is closed or merged
           then GenerationStop(closed|merged) + commit; no NEW provider
                effect can pass the fence. NOT "no further effects":
                published effects remain, late terminals are still
                collected or quarantined, bookkeeping continues.
                Terminal has no boundary reactivation route.
           — host/application.py:130-138, 360-394; host/runtime.py:253-267
```

## Authority, fencing, and discard

```text
CONFIRMED  given an effect authorized under (epoch, head, base_head,
                policy_digest, operation)
           when it is about to execute
           then the fence re-reads GitHub and refuses on any change of
                lifecycle, head, base, base ref, or policy — twice
                (before and after), proving authority did not move
                during fencing
           — host/runtime.py:234-267

CONFIRMED  given review computed against H1
           when authority moved to H2 before publication
           then the result is DISCARDED (StaleAuthorityError at the
                final fence; scope reset also cancels stale work);
                consumed inputs are NOT restored (doctrine)
           — host/activities.py:145-199; host/runtime.py:234-252;
             lifecycle decision record

CONFIRMED  given ingress provably targeting a closed generation
           when it arrives
           then it is acknowledged and dropped; if its generation is
                UNCERTAIN it is quarantined, never reinterpreted as
                current
           — lifecycle decision record

CONFIRMED  given a successful change/repair returning provisional_head
           when further effects are considered
           then everything is fenced until the provisional head is
                verified by admission; a confirmed generation
                (relation="confirmed") preserves repair lineage
           — contracts/readiness.py:157-166; host/runtime.py:224-250;
             host/application.py:328-353
```

## Review & findings

```text
NET-DECIDED given an active instance
           when review is warranted
           then the review agent runs — trigger policy (every head?
                gated?) is the net's decision; docs silent

CONFIRMED  given a review agent invocation
           when it executes
           then no GitHub credential or repository authority reaches
                the agent, and agent output alone never authorizes an
                effect
           — docs/product/principles.md:11-12; mutation decision record

PARTIAL    given accepted findings
           when they are published
           then inline where possible, immutable operation publication,
                lookup-first (marker: kind+operation+head)
           — host/activities.py:339-373; github_app/effects.py:89-146
           WHEN and re-publication policy after head move: NET-DECIDED
```

## CI / Actions

```text
CONFIRMED  given workflow_run / check_* webhooks for a PR
           when reconciliation runs
           then event payload status is NOT trusted: the newest
                exact-head run is selected, required jobs assessed, and
                ActionsObservation(epoch, head, run, attempt,
                conclusion, fingerprint, …) emitted
           — host/application.py:289-310; github_app/gateway.py:285-346

NET-DECIDED given failed required checks
           when a response is chosen
           then rerun vs repair vs wait vs ask — the selection is the
                net's; docs silent

CONFIRMED  given a repair attempt producing a patch
           when the commit is published
           then host-validated patch, commit with Hamsterdan-Operation
                and Hamsterdan-Payload-Digest trailers, server-side CAS
                ref advance after a fresh PR read; a moved branch
                rejects the attempt (discard, not force)
           — host/git_publish.py:80-152, 249-258

NET-DECIDED …and a fresh repair starts against the new head
```

## Conversation

```text
CONFIRMED  given a PR comment
           when admission is evaluated
           then fail-closed: only newly created, exact-leading @app
                mentions from human OWNER/MEMBER/COLLABORATOR authors
                are admitted; mention-stripped text + audit identity,
                bound to current epoch/head
           — github_app/webhooks.py:75-112; host/application.py:269-287

CONFIRMED  given an admitted conversation
           when classified
           then EXACTLY ONE typed intent of 12 kinds; zero or multiple
                → safe immutable "no workflow change" reply; `status`
                normalizes to `reply`
           — host/activities.py:273-317, 297-301

CONFIRMED  given a classified intent
           when it is a mutation kind (change, update_base,
                resolve_conflict — the only 3)
           then explicit+authorized executes immediately, no
                confirmation ceremony, under the full authority fence;
                ambiguous → clarification reply, no mutation;
                unauthorized → no mutation
           — host/activities.py:630-668; mutation decision record

NET-DECIDED given any of the 9 non-mutation kinds
           when executed
           then the workflow action per kind is the net's decision;
                docs silent (gap list #8-12)

CONFIRMED  given an intent reply
           when published
           then immutable lookup-first comment keyed by operation/head;
                payload collision fails closed
           — host/activities.py:766-788; github_app/effects.py:89-146
```

## Timers & sweep

```text
PARTIAL    given a reminder deferred until T
           when T matures (durable wall-clock timer)
           then reminder publication is fenced, lookup-first, immutable
                — replay of one operation cannot duplicate the comment
           — host/runtime.py:152-160; host/activities.py:397-415
           WHO schedules T and exactly-one-request: NET-DECIDED

CONFIRMED  given durable PR instances exist
           when the host starts or the sweep interval (60s) elapses
           then each valid instance is activated independently; frozen
                activity terminals are settled BEFORE observing the
                provider; failures in one instance do not stop others
           — host/service.py:163-165, 376-406, 494-508, 582-586
```

## Publication & recovery

```text
CONFIRMED  given any durable publication
           when it fails
           then bounded classified retry (3 attempts) inside ONE
                immutable logical operation; GitHub/deadline capability
                failures stay recoverable; unknown terminal failures
                become explicit nonrecoverable faults
           — host/runtime.py:59-63, 115-149

CONFIRMED  given a publication exhausted retries recoverably
           when an authorized recover_publication intent names the
                exact blocked target and operation
           then ONE fresh occurrence is created reusing the stable
                provider-effect identity (lookup-first); nothing
                reopens automatically otherwise
           — briefing:73-78; lifecycle decision record

PARTIAL    given readiness gates
           when all are satisfied (green/flaky Actions, findings
                clear/published, human approval, conversations
                resolved, base current, mergeable, no conflicts or
                pending mutations, no blocking faults)
           then the "gates ready" advisory is published — and Hamsterdan
                NEVER merges
           — gate predicate contracts/readiness.py:763-797;
             host/activities.py:417-441
           EMISSION of ReadinessCommand: NET-DECIDED
```

## Open questions after AX0

| # | Question | Status |
| --- | --- | --- |
| 1 | Review trigger policy (every head? gated?) | NET-DECIDED → AX1 re-derives from intent; AX5 compares |
| 2 | Per-kind semantics of the 9 non-mutation intents | NET-DECIDED + docs gap → same |
| 3 | ReadinessCommand emission ownership | NET-DECIDED → same |
| 4 | Rerun vs repair selection | NET-DECIDED → same |
| 5 | Dashboard republication trigger | NET-DECIDED → same |
| 6 | Restart-after-discard policy (new head) | NET-DECIDED → same |
| 7 | Reminder scheduling ownership (defer/snooze → timer) | NET-DECIDED → same |
| 8 | Full 29-item documentation gap list | preserved in [AX0](experiments/ax0-experience-map.md) |
