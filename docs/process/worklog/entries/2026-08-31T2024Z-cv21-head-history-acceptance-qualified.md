# CV21 Head History acceptance qualified locally

CV21.DS2 task 4 now carries one registered, opened, durably staged Head
observation through the sole workflow bridge into Petrus History and stops at
the unfinished acceptance cut. Hamsterdan pins Petrus exactly to
`4e5c2500af4eb439e8e8f5ec108982c81bfc7427`, reconstructs task-3 authority from
readiness SQLite by task-2 delivery identity, requires the existing host
registration/root binding to equal the deterministic subject-derived carrier,
requires exactly one matching catalog and singleton root-binding row, and
serializes the one-PR Engine writer under host catalog authority. Duplicate or
conflicting rows in malformed constraint-free schemas and a corrupt redirect to
another valid opened root fail before either History changes. No caller supplies
staging, subject, grant, entry, policy, source, token, delivery identity, or
occurrence, and HTTP remains custody-only.

The bounded catalog and root reads validate exact-one durable authority through
positive-integer and strict-text SQL projections with 128-byte identity limits
before constructing strict values. Wrong-type, oversized, and invalid-singleton
rows fail with fixed corruption codes; conflict diagnostics contain only the
bounded expected carrier identity, never malformed stored content.

The bridge identity is `workflow-bridge/head-seen-history-acceptance@2`. Its
first census row maps only source-neutral `HeadObservation` to retained
`HeadSeen` at `on_head`: exact head/base SHAs, explicit-true mergeability,
manifest policy, `strict_base=True`, and `base_current=False`. Only local
incarnation 1, open, non-draft, non-merged evidence is eligible. The stable
`history-delivery:v1:sha256:<digest>` binds bridge, manifest, grant digest,
entry order, and observation key. Public `Engine.accept_delivery` appends only
adjacent `ExternalEventDelivered` and `FiringBegun`; the detached strict posture
identifies the same unfinished occurrence without exposing Petrus or retained
types.

Only the original durable one-entry `novel` authority can enter History. Exact
restaging recovers that authority, while corroboration and collision families
return bounded no-admission posture and malformed authority fails loud before
History. Real SQLite overlap converges concurrent exact acceptors on one
occurrence. Changed content under the accepted identity collides without
unrelated progress. The configured manifest ceiling is preserved across both
authoritative reads, so an append between host selection and readiness
reconstruction fails before History. Actual `SIGKILL` after the two History
records commit but before caller acknowledgement leaves one recoverable
occurrence; a fresh host/readiness graph reconstructs staging, exact-reoffers,
returns occurrence 1, and appends nothing.

History acceptance now rejects a canonical database plus WAL/shared-memory
footprint above 2 MiB, caps public History inspection at 4,096 records, reserves
128 KiB before every Engine load for SQLite WAL/shared-memory establishment,
and remeasures then reserves 1 MiB before the public acceptance call for a new
identity's finite two-record transaction. Exact unfinished or ended reoffer
reserves no append bytes and appends nothing, while retaining the load reserve.
The real first transaction remains below the conservative write headroom, and
a modeled near-ceiling turn fails before `accept_delivery`. It translates an
ended prior acknowledgement from that finite page rather than a full
`Engine.records` copy. Owner-local and root resource profiles expose zero
unfinished firings before acceptance and exactly one afterward. Lowered byte,
record, and in-flight ceilings fail before another acceptance or append.
Malformed Engine load/replay becomes a fixed readiness-owned corruption error
whose exception chain contains no stored History content, including deeply
nested JSON recursion; valid-load changed-content collision remains distinct.
Malformed retained acquisition and canonical observation decoding likewise
become fixed cause-free ingress errors before Engine load, so stored content
cannot escape through task-4 diagnostics.
Direct public-seam tests prove one exact
source/token/identity call without scope, bounded prior/scoped posture, and
acknowledgement correlation refusal.

Owner-local and cumulative root Worlds expose custody, staging, unfinished
History acceptance, and not-yet-implemented fold as separate observations.
Fresh-root replay and independently derived owner and cross-owner root checks
pin bridge identity, source, token color and every payload field, delivery
identity, manifest/grant/key/order, occurrence, adjacent record order,
accepted-versus-folded status, and finite History/in-flight/file/byte/SQLite
resources. The root mounts the unchanged owner-local staging posture; accepted
state requires the exact original `novel` posture, while non-admitted staging
remains observable without registration or History. One bounded public History
page replaces complete History copying, and file/byte and catalog-row
observations stop at ceiling plus one before materializing oversized state.
Root/catalog SQL projections likewise reject oversized singleton values and
duplicate root authority before detached construction. The owner checker and
its versioned identity bind the independently decoded canonical Head
observation as well as its key/bytes, closing substitution of bridge input.
Focused task evidence passed 262 tests. `scripts/check hamsterdan2` passed strict
Ruff, formatting, ty, seven ast-grep rule fixtures/scans, architecture checks,
and 325 tests.

Eleven adversarial Oracle rounds preceded final qualification. The first ten
identified, in order: valid-root redirect and delegated root-check weakness;
lost inner manifest capacity; unbounded History inspection and missing in-flight
resource; duplicate malformed catalog/root authority; malformed singleton
diagnostics; checker staging omission and eager full materialization; raw
History errors, catalog reads, and uncovered acknowledgement branches; missing
observation binding in the owner checker; record-ceiling reoffer and nested-JSON
recursion; and pre-write WAL headroom plus ingress decoder-chain disclosure.
Each behavioral finding received a red regression before its smallest
correction. Fresh round 11 reviewed the complete updated diff and returned the
exact verdict `No findings.`

The required Petrus revision makes `Engine.records` return detached deep copies,
raising the unchanged generated current-V5 delivery-recovery campaign from
22.70 seconds under the prior pin to 33.65 seconds under the new pin. Its test
budget now follows the neighboring generated campaigns at 60 seconds without
changing assertions; it passed the full profile in 30.63 seconds. The full
profile passed quick/architecture/replacement, relay, TypeScript, live capture,
distribution build, and all task-related tests. Its cumulative Python run
reproduced exactly the inherited 14 `tests/unit/test_orb_setup.py` failures at
`.agents/setup:229` from unset `$USER`, alongside 1,151 passes. No new failure
remains, and the unrelated setup defect is unchanged.

The occurrence remains unfinished: there is no `FiringCompleted`,
`TokensProduced`, retained-Net fold, host completion, Dispatch task, Worker,
provider read/effect, agent work, currentness witness, lifecycle successor, or
second admission ledger. CV21.DS2 remains Active. Task 5 must reconstruct the
same immutable staging, exact-reoffer it to recover the accepted carrier, call
`Engine.complete_delivery` only for that occurrence, and then prove retained
fold and host completion as later cuts.
