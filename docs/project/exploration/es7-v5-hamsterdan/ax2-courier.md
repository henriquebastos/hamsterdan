# AX2 — The courier: a generic cross-instance delivery primitive

**Status:** done, oracle-approved (four rounds), 2026-08-15.
**Question:** what is the smallest primitive that moves a token minted
in Petrus instance A into instance B exactly once, across a transport
that can crash at each pinned boundary — using only shipped engine
features?

**Answer:** an outbox baton of token envelopes + a stateless,
schema-blind courier + the engine's own delivery-door dedup. No
engine changes, no production changes.

- [test_ax2_courier.py](test_ax2_courier.py) — the whole prototype:
  two toy nets (producer/consumer, Hamsterdan-independent), the
  `Courier` dataclass, 12 pinned timelines.

## 1. The protocol

```text
producer net                 host                consumer net
┌───────────────┐      ┌──────────────┐      ┌────────────────┐
│ out.box baton │─read─│   Courier    │─────▶│ on_parcel door │
│ {next,parcels}│      │  (STATELESS) │      │ (engine dedups │
│               │◀─ack─│              │      │  by identity)  │
└───────────────┘      └──────────────┘      └────────────────┘
```

1. **Outbox = one queue baton token** `{"next": n, "parcels": (...)}`.
   Each parcel is a **token envelope** the producing fold authors:
   `{"n": seq, "token": {"color": ..., "data": {...}}}`. The producing
   fold mints each parcel's sequence from the baton: durable,
   single-writer, replay-stable. One queue token (not one token per
   parcel) is what lets the ack fold match by pure data — zero guards,
   zero filters, the V5 style.
2. **Parcel identity = `{route_id}:{seq}`** — derived from durable
   source state, never minted by the transport.
3. **Courier = assembly wiring only, schema-blind.** `drain()` reads
   the outbox marking, reconstructs each envelope's token verbatim —
   never reading or constructing domain data — and delivers it to the
   target door under the parcel identity, then delivers an exact-seq
   ack (`ack:{route_id}:{seq}`, protocol-owned color `CourierAck`) to
   the source's ack door. It holds no durable state at all. The same
   unchanged class transports a second, materially different token
   schema (`test_the_unchanged_courier_transports_a_second_token_color`).
4. **Exactly-once landing is the ENGINE's word, not the courier's.**
   `Instance.deliver` commits the door firing before returning and
   dedups by identity: exact redelivery → `PriorAcknowledgement` (no
   firing, no token); identity reuse with different content →
   conflict, refused (DR 2026-07-14). The consumer net deliberately
   has NO dedup logic — its absence is the finding.

At-least-once transport + door-identity dedup = exactly-once landing.

## 2. The contract (oracle-hardened wording)

- **Identity namespace invariant.** Delivery identity is
  INSTANCE-GLOBAL at the target, not door-local. `route_id` must be an
  immutable, globally unique route identifier — distinguishing source
  instance (and incarnation, if a replaced source restarts its
  counter), outbox channel, and target route. Never a friendly label.
- **Custody contract.** One outbox is ordered, SINGLE-CONSUMER route
  custody. Every courier on it must share the exact wiring; same-route
  couriers may overlap — dedup at both doors converged in the tested
  serialized stale-snapshot interleave (one genuine schedule, not an
  exhaustive proof over all interleavings). Couriers with different
  targets on one outbox LOSE parcels — the first ack removes shared
  custody. Fan-out = one outbox per route, pinned by
  `test_one_producer_into_two_consumers_with_distinct_streams`.
- **Transport vs semantics.** The courier guarantees transport
  identity/dedup only. It does NOT provide stale-authority rejection:
  target loops keep their own fences (AX1's grant/incarnation
  comparison) — a deduped delivery can still be semantically stale.
- **Engine access stays serialized.** Two unfenced Engine objects
  writing one instance are outside the engine's single-writer
  contract; racing couriers are safe only through serialized calls.

## 3. Crash boundaries, each separately pinned

`Engine.deliver` returning means the door firing is COMMITTED — so the
boundaries that matter are not where intuition puts them. Scope of the
evidence: the tests pin the three post-return, inter-`Engine`-call
boundaries below by replaying over `InMemoryHistoryStore`; intra-call
atomicity and durable-backend crash behavior are inherited from the
engine's own contract, not fault-injected here.

| Crash at | Durable truth | Convergence | Test |
|---|---|---|---|
| after target accept, before target drive | parcel landed in target custody (one `ExternalEventDelivered`), downstream fold not yet run | resurrect target, fresh drain: fold fires, redelivery dedups, ack drains | `test_crash_after_target_accept_before_drive_is_already_durable` |
| after target drive, before ack | landed and folded; source never told | fresh drain: redelivery dedups, ack lands | `test_crash_after_target_delivery_before_ack_never_duplicates` |
| after ack accept, before source drive | CourierAck token durable NEXT TO the still-queued parcel | resurrect source: both survive; fresh drain dedups both deliveries; driving fires the pending fold | `test_crash_after_ack_accept_before_source_drive_converges` |

Plus the true overlap: courier B full-drains INSIDE courier A's loop
(A's snapshot goes stale mid-flight); A finishes its stale loop — all
its deliveries and acks dedup; FIFO order holds; one landing and one
ack landing per parcel (`test_two_same_route_couriers_racing_converge_in_order`).

And replay: a producer resurrected from its chronicle mid-crash-window
restores the durable parcel and re-derives the SAME identity strings
(the baton sequence is replayed state, `TokensProduced` freezes
produced parcels — no new sequence is minted), so redelivery dedups
(`test_a_resurrected_source_redelivers_the_same_identities`).

## 4. Design alternative, recorded

One-token-per-parcel outboxes with occurrence-derived identities
(correlating `TokensProduced.occurrence` / `TokensConsumed` in the
chronicle) were considered and set aside: parcel-level concurrency is
not needed for AX3's seams, host-side chronicle correlation is more
machinery, and ack matching would need keyed selection (guards) the
V5 style deliberately avoids. Revisit only if a route ever needs
out-of-order parcel consumption or unbounded queues.

## 5. Oracle rounds

| Round | Verdict | Amendments |
|---|---|---|
| 1 | reject | (1) the "crash after deliver" test actually crashed AFTER target drive — pin the real accept-before-drive boundary and rename the hook honestly; (2) pin the symmetric ack-accept crash and a real racing interleave; (3) state the identity namespace invariant, rename `stream` → `route_id` |
| 2 | reject | ack-replay test could not detect a duplicate ack landing (assert the surviving ack token and exactly one on_ack landing); the "race" was sequential — B must run INSIDE A's stale loop via a deterministic hook |
| 3 | reject | both round-2 blockers confirmed closed, but the courier still hard-coded the toy ParcelSeen/AckSeen schemas — "generic" was unearned. Amendments: parcels become verbatim token envelopes (`{"n", "token": {"color", "data"}}`), the ack becomes the protocol-owned `CourierAck` color, a second-token-color transport test, and four record wording fixes (crash scope, interleaving scope, "re-mints", premature approval status) |
| 4 | approve | — |

## 6. What AX3 inherits

- The courier as-is: `Courier(source, outbox_place, ack_door, target,
  door, route_id)` — one per cross-instance seam, any token color.
  Each seam's emitting fold authors the complete target token into its
  envelope; the courier transports it verbatim.
- Each AX1 cross-loop seam that crosses a shard boundary becomes:
  emitting fold appends an envelope to a route outbox (instead of a
  plain arc into the sibling mailbox) + a courier + the target's
  mailbox door.
- The seam facts already carry incarnation; the target loop's fences
  stay exactly as in AX1 (transport dedup ≠ authority fencing).

Validation at approval: 12 AX2 tests pass; 643 total with AX1 and the
untouched production suite; `scripts/check quick` clean.
