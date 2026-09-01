---
code: CV21.DS2
level: Delivery Story
status: Active
status_reason: Tasks 1 through 4 are delivered; retained fold and host completion remain in task 5
updated: 2026-08-31
related:
  - index.md
  - cv21-ds1-first-bridged-pr-lifecycle.md
  - contract-inheritance.md
  - ../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
---

# CV21.DS2 — Admit one PR observation through the bridge

## Outcome

Accept one signed GitHub webhook through new provider normalization and durable
host delivery custody, then acknowledge the HTTP request without waiting for
readiness. A later authority turn performs source-neutral readiness admission,
bridge conversion, and identified Petrus History delivery until the current
Net folds the exact observation. Custodied, acknowledged, admitted, and folded
remain distinct reconstructible cuts.

## Vertical path

```text
HTTP request: raw webhook -> new GitHub verification/normalization
  -> host delivery custody -> HTTP acknowledgement -> request ends

later authority turn: PullRequestSnapshot + provenance -> focused observation/key
  -> manifest/grant -> bridge conversion -> identified History -> current fold
  -> detached posture -> host delivery completion
```

## Owns

- first provider models, webhook acquisition, route evidence, and durable host
  delivery custody;
- snapshot/provenance, focused observation/key, ingress manifest/grant/entries,
  exact classification, and acknowledgement cuts; and
- first observation-family bridge census and correspondence scenarios.

## Excludes

No provider exact read, discovery, successor incarnation/currentness, effect,
new workflow fold, or second admission ledger.

## Confirmed expansion

DS2 proceeds serially. Completion of one task does not imply completion of the
Delivery Story:

1. **Petrus phased-delivery prerequisite — delivered.** Petrus `origin/main`
   contains exact commit `4e5c2500af4eb439e8e8f5ec108982c81bfc7427`
   (`feat(engine): split identified delivery into durable phases`). Hamsterdan
   does not consume that revision until task 4 first needs History acceptance.
2. **Signed webhook to durable HTTP custody — delivered.** One real ASGI
   request ends after new GitHub normalization and host-owned durable
   acquisition.
3. **Source-neutral readiness staging and classification — delivered.** The
   common snapshot projection, focused Head observation/key, manifest, grant,
   closed classifications, SQLite custody, detached reconstruction, and
   authority-side host composition now run outside the request.
4. **Bridge and identified History acceptance — delivered.** The exact Petrus
   revision is pinned. One eligible Head entry maps through the sole bridge and
   public `Engine.accept_delivery` into durable unfinished History. Acceptance
   and fold are now independently observable; this task stops at acceptance.
5. **Retained fold, host completion, and process/DST qualification — planned.**
   Recover the exact accepted carrier, complete only its occurrence, fold it in
   the retained Net, project detached posture, and mark host completion while
   extending the already established correspondence, crash, replay, checker-
   sensitivity, and resource evidence.

## Delivered task 2 contract

The task begins with exact raw ASGI headers and bytes and ends with one bounded
HTTP response. It does not open readiness, touch Petrus History, claim Dispatch,
run a Worker, call a provider API, invoke the bridge, or fold workflow state.

`github_app` owns strict provider identifiers and webhook models,
HMAC-before-parse verification through the installed GitHubKit boundary,
immutable `PullRequestSnapshot`, bounded `ObservationProvenance`, and exact
envelope normalization. `host` owns configured active-route binding, durable
inbox custody, acquisition identity `(ProviderRouteId, DeliveryId)`, monotonic
custody generation, receipt, collision quarantine, and FastAPI composition.

The snapshot retains only:

- immutable installation/repository/pull-request subject;
- exact head and base tips, each with repository ID, branch ref, and SHA;
- provider lifecycle state, draft, merged, and tri-state mergeability; and
- bounded diagnostic provider update time.

Event, action, and delivery ID belong to provenance. Branch policy, base
currentness, provider currency, arbitrary provider fields, and workflow
decisions are not inferred.

The durable acquisition outcomes are closed:

- first valid identity and canonical normalized content: `retained`;
- same route, delivery ID, and content: `exact_duplicate`, with no second row;
- same route and delivery ID with changed content: `quarantined`, with the
  original normalized evidence never overwritten and no readiness eligibility.

All three return HTTP 202 with the exact bounded receipt fields `custody`,
`provider_route_id`, `delivery_id`, `custody_generation`, and `disposition`.
The generation assigned by the first acquisition remains stable for every
redelivery. A collision and every later redelivery of a quarantined acquisition
return `quarantined`; HTTP receipt never claims workflow completion.

Transport and persistence are bounded: the raw body is at most 1 MiB; the raw
header block is at most 100 entries and 32 KiB; protected header values are
unique and at most 256 bytes; provider integer identifiers are in the positive
signed-64-bit range; branch evidence has explicit byte limits; normalized
provider timestamps are canonical UTC instants; normalized canonical content
is at most 16 KiB; and one custody store retains at most 10,000 acquisition
rows. Invalid HMAC, malformed or oversized request, duplicate protected header,
unsupported envelope, and unconfigured or mismatched route return HTTP 400 as
`{"refusal":"<closed_reason>"}`. Exhausted custody capacity returns the same
bounded shape with HTTP 503. Invalid raw input is never persisted.

The concrete route is `POST /github/webhooks`. A retained, duplicate, or
quarantined acquisition returns only the five documented receipt fields with
HTTP 202; a refusal returns only its closed reason. Neither response claims
later readiness or workflow completion.

SQLite retains only configured route identity, delivery identity, custody
generation, canonical normalized content and digest, disposition, and at most
one collision digest. It never retains raw body, signatures, secrets, arbitrary
headers, provider dictionaries, SDK objects, or unbounded diagnostics. A fresh
process can reconstruct the original normalized delivery and quarantine state.

## Delivered task 3 contract

A caller now uses the sole host composition root to reconstruct one task-2
`CustodiedDelivery` and run a separate readiness staging turn. HTTP does not
invoke this path. The turn projects the retained provider snapshot into a
workflow-owned `HeadObservation` for immutable subject and local incarnation 1,
then commits one immutable `IngressManifest`, one exact manifest-scoped
`AdmissionGrant`, its ordered unique-key `IngressEntry`, and one closed durable
classification in a single readiness-owned SQLite transaction. The returned
`StagingPosture` is detached and strictly reconstructible from a fresh object
graph.

The focused Head semantics are exactly the subject, local incarnation, head and
base branch tips, provider lifecycle state, draft, merged, and tri-state
mergeability. Provider update time, webhook event/action/delivery identity,
provider route, custody generation, policy revision, and provenance remain
acquisition or diagnostic facts and do not enter the observation canonical
bytes or semantic equality. Task 3 neither claims provider currency or base
currentness nor implements ancestry, lifecycle successor, or
`CurrentnessWitness`.

`ObservationKey` v1 is `obs:v1:sha256:<digest>` over finite deterministic
canonical JSON containing the complete focused semantics. Equality requires
both key and canonical bytes: identical key and bytes from another acquisition
are `corroborating`, while identical key with different bytes is a fatal
`semantic_collision` that retains both canonical observations. The complete
closed classification family is `exact_duplicate`, `acquisition_collision`,
`novel`, `corroborating`, `stale`, `semantic_collision`, `conflicting`, and
`incomparable`. Head evidence does not use timestamps, delivery order, custody
generation, or Git ancestry as an ordering source. Changed tips are therefore
`incomparable` and refresh-required; contradictory focused semantics at the
same tips are bounded non-retryable `conflicting` failure data. `stale` remains
available for a later orderable family and is not manufactured for Head.

An exact acquisition reoffer returns `exact_duplicate` without another
manifest, grant, entry, or durable decision. A task-2 quarantined acquisition
gets one empty manifest and grant with durable `acquisition_collision`; it is
never readiness-eligible and creates no observation entry. Changed facts under
an already staged acquisition identity return `acquisition_collision` while
the original immutable staging authority remains unchanged. Policy revision is
captured once in the manifest and therefore in its grant, but never in semantic
equality. No observation or admission ledger was introduced; Petrus History
remains the sole future workflow-admission ledger.

The authority turn linearizes at a final bounded host-custody read after strict
reconstruction of the initially fetched row. A collision completed before that
final read, including one concurrent with reconstruction, is reconstructed as
quarantine and produces empty fatal staging. A collision after the final read
is later than the staging turn: HTTP can complete without waiting for readiness,
and the changed custody fact cannot rewrite the original acquisition being
staged. Readiness serializes staging turns before selecting host custody, so a
later quarantine selector cannot overtake an earlier eligible selector at
manifest retention; HTTP never uses that readiness lock. If staging is
interrupted before the readiness commit, no staging authority is durable; a
fresh turn reconstructs the then-current host custody.

Ingress enforces 16,768 canonical acquisition bytes, 8,192 canonical bytes per
observation, eight ordered entries per manifest, 65,536 canonical manifest
bytes, 10,000 manifests by default, and 131,072 SQLite pages. Detached resource
observations report manifest, entry, grant, decision, acquisition-byte,
canonical-byte, and page usage with their ceilings. Serial SQLite authority
covering selection and retention prevents concurrent duplicate or inverted
manifests or grants. Strict reconstruction
revalidates acquisition canonical bytes and digest, identity, contiguous entry
order, key-to-bytes relation, canonical observation, manifest identity, exact
grant digest, and ruled decision shape. An immutable transaction-assigned
staging sequence reconstructs manifests in original retention order and exactly
recomputes each decision from preceding reconstructed entries. This sequence is
classification context only; it does not order Head semantics.
Reconstruction queries read at most the configured manifest ceiling plus one,
the entry ceiling plus one, and two decision rows before rejecting excess
cardinality. Every first-acquisition path, including quarantine, reconstructs
the complete prior authority and rejects orphan entry, grant, or decision rows
before inserting anything. Opening existing ingress also verifies that both the
effective SQLite maximum and current page count remain within the configured
page ceiling. Before any retained delivery can feed staging, host custody also
verifies its configured row ceiling and both its effective SQLite maximum and
current page count; host composition carries the same configured row ceiling
into HTTP acquisition and staging reconstruction. Singleton host acquisition,
readiness acquisition, and grant lookups read at most two rows and reject
malformed existing schemas that contain duplicate authority.

Owner-local and cumulative Petrus Worlds exactly replay staging from fresh
roots with independent key/bytes/order/manifest/grant/decision/acquisition
checker sensitivity and explicit resource budgets. The cumulative root first
proves signed HTTP custody leaves staging and History empty, then runs the
separate authority command exactly once while History, fold, and Dispatch stay
untouched. Real process evidence kills after the staging transaction commits
but before caller success; a fresh host/readiness composition reconstructs the
same authority and reoffers it as an exact duplicate without a second manifest,
grant, entry, or decision.

Task 3 stops before bridge conversion, Petrus History acceptance, retained-Net
fold, host completion, Dispatch, Worker, provider read/effect, agent work, or
workflow advancement. It leaves the Hamsterdan Petrus pin unchanged; task 4
owns the prerequisite pin and first use of identified phased delivery.

## Delivered task 4 contract

Hamsterdan now pins Petrus exactly to
`4e5c2500af4eb439e8e8f5ec108982c81bfc7427`. The sole host composition root
exposes a later authority operation selected only by task 2's
`(ProviderRouteId, DeliveryId)`. It reconstructs the original task-3 staging,
derives the staged subject, requires the existing DS1 registration/root binding,
requires that catalog binding to equal the subject-derived instance/root, and
requires exact-one cardinality for both the selected catalog authority and the
singleton readiness-root binding. Duplicate, conflicting, or invalid-singleton
rows in constraint-free malformed schemas fail before Engine load. Exact-one
rows are also projected through positive-integer, strict-text, and 128-byte
identity bounds before strict value construction; invalid types or lengths use
fixed diagnostics that contain no recorded value. Engine ownership remains
serialized through the host catalog authority transaction.
Unknown, mismatched, or redirected registration fails before History even when
the redirect names another internally valid opened root; the operation never
auto-registers a PR. HTTP still constructs only webhook normalization and host
delivery custody and never invokes, waits for, or acquires the readiness/History
authority path.

Readiness receives no caller-supplied posture, manifest, grant, entry, token,
source, identity, policy, occurrence, or subject. It reconstructs the selected
staging authority from readiness SQLite and revalidates acquisition identity,
manifest identity, policy, entry order/key/canonical bytes/observation,
grant ID/digest, closed decision shape, subject, and local incarnation before
History. Only the original durable `novel` posture with exactly one entry is
eligible. Exact-acquisition restaging recovers that original authority;
`corroborating`, `acquisition_collision`, `semantic_collision`, `conflicting`,
and `incomparable` return detached `staging_not_novel` refusal without History
creation or mutation. Corrupt or unearned `stale` authority fails strict
reconstruction. The configured manifest ceiling governs both host selection and
readiness's later authoritative reconstruction; an append between those reads
therefore fails before History instead of reverting to the default ceiling. No
accepted flag or pointer is retained in host or ingress; Petrus History is the
sole admission ledger.

The first bridge census row is source-neutral `HeadObservation` to retained
`HeadSeen` at source `on_head`, under
`workflow-bridge/head-seen-history-acceptance@2`. The exact payload is:

```text
head = observation.head.sha
base = observation.base.sha
mergeable = observation.mergeable is True
policy = manifest.policy_revision
strict_base = True
base_current = False
```

The bridge accepts only local incarnation 1, lifecycle `open`, `draft=False`,
and `merged=False`; tri-state mergeability remains admitted through the mapping
above. Closed, merged, or draft observations fail before History with bounded
bridge diagnostics. This task does not fabricate `DraftSeen`, `ReadySeen`, or
`CloseSeen`. Repository/ref/lifecycle semantics remain in canonical staging and
acceptance identity even though retained `HeadSeen` consumes the two SHAs.
Provider provenance, update time, route, custody generation, and receipt order
enter neither token nor `ObservationKey`; policy comes only from the exact
manifest and remains outside semantic equality.

`HistoryDeliveryIdentity` is the finite
`history-delivery:v1:sha256:<digest>` of bridge identity, exact manifest ID,
grant ID and manifest digest, entry order, and observation key. Those immutable
authority identifiers transitively bind canonical source-neutral staging, so
the identity is deterministic across process loss and independent of process
memory, time, mutable configuration, receipt order, and retained token rendering
alone. It is neither a spent-grant marker nor a second ledger.

Readiness loads the one-PR Engine and calls public `Engine.accept_delivery`
exactly once per authority turn with the bridge-private source/token and stable
identity, without scope. A fresh offer appends exactly adjacent
`ExternalEventDelivered` and `FiringBegun` and returns `AcceptedDelivery`. The
detached strict `HistoryAcceptancePosture` exposes the new subject, staging/
bridge/manifest/grant/entry/key/delivery identities, occurrence, and explicit
unfinished/unfolded status without Petrus or retained V5 types. Fresh exact
reoffer reconstructs the same `AcceptedDelivery` and occurrence without an
append or empty provider transaction. `PriorAcknowledgement` becomes bounded
`occurrence_already_ended` refusal, never implicit completion; an unexpected
scoped acknowledgement is also a bounded refusal.

Before Engine load, readiness caps the canonical SQLite database, WAL, and
shared-memory files at 2 MiB. It then uses public `Engine.history_page` with a
4,096-record ceiling. It reserves the exact two records only when that delivery
identity has no durable acceptance fact; exact unfinished or ended reoffer at
the ceiling reserves none and appends nothing. Prior-acknowledgement translation
inspects that same bounded detached page rather than `Engine.records`. The owner
and root observations expose and budget
`retained.readiness.in_flight_occurrences`: zero through staging and one at this
unfinished acceptance cut. Malformed History load/replay becomes one fixed
readiness-owned corruption error with no stored payload in its exception chain,
including recursive JSON decode failures; a changed-content identity collision
after valid load remains a separate Petrus refusal. Direct seam evidence pins
exactly one `accept_delivery` call with source/token/identity and no scope, plus
bounded prior/scoped return postures and identity-correlation refusal.

Owner-local readiness and cumulative root Worlds now use a separate strict
acceptance command after open, custody, and staging. Neutral History observation
pins source, token color and every payload field, stable identity, occurrence,
adjacent record order, and accepted-versus-folded status. Independent mutations
cover bridge/root/manifest/grant/key/order/identity/correlation evidence. Fresh-
root replay is exact under finite History, in-flight, file, byte, and SQLite
resources. Real SQLite concurrent exact acceptors converge on one occurrence;
changed content under that identity collides without unrelated progress.
Actual `SIGKILL` after durable acceptance but before caller acknowledgement
leaves the two records intact; a fresh host/readiness graph reconstructs staging,
exact-reoffers, observes occurrence 1, and appends nothing. The root observation
mounts the unchanged owner-local staging posture; accepted checker state requires
that exact original `novel` posture, and cross-owner correspondence requires it
to equal ingress custody. History uses one bounded public page, while file/byte
and host-catalog observations stop at ceiling plus one before complete
materialization. Type/byte projections and limit-two root/catalog reads reject
oversized singleton values or duplicate root authority with fixed diagnostics
before constructing detached observations.

Task 4 deliberately leaves the occurrence unfinished. It creates no
`FiringCompleted`, `TokensProduced`, retained-Net fold, host delivery completion,
Dispatch task, Worker, provider read/effect, agent work, currentness witness,
lifecycle successor, or second admission ledger. Task 5 must reconstruct the
same immutable staging, load the Engine, exact-reoffer to recover the
`AcceptedDelivery` carrier, call `Engine.complete_delivery` for only that
occurrence, then prove retained fold and host completion as later cuts.

## Acceptance

- exact duplicate, corroboration, collision, incomparable evidence, and refusal
  have closed finite outcomes;
- the HTTP response requires only durable host custody and neither invokes nor
  waits for staging, a readiness fold, Dispatch claim, provider effect, or
  Worker;
- History is the sole workflow-admission ledger;
- same accepted input reaches the current Net exactly once across every named
  crash cut without old value leakage;
- bridge conversion does not add policy or provider provenance to semantic
  equality; and
- owner-local/root replay and mutation-sensitive checks prove the full path.

Tasks 1–4 do not yet satisfy this Delivery Story acceptance. Task 5 remains
required before DS2 can become `Completed` or receive a completion worklog.
