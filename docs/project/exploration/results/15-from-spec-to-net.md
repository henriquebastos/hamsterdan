# 15 — From spec to net

**Rely on this: a Given/When/Then story maps onto a net mechanically —
Given names tokens and authority, When names triggers and steps, Then
names exits and gates.**

## The mapping

```text
GIVEN   what must already be true
        → the entry token's type (its color) and fields
        → declared contexts (ambient facts the work may read or hold)
        → the authority the case runs under (epoch, head, …)

WHEN    what happens
        → the trigger: an ingress event with a deduplicating identity
        → the steps: pure steps, modeled decisions, activities

THEN    what the world looks like after
        → one named exit per distinct outcome — including "discarded"
        → every world change goes through a gate (lookup-first or CAS)

BUT/IF  the edge clauses
        → value guards, extra outcomes, the failure rail
```

Two rules keep the mapping honest. Every `Then` clause is either a
**named exit** (the net's own vocabulary) or a **gate effect** (with an
operation identity) — never both vague. And any clause you cannot
place is a missing concept: an unnamed outcome, an undeclared ambient
fact, or an unowned piece of loop state.

## A worked example

The spec, as you'd write it:

```gherkin
Feature: refund a paid order

  Given a paid order
  When the customer requests a refund
  Then the payment is refunded through the provider
  And the customer is notified

  But if the amount exceeds the approval threshold
  Then a human approves first

  But if the provider says the payment was already refunded
  Then treat it as done, not as an error

  But if the order was cancelled while we processed
  Then discard the work and do nothing
```

The design, read straight off the mapping:

```python
# GIVEN → colors
RefundRequest   # entry: order_id, amount, epoch
Approved        # human said yes
Refunded        # provider confirmed (or had already done it)
Discarded       # authority moved; world untouched

# WHEN/BUT → steps and routing
req = on(RefundRequest)

decide = branch("triage",
    case(req.amount > THRESHOLD, then=human_approval()),   # value guard
    otherwise=auto_approve(),
)

refund_gate = activity("refund",                            # the CAS-like gate
    outcomes={
        "refunded":  Refunded,
        "already":   Refunded,      # BUT-clause 2: done is done — same exit
        "cancelled": Discarded,     # BUT-clause 3: preconditions changed
    },
    identity=lambda r: f"refund:{r.order_id}:{r.epoch}",
)

notify = activity("notify",                                  # lookup-first gate
    outcomes={"sent": Notified},
    identity=lambda r: f"notify:{r.order_id}:refund",
)

# THEN → composition; exits are the spec's Then-clauses, verbatim
workflow = then(decide, refund_gate, on="approved")
workflow = then(workflow, notify, on="refunded")
# exits: sent | discarded — and nothing else
```

Everything before `refund_gate` is disposable (concept 9): approval
routing is pure, and if the order is cancelled mid-flight, the gate's
own `cancelled` outcome is the discard path — no pre-checking.

Then run it and read the four artifacts (concept 14):

```python
motion = run(workflow, RefundRequest(order_id="o-1", amount=50, epoch=3))
motion.settled      # {'sent': [...], 'discarded': []}
motion.replay()     # the durable contract, demonstrated
```

## The design checklist

In order, for any new net:

1. **Colors first.** Name every token type a story clause mentions.
   One named type per meaning — never tuples, never reuse.
2. **Ingress.** What events start or resume work? Give each an
   identity.
3. **Gates.** Where does the world change? Lookup-first or CAS? What
   is each operation's identity?
4. **Exits.** One per distinct Then/But clause — including
   `discarded`. If two clauses end the same way, they share an exit.
5. **Routing.** Modeled outcome (someone decides) or value guard (the
   data decides)? Declare overlap order and `otherwise`.
6. **Parallelism.** Named branches, explicit join color, totality.
7. **Repetition.** Where does the loop variable durably live — token,
   or provider? Bound it; name the exhaustion exit.
8. **The rail.** What can fail that nobody modeled? Attempt those
   steps; recover or terminate visibly.
9. **Lifecycle.** Can the case pause and resume? Then it has a control
   machine and an epoch; stamp head-bound work.
10. **Coordination.** Do concerns wait on each other? Fold their exits
    into a snapshot; decide from the snapshot; never read across.
11. **Purity audit.** Push gates late; bracket everything before them
    as disposable. Prefer discarding work over saving it.
12. **Run, replay, count.** Four artifacts; `arcs/(P+T)` near 1;
    every clause of the spec visible as a port, gate, or guard.

## What stays explicit, what may be inferred

```text
EXPLICIT   exit names · payload types · operation identities · overlap
           order · join colors · adapters between differing payloads ·
           epochs on head-bound work · gate economy (lookup vs CAS)
INFERRED   single-in/out ports from signatures · colors from types ·
           adapter contracts from signatures · staleness from
           epoch comparison · dedup from operation identity
NEVER      connectivity from type matching · meaning from shape ·
           durable state from any live object · correctness from
           a live marking (fold settled exits instead)
```

## Why trust it

The mapping is the inverse of how ES-004 derived its specification:
boundary evidence (inputs, effects, invariants) → behavioral model →
net, with every divergence from production classified. The example's
every element is a proven concept from this primer — nothing here is
new machinery. The contrast experiment the Navigator asked for is
exactly this chapter applied by hand: write the stories, run the
checklist, and compare what emerges with what exists.
