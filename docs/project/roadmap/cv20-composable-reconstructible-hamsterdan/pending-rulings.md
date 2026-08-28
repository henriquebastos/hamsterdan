# CV20 DS4–DS13 pending rulings

This register preserves the DS4–DS13 architecture audits for future Navigator
review. It is evidence and recommendation, not accepted CV20 design. The
canonical owners remain [the architecture](architecture.md),
[API contracts](api-contracts.md), [delivery sequence](delivery-sequence.md),
[replacement ledger](replacement-ledger.md), the Delivery Stories, and decided
records.

No recommendation in this register is Navigator-approved unless a current
canonical owner cited here already states the same rule. Audit adoption means
only that the audit author accepted an Oracle finding into the audit report. It
does not mean project adoption. No glossary term has been accepted by the
[concept analysis](concept-analysis/index.md).

## Register scope and authority

| Field | Value |
|---|---|
| Current authority baseline | `c3db3c037af58dcf7e1906bfe4aa6ae37ac78bcb` (`origin/main` when this register was prepared) |
| Audited provenance baseline | `5139af7848de4925c8326da12f7a53066ad76d7b` for every DS4–DS13 audit |
| In scope | Pending findings and ruling proposals for CV20.DS4–DS13 |
| Out of scope | Product implementation; acceptance of any ruling; changes to canonical DS1–DS3 authority; cutover, deployment, provider mutation, or dependency publication |
| DS1–DS3 use | Dependency context for DS4 and later only; no DS1–DS3 ruling is recorded here |

The only repository commit between the audit baseline and the current baseline
is `c3db3c0` (`docs: preserve CV20 concept analysis`). It added the
non-authoritative concept-analysis worksheets/register and linked them from the
CV20 index. It did not change the architecture, API contracts, delivery
sequence, replacement ledger, Delivery Stories, decisions, dependency pin, or
product code. The added worksheets corroborate several hidden concepts below,
but explicitly say that no concept has been accepted. Therefore no audit
finding is treated as resolved or superseded by that drift. Audit line numbers
are intentionally not copied; headings and named contracts are the stable
anchors.

### Reading labels

- **Canonical decision**: current accepted repository authority.
- **Evidence**: observed repository, dependency, provider, or audit fact.
- **Recommendation**: the audit's proposed choice; not accepted.
- **Unresolved ruling**: a choice the Navigator must make before the owning
  Delivery Story can be design-complete.
- **Blocker**: a missing predecessor, public seam, approval, or contradiction
  that prevents pull or implementation.
- **Dependency**: accepted behavior or unresolved work owned by another story or
  repository.

Here, **DST** means deterministic simulation testing. It does not refer to
daylight saving time.

Reconciliation statuses mean:

- **Current**: still applies at `c3db3c0`.
- **Already resolved**: newer repository authority resolved it.
- **Superseded**: newer repository authority replaced it.
- **Conflicting**: current canonical statements or ownership assignments still
  conflict and require a ruling/correction.
- **Requires revalidation**: external, adjacent-repository, live-state, or
  approval-sensitive evidence must be checked again before implementation.

There are no **Already resolved** or **Superseded** findings in this register.
The current drift added analysis, not rulings.

## Cross-story reconciliation

| Relationship | Current reconciliation | Required future action |
|---|---|---|
| DS3 → DS4 occurrence seam | **Dependency.** DS3 requires exact public pending-Activity identity; DS4 needs the original Engine occurrence at claim and terminal admission. The pinned Petrus `ActivityAttempt` did not expose an explicit occurrence in the audit. | Prove an injective public invocation-to-occurrence projection or add, release, pin, and qualify a public Petrus occurrence reference. Do not modify DS3 in this pass. |
| DS4 marker → DS13 cutover | **Conflict risk.** DS4 fixes `<!-- hamsterdan:readiness operation=<operation> head=<head> -->`; V5 already uses the same marker namespace and a singleton dashboard marker. Lookup can return an existing V5 effect before a canonical fence. | DS13 must rule each V5 marker family as rejected, external reconciliation evidence only, or superseded. An existing marker can never prove the canonical no-return operation. |
| DS5 witness → DS9 ownership | **Conflicting.** DS5 needs a cut-specific currentness proof before protected findings/Pi start, while DS9 says it alone owns `CurrentnessWitness` and lifecycle/currentness completion. | Rule DS5's narrow start-cut witness and host conditional route binding; reserve successor incarnations, movement, convergence, revocation, and the full policy matrix for DS9. Or choose another explicit authority aggregate without reusing `AdmissionGrant`. |
| DS5 accepted delivery → DS6 causal mutation | **Dependency.** DS6's “exact delivered result” must mean rehydration from the same agent-owned accepted-delivery record, not structural equality or Python object identity. | DS5 must settle accepted receiver identity, request/result digests, one accepted terminal, and retention before DS6 can prove causal publication. |
| DS6 Git object/CAS recovery | **Open blocker.** A lost response after blob/tree/commit creation can leave unreachable objects that first-parent lookup cannot discover. GitHub REST `force=false` is not documented expected-old-SHA CAS. | Rule deterministic expected object IDs or durable per-object operation proof, bounded lookup custody, strict trailer/proof grammar, and demonstrate the selected exact-head CAS seam. |
| DS7 ↔ DS8 timers | **Boundary, not a merge.** DS7 is event/evidence-driven and must not add sleeps, TTLs, cooldowns, polling cadence, or elapsed-time flake rules. DS8 owns durable timer command/custody/deadline/wake behavior. | Keep CI episode and rerun/repair budgets in workflow evidence. Route only genuine deferred work through DS8's ruled timer protocol. |
| DS9 → DS10 → DS11 authority/scheduling | **Two conflicts remain.** DS9 owns lifecycle/currentness; DS10 owns unknown discovery and needs atomic register-and-due; DS11 owns fair runnable scheduling. DS10's current text promises registration/enqueue while the initial ledger first assigns catalog/runnable machinery to DS11. DS11 also uses PR-subject cut names for repository targets. | Give DS10 the minimal atomic `ensure registered and reconciliation-due` transaction. Give DS11 the closed `RunnableTarget` union, fair sequence, leases, reason watermarks, and service supervision. Discovery uses host route/configuration preconditions, not a fabricated readiness `AuthorityClaim`. |
| DS12 predecessor proof | **Open blocker.** DS12 says every earlier tracer already owns DST/checker/bounds/correspondence but has no closed-world predecessor-obligation manifest. | Introduce an owner-authored, phase-indexed, append-only obligation manifest. Every acceptance clause maps to a required row; DS12 cannot add, waive, rename, or downgrade predecessor evidence. |
| DS13 ingress and no-return | **Open blocker.** V5 drain state cannot prove the Amp relay has no deliverable old-generation items. Canonical startup can execute retained work unless mutation is persistently denied. | Add durable relay-generation/cut custody, fail-closed old-generation admission, a persistent default-denied single-use mutation permit, and no-return evidence requiring post-cut provider acceptance after that exact permit opens. |

### Adjacent Petrus seams

Current canonical CV20 still cites Petrus
`44cac5ff48ac371ebae56323941983f30db13c0d`. The audits found these public-seam
obligations; none changed at `c3db3c0`:

1. **DS2 transitive blocker:** public bounded
   `accept/resume-one-accepted-unfinished-occurrence` behavior. Internal
   `Instance` access and collapsing `observation_accepted` with
   `observation_folded` remain forbidden.
2. **DS3/DS4:** public injective Activity invocation-to-occurrence identity and
   split claim/effect-observed/terminal-recorded reconstruction. Public lower
   `WorkerDispatch.claim/heartbeat/complete/fail` phases are usable, but
   heartbeat data is not semantic effect proof.
3. **DS5:** public behavior for accepted-and-begun Motus recovery, executing Pi
   process loss, receiver acceptance, retention/eviction, and complete bounded
   runtime supervision. Process death while `EXECUTING` must remain
   `INDETERMINATE` unless a supported resume contract proves otherwise.
4. **DS11:** the minimum page-bounded construction/replay seam established by
   DS1 must be pinned and qualified before real multi-PR composition.

Every item requires revalidation against the exact dependency revision selected
by the owning Plan. A newer Petrus `main` is not evidence until Hamsterdan pins
and qualifies a released public seam.

### Hidden concepts and minimum proposed aggregates

These are audit candidates, not canonical vocabulary:

| Story | Minimum proposed concepts/aggregates |
|---|---|
| DS4 | Exact provider read, one-page candidate acquisition, complete marker lookup, operation-bound provider acceptance, Activity settlement |
| DS5 | Review operation, workflow-authored agent attempt, immutable route bind, runtime terminal, receiver acceptance, cleanup report |
| DS6 | Authorized conversation, accepted delivery, causal mutation work, Git object/publication proof, exact-head ref update |
| DS7 | Exact CI execution evidence, escalation episode, rerun causal witness, bounded repair budget |
| DS8 | Timer command/acknowledgement/maturity, deferral occurrence, deterministic wake, disposable host hint |
| DS9 | Immutable PR root, lifecycle incarnation, operation authority policy, cut-specific currentness witness, late-terminal quarantine |
| DS10 | Repository discovery pass/claim, active-page candidate journal, exact-read registration, reconciliation-due handoff |
| DS11 | Closed runnable target, fairness sequence, fenced lease, reason watermark, retained instance catalog |
| DS12 | Predecessor obligation, journey/overlay catalog, violation fingerprint, correspondence row, qualification envelope |
| DS13 | Relay generation/cut, mutation permit, phase journal, scoped grant, fresh-root proof, no-return acceptance, opaque snapshot custody |

## DS4 — Settle one GitHub Activity lookup-first

### Provenance and current state

- Audit: [DS4 archived audit](https://ampcode.com/threads/T-01a04630-b07c-722a-bc0c-a2b027c7afc3)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete architecture/source audit; read-only; no implementation
  tests. One attempted `uv` inspection was unavailable, while immutable source
  and lock evidence supported the dependency conclusions.
- Current story: `Planned`, not pulled, dependent on accepted DS3.
- Current concept analysis: lookup-first provider effect, provider observation,
  Activity settlement, and operation-specific authority are traced candidates,
  not accepted concepts.

### Finding reconciliation

| ID | Audit finding | Reconciliation at `c3db3c0` |
|---|---|---|
| F1 | DS4 waits on DS3; DS3 waits on DS2's Petrus resume seam. | **Current blocker** |
| F2 | Public attempt lacks an explicit original Engine occurrence. | **Requires revalidation; blocker until proved or added** |
| F3 | DS4 API-strengthening questions remain unresolved. | **Current blocker** |
| F4 | “Durable provider observation” must not become a readiness effect journal. | **Current recommendation; consistent with canonical external-owner recovery** |
| F5 | Durable eligibility after ambiguity is underspecified. | **Current unresolved ruling** |
| F6 | V5 `immutable()` can issue two unproven mutations. | **Current negative precedent; V5 code did not drift** |
| F7 | V5 singleton marker does not bind operation/head. | **Current negative precedent** |
| F8 | Current `WireResponse` lacks complete rate, elapsed-stream, and close evidence. | **Current redesign requirement** |
| F9 | Current `transport.pages()` drains pages and does not fit one-page/list or complete-lookup contracts. | **Current redesign requirement** |
| F10 | General Engine custody guidance differs from CV20's `readiness.runtime` placement. | **Current resolved precedence:** the more specific canonical CV20 architecture governs |
| F11 | “Current/authority fence” can accidentally import DS9's full authority model. | **Conflicting wording; unresolved** |
| F12 | Repository listing can accidentally import DS10 pass custody. | **Current fixed boundary:** DS4 owns only a one-page leaf capability |
| F13 | Indefinitely invisible accepted comments defeat both eventual completion and duplicate prevention. | **Requires revalidation against real provider behavior** |
| F14 | Petrus has no semantic provider-effect-observed journal; heartbeat is opaque operational data. | **Requires revalidation at selected pin; current no-journal recommendation** |
| F15 | Live GitHub mutation was not approved. | **Current approval blocker** |

### Proposed ruling bundles

| Bundle and scenario | Options | Audit recommendation |
|---|---|---|
| A. PR 42 appears on a list page, then closes before exact read. | Generic iterator; broad body-only response; separate exact-read and one-page capabilities. | Separate capabilities. A list page is a transient hint and remains leaf-only until DS10. |
| B. Provider accepts a dashboard write but the response is lost. | Copy V5 singleton; immutable operation-scoped comment; mutable slot with explicit replacement lifecycle. | Prefer immutable operation-scoped publication if product behavior permits. Otherwise rule singleton replacement, old-operation recovery, and marker transitions explicitly. |
| C. Process dies after provider acceptance and before terminal record. | Semantic heartbeat/journal; unresolved Dispatch work; explicit timed defer custody. | Use unresolved Dispatch request/lease plus external marker; no local effect journal. Add timed deferral only if separately required and publicly supported. |
| D. Route revokes between complete absence lookup and POST. | Full DS9 claim; no check; narrow dashboard route/custody safeguard. | Narrow safeguard after lookup and immediately before mutation. |
| E. Provider failures must remain provider-owned while readiness emits `Dash*`. | Generic service/DTO; fake-pure reducer; owner-specific provider effect plus pure classification and host factory. | Owner-specific effect and adapter, direct composition, public Dispatch phases. |
| F. Lookup exhausts while `next` still exists or a body stalls after headers. | Treat status/body as enough; detached hooks; strict proof. | Typed complete/incomplete proof, full-stream bounds, and independent physical/resource counters. |
| G. Fakes pass while SDK retries or a terminal is lost. | Component tests; simulation-only E2E; full vertical plus direct correspondence. | Only the full vertical closes DS4. Live mutation remains explicitly unavailable until approved. |

### Proposed identities, authority, cuts, and recovery

- Preserve the exact marker:
  `<!-- hamsterdan:readiness operation=<operation> head=<head> -->`.
- Read acquisition is `(ProviderRouteId, ProviderReadId)`; a retry that may see
  changed state gets a new read ID.
- Workflow identity is Activity name, Engine occurrence, exact work, operation,
  correlation, and idempotency; for external work
  `correlation == idempotency == operation`.
- Dispatch claim/epoch/lease is a physical attempt, never the business
  operation.
- A compatible existing acceptance requires the exact bot author, final marker,
  expected head, and canonical body/payload. Same operation with incompatible
  content is collision.
- Durable positions remain request/original occurrence,
  `activity_attempt_claimed`, externally observable acceptance,
  `activity_terminal_recorded`, and canonical fold. The observed provider
  result may be process-local between effect and terminal; recovery starts with
  complete external lookup.
- Lookup runs before safeguard. A route revoked after accepted provider work
  cannot erase that acceptance; it prevents only a new mutation.

Minimum aggregates are exact PR acquisition, one open-PR candidate page,
complete marker lookup, one bound publication operation, strict readiness
classification, and public Dispatch terminal admission. DS4 must not add a
discovery pass, currentness witness, lifecycle successor, generic publication
outcome, or generic service layer.

### Bounds and verification obligations

Independently bound request/stream bytes, rows/page, one list-page call, lookup
pages/comments/calls, zero redirects, zero implicit mutation retries, elapsed
deadline, whole-stream permit, rate reserve/`Retry-After`, retained proof bytes,
claims/leases, physical lookups/mutations/acceptances, History/Dispatch rows,
simulation generations, and journal/artifact bytes. Test every chosen limit at
−1 / limit / +1.

TDD must cover each public behavior. Properties cover operation/marker/body
round trips, exact author/final-marker uniqueness, fresh read IDs, Link/rate
parsing, and incomplete-never-absent. Mutation must detect removed lookup,
incomplete-as-absent, a second mutation, singleton markers, omitted body or
terminal identity checks, wrong occurrence, and list/get conflation. DST must
crash at claim, each lookup page, safeguard, hidden acceptance, lease reclaim,
terminal record, collection, and fold with fresh-object replay. Local checkers
consume detached owner evidence; a root substitution leaves them green and
fails only the responsible edge. Real seams are GitHubKit/locked schemas over
mock transport, stream close/rate/Link behavior, public Petrus claim/terminal
reload, fresh SQLite/filesystem, and OS process death. Live mutation is a
separate approval.

### Oracle, targets, and completion

Oracle found DS4 coherent only with external acceptance truth, public lower
Dispatch phases, a narrow dashboard safeguard, leaf-only listing, and an
injective public occurrence mapping. It also identified invisible-acceptance
limits and rejected semantic heartbeat proof. The audit adopted every finding;
the project has not.

Canonical update targets after Navigator ruling: DS4, API contracts, and only
those architecture/ledger entries whose accepted API placement changes.

**Design-complete** requires accepted predecessors and occurrence mapping,
marker/singleton semantics, ambiguity eligibility, safeguard, outcomes,
limits/evidence, and the seven bundles written into DS4/API contracts.
**Implementation-complete** requires the real DS2 observation → DS3 request →
claim → complete lookup/safeguard/one mutation → provider observation → strict
terminal → canonical History completion → original fold route, plus checker,
replay, bounds, correspondence, secret, and gate evidence.

## DS5 — Settle one reconstructible agent round

### Provenance and current state

- Audit: [DS5 archived audit](https://ampcode.com/threads/T-01a04630-c63b-703c-b28d-2e794a7d7d8a)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only report; all nine findings blocking.
- Current story: `Planned`, dependent on accepted DS4.
- Current concept analysis traces durable agent execution, agent execution
  identity, exact delivered result, and authority claim without accepting them.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| B1 | DS5 and DS9 contradict on first usable currentness proof. | **Conflicting; unresolved** |
| B2 | Pre/post provider reads leave revocation gap before Pi admission. | **Current blocker** |
| B3 | Pinned Petrus cannot resume accepted-begun Motus work or an executing Pi process. | **Requires revalidation; blocker** |
| B4 | Retry wording conflates business, Engine, lease, agent, Pi, route, input, terminal, and receiver identities. | **Current blocker** |
| B5 | “Delivered once” is false after lost receiver acknowledgement. | **Current correction:** at most one accepted receiver terminal; finite physical attempts |
| B6 | Runtime outcome and cleanup incorrectly compete as terminal variants. | **Current blocker** |
| B7 | Generic/shallow agent values hide the review domain and mutability. | **Current blocker** |
| B8 | Private-repository workspace source/custody/bounds are unspecified. | **Current blocker** |
| B9 | Per-operation Pi supervision is deferred to DS11 even though DS5 needs it. | **Conflicting ownership; unresolved** |

### Proposed ruling bundles

| Scenario | Options | Audit recommendation |
|---|---|---|
| Route revokes immediately before Pi start. | Defer to DS9; witness without bind; witness plus host expected-generation conditional bind. | Narrow DS5 witness plus host conditional route-binding linearization cut. |
| Settled response is lost or process dies while executing. | Rerun same ID; allocate new ID for all retries; replay same ID for technical loss, indeterminate on process death, new attempt only by workflow. | Third option; separately rule whether pre-start `RoundDeferred` consumes an attempt. |
| Readiness accepts terminal but acknowledgement is lost. | Never retry transport; trust sender bit; query receiver acceptance before bounded retry. | Receiver-acceptance lookup and bounded same-terminal retry. |
| Restart private-repository review without agent credentials. | Tokenized clone; public clone; trusted exact-head archive handoff. | Host/provider creates bounded credential-free archive; agent receives bytes, digest, and correlation only. |
| DS5 needs protocol, Pi, receiver, and start fence but not movement. | Split story; one ordered tracer with DS9 boundary; absorb DS9. | Keep one tracer with ordered Technical Stories and explicit DS9 boundary. |
| Baseline Pi dies during `EXECUTING`. | Private Petrus state; assume claim replay resumes; qualify later public seam and report indeterminate honestly. | Public predecessor seam plus exact pin qualification; never private state. |

### Proposed identities, authority, cuts, and aggregates

Recommended grammars:

```text
review:{subject}:i{incarnation}:sha256:{canonical(head,base,policy)}
pi:sha256(review_operation + "\0" + agent_attempt)
```

Keep PR subject, review operation, Engine occurrence, correlation/idempotency,
Motus lease attempt, workflow-authorized review attempt, Pi ID, route
composition, request/workspace/prompt digests, runtime terminal, receiver
acceptance, Activity terminal, and workflow fold distinct. Route generation is
not part of the stable review operation.

The proposed DS5 witness binds original invocation/grant reference, expected
five-field claim, provider read identity/digest, pre/post route and custody
generations, review operation, and agent attempt. It has no TTL or reuse.
Host conditionally binds the Pi operation to the exact immutable route
composition at expected generations. DS5 promises currentness at accepted
start; result-time currency is a separate witness or later scope.

Primary runtime outcome is `completed | canceled | timed_out | failed |
indeterminate`; cleanup is separately `verified | unverified`. Preserve the
first cause and exact validated `ReviewResult`. The workflow union remains
`AgentReview | RoundDeferred | RoundMoved | RoundUnable`.

Durable positions: `RoundOpen`; Activity claim; exact request/attempt; witness;
conditional route bind; Pi submit/accept; executing/terminal; verified output
and workspace references; receiver acceptance; sender acknowledgement; Motus
terminal; History fold; route settlement; cleanup. Recovery uses the same
attempt/Pi ID for technical replay, `INDETERMINATE` for unresumable executing
loss, and a new ID only for workflow-authored attempt N+1.

Minimum owners remain workflow review, `agents.protocol`, Pi/workspace,
host Pi/routing custody, readiness authority/review custody/effects, and sole
host composition. No generic handler/session/context/service layer is proposed.

### Bounds and verification obligations

Bound protocol/prompt/result sizes; findings and lineage; archive paths,
entries, expanded bytes and ratios; fetch/parse/extract calls; process/FD and
stream/event/tool/session counts; deadlines/cancel/grace/kill/reap/cleanup;
secret lifetime; durable rows/pages/bytes/retention; retries/leases; simulation
steps/faults/generations and artifacts. Exercise every number at
−1 / limit / +1.

TDD covers strict codecs, pair/correlation validation, copy isolation, every
primary-outcome × cleanup state, duplicate/collision receiver acceptance, and
grant/start fencing. Stateful properties cross every retain/witness/CAS/claim/
Pi/acceptance/terminal/fold/eviction cut. Mutation must detect identity or
provenance removal, request/result/workspace/witness swaps, duplicate starts or
acceptance, witness reuse, missing CAS, overwritten first cause, and archive or
credential escape. DST crosses every retain/witness/CAS/claim/Pi/acceptance/
terminal/fold/eviction cut under duplicate delivery, cancellation, crash, and
fresh-generation replay. Owner checkers separately cover agent starts/
terminals, readiness acceptance/fold, host route/resources, and root edges.
Real seams are strict codecs, archive/filesystem safety, SQLite reopen, process
death, public Petrus Pi runtime and Motus claim/complete, cancellation/cleanup
races, and the trusted private archive handoff. Authenticated Pi requires
separate approval or an explicit blocker.

### Oracle, targets, and completion

Oracle confirmed the route-revocation linearization gap, DS5/DS9 ownership
split, distinct Motus/agent attempts, and public-seam problem. The audit adopted
those. Oracle claimed exact output/archive loading was absent; exact-pin review
found public `load_output` and `load_workspace_archive`, so the audit narrowed
the remaining deficits to receiver acceptance, retention/eviction, and
executing-operation resume.

Canonical update targets after ruling: DS5, API contracts, architecture
acceptance-versus-acknowledgement and conditional binding, delivery wording,
DS9/DS6/DS7 alignment, and exact dependency evidence. The ledger changes only
if responsibility changes.

**Design-complete** requires all six bundles, final codecs/grammars/cuts/errors/
bounds, exact later Petrus pin and public seam evidence, and no private-state
workaround. **Implementation-complete** requires
`RoundOpen → request → witness → route CAS → Pi terminal → receiver acceptance
→ Motus terminal → AgentReview fold`, reconstructible at every cut with one
accepted receiver terminal, preserved first cause, checker sensitivity, real
seams, credential scans, and gates.

## DS6 — Publish one causally aligned mutation

### Provenance and current state

- Audit: [DS6 archived audit](https://ampcode.com/threads/T-01a04630-ce42-7589-abbb-69e81a85922e)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only audit with canonical, V5, Petrus, test, and
  Oracle evidence.
- Current story: `Planned`, dependent on accepted DS5; replacement absent.
- Current concept analysis traces authorized conversation, mutation work,
  causal mutation, and Git publication without accepting language or APIs.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| DS6-01 | Public Petrus resume and split Activity positions are missing. | **Requires revalidation; hard predecessor blocker** |
| DS6-02 | Exact accepted-delivery causality is not operationally defined after restart. | **Current blocker** |
| DS6-03 | Conversation provenance and error semantics are underspecified. | **Current blocker** |
| DS6-04 | Repository/workspace/patch/change provenance is insufficiently bound. | **Current blocker** |
| DS6-05 | Digest, Git proof, trailer grammar, `Pushed`, collision, and object/ref recovery are open. | **Current blocker** |
| DS6-06 | Lost object-write responses can create unreachable orphan objects. | **Current Oracle-added blocker** |
| DS6-07 | First-parent lookup is unbounded and cannot safely prove absence. | **Current blocker** |
| DS6-08 | Crash cuts and physical mutation cardinality are too coarse. | **Current blocker** |
| DS6-09 | Mutation-specific fences and terminal taxonomy are open. | **Current blocker** |
| DS6-10 | Call signatures, touched paths, and one-human-change scope remain open. | **Current design blocker** |
| DS6-11 | No executable DS6 evidence bundle exists. | **Current design blocker** |
| DS6-12 | V5/S11 are correspondence only, not DS6 completion. | **Current evidence limitation** |

### Proposed ruling bundles

1. **Public seam.** When one unfinished occurrence must resume, choose a
   released public Petrus API and exact pin; private `Instance`, Coordinator,
   Dispatch, or Worker state is not an option.
2. **Causal delivery.** When an equal-looking result is recreated after restart,
   accept only versioned immutable bytes rehydrated from the same agent-owned
   accepted-delivery identity. Independent History and agent-store provenance
   must agree.
3. **Conversation/authority.** Preserve actor, association, delivery/comment,
   bounded text, intent, frozen authority, edit/delete, collision, unavailable,
   and stale classifications. Do not collapse classifier failures into
   unauthorized.
4. **Git recovery.** A matching publication, bounded scan exhaustion, lost
   object POST, and lost ref CAS need separate proof. Complete trusted-boundary
   traversal alone proves absence. Use deterministic expected object identity
   or durable per-object proof, strict trailers/digests, and exact expected-head
   CAS.
5. **Scope/evidence.** Keep one authorized human change chain under fixed owner
   boundaries and DS1's global gate. Do not introduce generic orchestration or
   a second coding path.

### Proposed identities, authority, cuts, and aggregates

“Exact delivered result” means the value decoded only from the same agent-owned
accepted-delivery record, not Python object identity or structural equality.
Retain logical operation, attempt, execution ID, accepted-delivery ID, request
digest, result digest, workspace/archive identity, canonical patch digest,
provider route/repository, subject, exact checkout commit/tree, and publication
proof.

`AuthorityClaim(phase, incarnation, head, base, policy)` remains fixed.
`MutWork` is independently derived from workflow History. A proposed
publication proof links operation, expected head/parents, repository, request/
result/patch digests, exact tree/commit/new head, authority, and recovered or
accepted disposition. Its final name and trailer grammar remain unresolved.
`Pushed` minimally correlates op-key, expected head, new head, proof/digest, and
the original Activity identity before terminal admission.

Required cuts include conversation retention/classifier lifecycle/manifest/
History fold; `MutWork` request and claim; coding submit/start/terminal/
acceptance/exact lookup; patch admission; every lookup page; each blob/tree/
commit acceptance with hidden response; pre-object and pre-ref authority
fences; ref-CAS hidden acceptance and verification; effect observation;
terminal record; History fold and posture. Rebuild from durable owners at every
cut and expose physical classifier, coding, lookup, object, CAS, terminal, and
fold counts separately.

### Bounds and verification obligations

Bound request/result/patch/archive bytes, paths/modes, repository transfer,
History/agent/Git rows, lookup commits/pages/calls/time and cursor custody,
object writes, CAS attempts, process calls, schedules, artifacts, and all
retained proofs. Test −1 / limit / +1 and classify incomplete lookup as
unavailable, never absent.

TDD begins at each real edge. Properties cover immutable codec/copy behavior,
identity uniqueness, collisions, workspace/patch safety, replay, and complete
lookup. Mutation must detect equal-result substitution, instruction
substitution, omitted result/trailer/proof fields, wrong repository/workspace,
skipped lookup/fence, wrong occurrence, duplicate CAS, or limit exhaustion as
absence. DST crashes at every named cut with fresh generation and semantic
shrinking. Local checkers prove owner invariants; root checkers compare exact
History work, accepted delivery, publication proof, and `Pushed`. Real seams for
Git must exercise actual object IDs, modes, trailers, parents, orphan response
loss, first-parent lookup, and exact ref behavior. Provider/Pi evidence is direct
or an explicit approval blocker.

### Oracle, targets, and completion

Oracle's main additional finding was the orphan/unreachable object
response-loss hole; the audit adopted it. It also confirmed causal provenance,
publication proof, authority, scope, and evidence gaps. The audit narrowed two
points: finite lookup is coherent if exhaustion is unavailable rather than
absent, and DS6 needs mutation-specific authority rather than DS9's whole
matrix. The Oracle's 1–2 day estimate was not accepted as a commitment.

Canonical update targets: DS6, API contracts, and accepted actual source/test
maps in the ledger. **Design-complete** requires those rulings plus accepted
DS1–DS5/Petrus prerequisites. **Implementation-complete** requires replacement
code and tests executing the causal invariant, all cuts/bounds/checkers, and
real Git/public dependency evidence; V5/S11 evidence cannot substitute.

## DS7 — Recover CI and repair escalation

### Provenance and current state

- Audit: [DS7 archived audit](https://ampcode.com/threads/T-01a04630-d643-77a9-9bcd-7a43fbe0beba)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete advisory audit; read-only; Oracle completed.
- Current story: `Planned`, dependent on accepted DS6.
- Current concept analysis traces CI evidence, CI recovery, workflow
  escalation, and repair escalation, without approval.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| F1 | V5 treats greater IDs/timestamps as freshness and escalation evidence. | **Current negative precedent and blocker** |
| F2 | CI execution, policy/App provenance, completeness, classes, operations, limits, and errors are open. | **Current blocker** |
| F3 | Actions rerun and generic Checks rerequest are distinct protocols. | **Current blocker/ruling** |
| F4 | Existing broker/comment marker does not prove operation → provider attempt causality. | **Requires revalidation against chosen provider/broker seam** |
| F5 | V5 escalation fingerprint can collide/reset budgets. | **Current blocker** |
| F6 | Authority and DS8 time boundary need concrete rules. | **Current blocker** |

### Proposed ruling bundles

| Bundle and scenario | Options | Audit recommendation |
|---|---|---|
| A. Correct check name arrives from wrong App; fork webhook omits PR association. | Actions-only first tracer; union Actions and generic Checks. | Actions-only. Retain workflow/run/attempt/suite/job/check/App/repository/ref/SHA evidence; webhook is a wake/acquisition hint. |
| B. Attempt 1 fails; an unrelated same-head run succeeds before the rerun target appears. | Infer from later success; require causal witness. | Require operation-to-target-attempt causality. Unrelated success cannot prove flaky. Different signature becomes bounded inability unless separately ruled. |
| C. Provider accepts rerun POST and process dies. | Broker operation witness; direct App store with proved attribution; remain ambiguous. | Prefer externally discoverable operation-to-attempt witness until direct attribution is proven. Ambiguity cannot authorize repair. |
| D. Implement without collapsing owners. | Generic `CIService`; provider normalization + readiness projection/effect + pure workflow classification/escalation + host injection. | Preserve owner-specific split; no generic service. |

### Proposed identities, authority, cuts, and aggregates

Exact CI evidence binds `BranchTip(repository_id, ref, sha)`, exact policy
identity/digest, required selector plus `app_id`, workflow ID/path/ref/event,
run ID/attempt, suite ID, job/check ID/name/App/status/conclusion, and provider
provenance. Numeric or lexical ordering never proves causality or freshness.

An escalation episode is subject + incarnation + exact source head + policy
identity + exact initial failed execution. Failure signature is diagnostic only.
A `RerunCausalWitness` binds stable logical operation, exact failed source
execution, authored AuthorityClaim, compatible payload digest,
provider-visible acceptance/reference, exact resulting execution, and bounded
operation-to-execution provenance. One logical rerun and one causally aligned
repair are allowed per episode; a repair head does not reset the episode.

Classification: clean requires a complete exact-head inventory satisfying the
exact policy. Flaky requires a causally witnessed target attempt that becomes
completely clean. Persistent requires the causally witnessed target to fail
with the same canonical failure signature. Missing, pending, truncated,
rate-limited, unsupported, contradictory, or ambiguous evidence is waiting,
unavailable, or incomparable. `RerunLanded` records accepted command, not
recovery.

Cuts: exact CI read; manifest stage/admit/fold; rerun request/claim; operation
lookup; authority fence; hidden acceptance; causal acknowledgement; terminal
record/fold; target-attempt admission; DS6 agent delivery/Git/Pushed;
repaired-head evidence; final posture. Lookup accepted operations before a new
fresh three-source fence. Moved/collision consumes no new budget. DS7 adds no
clock-based scheduling.

### Bounds and verification obligations

Bound workflows/runs/attempts/jobs/checks/pages/calls/bytes, provenance,
episodes/signatures, physical POSTs, History/Dispatch, agent/Git operations,
schedules/faults/journals/artifacts. Exercise each number at −1 / limit / +1.

TDD starts with each provider normalization, complete-inventory class, rerun
terminal, workflow escalation, and causal-witness behavior. Properties generate
permutations, redeliveries, greater unrelated IDs/times, wrong App/workflow/
policy, incomplete pages, conclusions, ambiguity, movement, changed signatures,
and repair-head reset attempts. Metamorphic tests remove flake classification
when the causal target is replaced by unrelated success. Mutation kills omitted
head/App/policy checks, operation/attempt confusion, incomplete-as-failure,
ambiguity-as-repair, fingerprint identity, and budget reset. Checkers
independently prove provider→workflow, rerun→target, persistent evidence→
`MutWork`, and `CodingResult→Git→Pushed→new-head` edges. Real seams require exact
provider pagination/rate/response-loss and operation-attribution correspondence,
fresh storage/process death, and separately approved Actions mutation.
DST crosses each inventory, lookup, authority, hidden-acceptance, terminal,
fold, target-attempt, and repair cut with fresh-generation replay.

### Oracle, targets, and completion

Oracle said “block DS7 from being pulled” and identified all six gaps. The audit
adopted Actions-only scope, exact App/policy evidence, distinct identity layers,
causal witness, bounded episode, lookup-first recovery, no timers, and real-seam
requirements. Project adoption remains absent.

Canonical update targets are DS7 and API contracts; architecture/ledger only
if accepted ownership changes. **Design-complete** requires accepted DS6,
bundles A–D, canonical identities/classes/policies/cuts, and a feasible causal
provider seam or explicit blocker. **Implementation-complete** requires clean,
causal-flake, and persistent-regression-through-one-repair verticals, each with
negative causality, crash reconstruction, exact counts, bounds, checkers,
replay, and provider correspondence.

## DS8 — Recover timers and deferred work

### Provenance and current state

- Audit: [DS8 archived audit](https://ampcode.com/threads/T-01a04630-df74-752b-b660-247c650761f3)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only audit; Oracle completed.
- Current story: `Planned`, dependent on accepted DS7.
- Current concept analysis traces timer, timer custody, and deferred work but
  accepts no fields, grammar, or term.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| F1 | Timer and deferral identities are not canonical. | **Current critical ruling** |
| F2 | Fold-before-delivered-mark order is not explicit. | **Current critical ruling** |
| F3 | Integer logical-time transition semantics are incomplete. | **Current high ruling** |
| F4 | DS8 liveness must stop at known-subject open/step/restart; DS11 owns unattended multi-PR progress. | **Current clarified boundary** |
| F5 | History recovery precedence and durable-store loss behavior are unspecified. | **Current high ruling** |
| F6 | Retention/capacity and recurring-reminder behavior are unspecified. | **Current high ruling** |
| F7 | “Exactly once” overstates the guarantee. | **Current correction:** semantic idempotency plus at-least-once external attempts |
| F8 | Public Petrus accepted-unfinished resume seam is missing. | **Requires revalidation; external blocker** |

### Proposed ruling bundles

1. **Identity/one-shot scope.** Duplicate host hints around a crash must derive
   the same canonical timer or deferral identity. Derive a timer-arm identity
   from version, subject/incarnation, workflow source occurrence, and purpose;
   derive command/ack/due from it. Derive one deferral occurrence from subject,
   incarnation, original Activity occurrence, stable operation, and exact
   deferred terminal; derive exactly one wake. Do not add cancellation/
   rescheduling in initial DS8.
2. **Durable order.** A crash after History acceptance but before fold must not
   let a premature local mark suppress the fold. Apply command → retain ack →
   History accept → `observation_folded` → mark exact ack delivered. Use the
   same order for maturity and deferred wake. Replay the oldest unfinished stage
   first.
3. **Time semantics.** Use validating integer instant/duration/generation/
   sequence values. Reject bool, overflow, negative duration, backward advance,
   and out-of-range generation. Due at `now_us >= due_at_us`; checked addition;
   frozen due and first `matured_at_us`; duplicates cannot rewrite them.
   `Timeline.advance` performs no implicit work.
4. **Hints/DS11.** Early, duplicate, late, lost, or corrupt hints only trigger
   custody inspection. DS8 guarantees progress when a known subject is opened,
   stepped, or restarted; DS11 owns fair autonomous supervision.
5. **Store loss.** Use existing bounded History page/one-occurrence repair. If
   exact retained ack cannot be established after real store loss/corruption,
   return typed non-retryable unavailability; never fabricate or rearm.
6. **Finite recurrence.** Prefer a finite workflow-visible horizon/refusal.
   Indefinite reminders require a separately proved compaction/checkpoint
   contract.

### Proposed identities, authority, cuts, and aggregates

Minimum concepts are reminder timer, timer command operation, deterministic
acknowledgement, immutable maturity, review/announcement deferral occurrences,
their deterministic wakes, disposable host deadline hint, and reminder effect
operation derived from matured timer. Host hint identity never enters canonical
identity. External effect operation remains stable across restart and preserves
the exact DS4 marker grammar.

Custody cuts remain apply one command, read oldest ack, History accept/fold,
mark exact ack, claim earliest maturity, read oldest maturity, History
accept/fold, mark exact maturity, and accept/fold/mark deferred wake. One call
handles at most one item. Custody receives explicit `now_us`; it never reads the
clock. Wake hints are reconstructible from retained custody.

### Bounds and verification obligations

Name and bound command/live/terminal rows and bytes; pending ack/maturity;
History page records/bytes/cuts; deferred candidates/facts; hints; clock reads;
eligible actions; logical time; owner steps; generations; journal and artifact
bytes. Exercise −1 / limit / +1 and finite capacity refusal.

TDD covers arm/application, duplicates/collisions, due−1/due/due+1, delayed
maturity, review/announcement deferral, and every crash cut. Property tests
generate command generations, time advances, duplicate hints, crashes, SQLite
faults, and resource edges. DST schedules every apply/retain/accept/fold/mark/
maturity/wake cut with fresh-generation replay. Mutation must detect comparator
changes, due recomputation, missing collisions, wrong order, mark-before-fold,
hint trust, float conversion, wrong deferral identity, multi-item calls, and
constructor drains. Local/root checkers prove command/ack/maturity/reminder/
deferral edges. Real seams require SQLite WAL interruption, fresh child-process
reopen, real integer host clock/early wake behavior, and static sole-clock
ownership.

### Oracle, targets, and completion

Oracle supplied the duplicate-hint/duplicate-deferral interleaving and the
audit adopted it. It also narrowed the work: paging already exists; normal
commit retains ack; only real store loss fails closed; autonomous multi-PR
liveness belongs to DS11; effect dedupe is sufficient once identities are
canonical.

Canonical update targets: DS8 and API contracts; delivery sequence for the
DS8/DS11 liveness boundary and Petrus prerequisite; architecture only if owner
boundaries change; ledger test/owner mapping as needed. **Design-complete**
requires every identity, API, cut, error, liveness, retention, and bound ruling
written into both DS8 and API contracts. **Implementation-complete** requires
the full workflow→custody→clock→workflow→established-effect vertical with all
recovery, replay, checker, real-store/clock, and gate evidence.

## DS9 — Fence lifecycle and authority changes

### Provenance and current state

- Audit: [DS9 archived audit](https://ampcode.com/threads/T-01a04630-e9a6-7787-a501-d548387aa475)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only audit; Oracle challenge completed.
- Current story: `Planned`, dependent on accepted DS8.
- Current concept analysis traces current authority, lifecycle authority,
  currentness witness, and known-subject reconciliation, without accepting the
  proposed semantics.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| F1 | “Durable readiness grant” is undefined and cannot mean `AdmissionGrant`. | **Conflicting canonical wording; blocker** |
| F2 | DS9 calls close/merge terminal while requiring reopen/successor movement; V5 permanently absorbs close. | **Conflicting lifecycle semantics; blocker** |
| F3 | Universal “no stale physical effect” is impossible across read/effect races. | **Conflicting guarantee; blocker** |
| F4 | Canonical per-operation authority/terminal matrix is absent. | **Current blocker** |
| F5 | Conflict can change while five claim scalars remain equal. | **Current blocker** |
| F6 | Public Petrus accepted-unfinished resume seam is missing. | **Requires revalidation; external blocker** |
| F7 | Witness fields, cuts, bounds, correspondence, and terminal mappings are open. | **Current blocker** |

### Proposed ruling bundles

1. **Root/incarnation.** If operation N is accepted, PR closes, the effect lands
   hidden, and the same unmerged PR reopens, retire N and create successor N+1
   under the same immutable PR root. A merged root has no successor. Closed N
   may lookup-settle historical operations but never claim or authorize N+1.
2. **Authority basis.** Do not reuse `AdmissionGrant` or invent a mutable latest
   grant. Use the exact durable Activity invocation/operation with its authored
   `AuthorityClaim`, compared with History lifecycle state, fresh provider
   evidence, and fresh host route/custody evidence.
3. **Operation matrix.** Adopt explicit operation-specific policies and closed
   terminal mappings. Do not replace reply/reminder/dashboard safeguards with a
   generic strongest fence.

Recommended race-aware invariant:

> No new effect is claimed after movement is known. An already-attempted
> operation remains lookup-reconcilable under its original identity, but cannot
> revive its retired incarnation or authorize a successor.

### Proposed identities, authority, cuts, and aggregates

Keep immutable PR root, root-local monotonic incarnation, exact
`AuthorityClaim(phase, incarnation, head, base, policy)`, durable Activity
invocation/operation, cut-specific `CurrentnessWitness`, host route/custody
generations, ingress/admission facts, History lifecycle proof, effect-owner
lookup, Petrus lifecycle scope, and late-terminal quarantine distinct.

The proposed witness binds subject, operation/occurrence, authored claim,
provider read identity/snapshot digest, History lifecycle comparison cut,
route/custody generation before and after, and one cut identity. It has no TTL
or general latest-truth use. Current requires all five fields, active route, and
stable pre/post generations. Successor/retirement or semantic difference is
stale/moved; unorderable evidence is incomparable and returns through DS2
refresh; revoked/moving/unavailable evidence refuses; incompatible bytes under
one identity collide.

The proposed matrix preserves weaker lookup/context safeguards for reply,
dashboard, and reminder; full claims for findings, announcement, rerun, review
start, mutation, and Git publication at their ruled cuts; transactional timer
identity; and the existing asymmetric closed terminal unions. Exact unavailable
mapping for rerun remains a ruling because its union lacks a blocked variant.

Cuts: invocation/claim; generation-before; exact provider read; changed
snapshot through DS2 stage/classify/accept/fold; generation-after; witness;
lookup; effect observation; terminal record; workflow fold; lifecycle
close/reset commit; cancellation/late quarantine. Crash before effect reacquires
witness; hidden acceptance uses lookup; retired terminals settle only as old
incarnation evidence; `settle` cannot claim new work.

### Bounds and verification obligations

Bound exact reads/bytes, mergeability retries, deadlines, generation rereads,
movement retries, closed-unmerged watch retention, History pages/turns,
evidence/witness rows/bytes, lookups/effect attempts, terminal/blocker/journal/
artifact retention, processes/generations/faults/checkers. Exercise
−1 / limit / +1.

TDD and properties cover lifecycle/action sequences and every bound. Mutation
must kill omitted claim fields, inverted generation checks, witness reuse,
revoked-route acceptance, accepted/fold collapse, and wrong terminal mapping.
DST injects movement at every read/fence cut and crash at every durable cut.
Owner checkers use detached evidence; edge substitutions leave locals green and
fail only the root edge. Real-seam correspondence covers lifecycle webhooks,
repeated unknown mergeability, transport, exact selected Git ref semantics,
fresh storage/process death, and separately approved provider mutation.

### Oracle, targets, and completion

Oracle blocked DS9 as written and recommended terminal N + same-root N+1,
lookup-only historical settlement, an untouched `AdmissionGrant`, and a
root-level distinction between closed-unmerged reopen eligibility and merged
terminality. The audit adopted all points; project adoption remains absent.

Canonical update targets: a Navigator lifecycle/incarnation decision record,
DS9, API contracts, architecture's undefined durable grant and known-subject
wording, and only affected sequence/ledger entries. **Design-complete** requires
the lifecycle/root/authority rulings, exact witness/matrix/mappings/cuts/bounds,
accepted DS8, and explicit pull. **Implementation-complete** requires every
established real effect under its explicit policy and every lifecycle movement
ending in a typed outcome, with complete race/crash/replay/bounds/
correspondence evidence. A standalone claim test or generic fence is not enough.

## DS10 — Discover unregistered open PRs boundedly

### Provenance and current state

- Audit: [DS10 archived audit](https://ampcode.com/threads/T-01a04630-f0d3-712a-9e2b-596f38e00d40)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only audit; Oracle completed.
- Current story: `Planned`, dependent on accepted DS9.
- Current concept analysis traces configured-repository discovery and discovery
  pass but does not resolve pass completion, journal, or registration custody.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| F1 | “Open through one completed pass” is not guaranteed by mutable offset pagination. | **Conflicting with current liveness wording; blocker** |
| F2 | Pass boundary lacks candidate journal, completion predicate, and fenced claim/CAS. | **Current blocker** |
| F3 | Route/configuration and installation-wide rate authority/error semantics are underspecified. | **Current blocker** |
| F4 | DS10 promises atomic registration/enqueue while DS11 first owns catalog/runnable machinery. | **Conflicting ownership; blocker** |
| F5 | Adjacent Petrus effect-position/public factory seams remain blocked. | **Requires revalidation against selected pin** |
| F6 | Numeric limits, continuation, leases, tooling, markers, and signatures remain Plan decisions. | **Current unresolved refinement** |

### Proposed ruling bundles

1. **Operational completion.** Mutable pages can shift `[D,C] [B,A]` to
   `[C,B] [A]`, skipping B even while B remains open. Reject an atomic-snapshot
   or “open throughout one pass” guarantee. A completed pass proves terminal
   pagination plus durable drain of every retained candidate under recorded
   correspondence. Eventual discovery requires appearance on a retained page
   or a sufficiently quiescent interval. Page ETags are local only; crash or
   takeover restarts page 1; uninterrupted traversal follows the exact Link.
2. **Pass custody and DS11 handoff.** If the terminal page lists X and process
   dies before exact read, a next-page-only boundary loses X. Persist a bounded
   normalized active-page candidate journal, pass ID, lease epoch, row revision,
   explicit disposition, and fenced completion. DS10 owns atomic/idempotent
   `ensure registered and reconciliation-due`; DS11 later owns fair selection.
3. **Configured authority/rate/errors.** Before every list/exact-read verify
   configured repository, active route generation, pass claim, and shared
   installation reserve. Registration CAS binds the exact read and current
   route/configuration. Bare `404` is `not_found_or_inaccessible`, not proof of
   missing; `403/429` use header-aware rate classification. Unknown discovery
   uses host transaction preconditions, not a readiness `AuthorityClaim`.

### Proposed identities, cuts, and aggregates

Keep `RepositoryDiscoveryPass`, explicit `RepositoryDiscoveryPassBoundary`,
last-completed inspection evidence, and `UnknownPullRequestDiscovery`. Add a
fenced pass claim and bounded candidate journal. Completion requires terminal
page, empty journal, durable matching registration-and-due for every eligible
candidate, no retryable provider/rate/route ambiguity or overflow, and current
claim/route correspondence.

Preserve exact cuts `repository_discovery_page_listed`,
`repository_discovery_candidate_classified`, and
`repository_discovery_pass_completed`; fence every write by pass ID, lease
epoch, and revision. Discard provider reads returned after lease/route loss.
Exact read precedes registration; list summaries never enter History; repeated
pages, restart, overlap, webhook race, and crash produce one binding and one due
known-subject path. List absence never closes or proves completeness.

### Bounds and verification obligations

Bound page size (GitHub maximum 100), pages, candidates, physical calls,
response bytes, journal rows/bytes, duration, leases, defers, shared rate
reserve, artifacts, and resource peaks. `Link` at the page cap is incomplete,
not complete. Account for physical calls such as PR and base-ref GET. Exercise
every chosen number at −1 / limit / +1.

TDD proves list summaries cannot register, exact read precedes registration,
and register+duty is atomic. Property tests generate mutable pages, overlap,
addition/removal, restart, webhook race, process crash, lease takeover, and
route movement. Full-state assertions pin boundary, journal, claim epoch,
binding, due reason, collision, and completion. Mutation kills removed scope/
read/lease/reserve guards, collision refusal, atomic duty, or completion
predicate. Independent checkers consume detached page/read/transaction traces.
DST supplies finite schedules, shrinking, exact replay, and resource peaks.
Real seams cover GitHub list/get/Link/rate/304/403/404/429, SQLite/filesystem,
process death, and separately approved read-only live list/get correspondence.

### Oracle, targets, and completion

Oracle independently found mutable-pagination liveness, candidate-journal,
route/rate/error, and DS10/DS11 ownership blockers. The audit adopted operational
completion and DS10-owned atomic register-and-due, rejecting deferral to DS11.

Canonical update targets: DS10, API contracts, delivery sequence, replacement
ledger, DS11, DS12, references, and the existing configured-repository recovery
decision if the Navigator changes its liveness claim. **Design-complete**
requires the completion ruling and agreement across those owners on pass state,
journal, claim, errors, rates, collisions, bounds, and evidence.
**Implementation-complete** requires one unknown eligible configured PR to traverse real list →
exact read → idempotent register-and-due → known-subject recovery, with all
page/race/crash/rate/absence/checker/replay/correspondence evidence and no
snapshot/completeness claim.

## DS11 — Supervise multiple PRs fairly

### Provenance and current state

- Audit: [DS11 archived audit](https://ampcode.com/threads/T-01a04630-f86a-7688-b3b2-fc12fb56f470)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only audit; Oracle completed.
- Current story: `Planned`, dependent on accepted DS10; replacement absent.
- Current concept analysis traces multi-PR supervision, durable fairness,
  runnable custody, and instance catalog without accepting scheduler semantics.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| DS11-R1 | PR subject cannot identify repository-discovery work. | **Current blocker** |
| DS11-R2 | Lease expiry/late completion lacks fencing and finalization rules. | **Current blocker** |
| DS11-R3 | Terminality, catalog retention, hints, corruption, and missed reopen are underspecified. | **Current blocker** |
| DS11-R4 | Process topology/startup/drain/cancel/close permit incompatible implementations. | **Current blocker** |
| DS11-C1 | DS11 orders discovery-pass completion before registration, contradicting DS10. | **Conflicting; correction required** |
| DS11-C2 | `subject_selected/requeued` cannot cover repository targets. | **Current correction required** |
| DS11-C3 | Rollback preserves DS9 instead of accepted DS10. | **Current correction required** |
| DS11-C4 | DS11 risks taking DS12 portfolio qualification ownership. | **Current correction required** |
| DS11-C5 | `instances.py` versus DS10 `discovery.py` ownership needs explicit correction. | **Current correction required** |
| DS11-B1 | DS10 must expose protected-capacity deferral. | **Current dependency blocker** |
| DS11-B2 | DS1 public Petrus construction/replay seam must be pinned/qualified. | **Requires revalidation; dependency blocker** |
| DS11-B3 | V5 `RunnableIndex` is unsafe precedent. | **Current historical warning** |

### Proposed ruling bundles

1. **Runnable target/fairness.** Use a closed `RunnableTarget` union of known PR
   (`PRSubject`) and configured-repository discovery binding. Do not fabricate a
   PR subject or run separate incompatible schedulers. Select the lowest enqueue
   sequence among due, unleased, non-deferred targets; eligibility is a
   predicate. Every completion/failure/expiry/still-runnable result receives a
   fresh tail sequence. DS10 protected reserve overrides fairness and returns a
   visible future-eligible defer.

   Proposed fairness invariant:

   > For any finite cohort of continuously eligible, due, unleased targets,
   > continued claims plus bounded completion/expiry select every cohort member
   > before any selected member receives a second claim.

2. **Lease/reasons/finalization.** A stale generation-4 turn returning after
   generation-5 takeover must not overwrite posture or clear a new wake. Claims
   carry target identity, process generation, monotonic lease fence, expiry,
   captured reason-generation watermark, and bounded reason snapshot. Claim,
   renew, repair, and finalize use exact-fence CAS; finalize consumes only
   reasons at or below its watermark. Newer reasons force tail requeue. Reasons
   are bounded typed hints; overflow coalesces to “inspection required.”
3. **Catalog/terminality.** Retain immutable subject/root binding after close or
   merge; terminal means runnable dormancy and resource close, not identity
   deletion. A listed known terminal PR is a hint to enqueue its known-subject
   exact-read path. Reconstruct from catalog + exact owner custody + bounded
   readiness inspection + clock, never History scan. Corrupt sequence/lease
   authority fails visibly or starts an explicit new fairness epoch.
4. **Process topology.** One host process generation owns a root and runs a
   finite pool of independent turns, at most one live claim per target. Capacity
   must demonstrate at least two PRs. Startup validates/open stores, walks a
   finite catalog without keeping lifecycles loaded, records per-binding
   failures, and begins after initial cohort establishment. Shutdown stops
   claims, tells readiness to stop new effects, drains to a deadline, fences
   results, independently cancels/closes, requeues only after old work stops,
   and closes shared resources last with aggregate failures.

### Proposed cuts, authority, bounds, and verification

Generalize cuts to `runnable_target_selected` and
`runnable_target_requeued`; do not add compatibility aliases. Known-PR turns
call readiness zero or one time; discovery turns call it zero times and advance
one DS10 cut. Discovery registration schedules a later PR turn. Lease is
scheduler authority, never exactly-once effect authority; all provider,
delivery, route, and workflow effects retain owner-specific lookup/CAS.

Bound rows/bytes, sequence capacity, lease/renewal/expiry, active turns/loaded
instances, startup/shutdown/deadlines, calls/reserve, retry/defer, inspection,
API/CLI, and artifacts, each at −1 / limit / +1.

TDD covers target identity, fairness, lease, reasons, startup/shutdown, and
one-call turns. Properties cover idempotent enqueue, one live fence, stale
refusal, no lost leased enqueue, tail ordering, cohort fairness, reserve defer,
terminal binding retention, and independent close aggregation. Mutation must
detect reversed order, stale fence, cleared post-claim wake, deleted binding,
readiness called twice/from discovery, reserve spend, trusted posture, or
short-circuited close. DST uses two PRs plus repository target, all enqueue/
expiry/finalize/terminal/reopen/reserve/startup/shutdown races, fresh replay,
and semantic shrinking. Host/root checkers independently derive scheduler and
edge truth. Real seams cover multi-connection SQLite contention/CAS, process
restart, slow-PR isolation, FastAPI lifespan, independent close failure, and
physical resource/effect peaks. SQLite correspondence does not authorize
multiple processes sharing one root.

### Oracle, targets, and completion

Oracle blocked Plan confirmation and found all four bundles plus the DS10
ordering, reserve, retention, rollback, and process-topology corrections. The
audit adopted them, narrowing multi-connection SQLite to in-process concurrency
under exclusive root ownership. Process-kill evidence remains separately
approved.

Canonical update targets: DS11, API contracts, architecture, DS10, delivery
sequence, replacement ledger, and boundary corrections in DS9/DS12 only if
needed. **Design-complete** requires bundles A–D, DS10 defer, corrections C1–C5,
qualified Petrus construction/replay, and explicit process topology.
**Implementation-complete** requires at least two real readiness lifecycles and one discovery
target under production composition, complete tests/checkers/real seams/bounds,
real startup/shutdown and hint recovery, disabled effect-free operator surfaces,
and no DS12 backfill of missing DS11 evidence.

## DS12 — Qualify journeys and real-seam correspondence

### Provenance and current state

- Audit: [DS12 archived audit](https://ampcode.com/threads/T-01a04630-fff9-765e-b3d6-ef67cebb0989)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete archive review through all messages and Oracle.
- Current story: `Planned`, dependent on accepted DS11.
- Current concept analysis correctly says DS12 introduces no production-domain
  concept; it does not resolve evidence ownership or completeness.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| F1 | No append-only predecessor-obligation manifest proves DS1–DS11 completeness. | **Current blocker** |
| F2 | Twelve names are not a versioned journey/probe catalog. | **Current blocker** |
| F3 | Live GitHub mutation and authenticated Pi are approval-dependent but not explicitly required. | **Current approval/contract blocker** |
| F4 | No ruled semantic-shrink fingerprint. | **Current high ruling** |
| F5 | Checker, coverage, and mutation obligations are not closed/sensitivity-proven. | **Current high ruling** |
| F6 | Correspondence is seam-category rather than claim-level with physical counts/non-equivalence. | **Current high ruling** |
| F7 | Qualification-envelope provenance is unspecified; process-kill evidence can be mislabeled as replay. | **Current high ruling** |
| F8 | Campaign tiers, numeric profiles, resource/marker/coverage/mutation policy remain open. | **Current high refinement** |
| F9 | Secret scans lack canary sensitivity. | **Current medium ruling** |
| F10 | DS12 distribution meaning is ambiguous; installed production must remain V5-only through DS12. | **Current medium ruling** |
| F11 | `host/operator.qualification` may be the wrong aggregate report owner. | **Current ownership ruling** |
| F12 | DS2 Petrus resume seam remains blocked. | **Requires revalidation; transitive blocker** |

### Proposed ruling bundles

1. **Predecessor manifest.** A loose aggregate can pass while an original
   checker or identity drifted. Use an owner-authored, phase-indexed append-only
   obligation manifest from DS1. Every acceptance clause gets a row. Separate
   `required-at-owner-acceptance` from `required-at-DS12`; supersede by appended
   record, never rename/downgrade/delete. `Unavailable` is evidence, never pass.
2. **Journey/overlay catalog.** Replace a count of names with a versioned
   catalog and required/not-applicable overlay matrix with rationale. Decide
   whether causal exact-delivered-result publication is a user journey or a
   mandatory contract probe.
3. **Shrink/replay.** Preserve a `ViolationFingerprint` containing obligation/
   checker/property version, owner/cross-edge, checkpoint, expected/observed
   semantic digests, and ending class. Original, shrunk, and fresh replay must
   match; harness/budget/cleanup failure cannot replace the primary violation.
4. **Checkers/coverage/mutation.** Coverage witnesses are checkpoint-scoped and
   require executable adapter + passing relevant checker + detached semantic
   outcome + exact replay. Maintain curated risk→mutant→expected-checker
   manifest; expected survivors block.
5. **Correspondence/approvals.** Claim-level rows bind claim, real seam, fixture,
   expected observation, physical counts, bound, and known non-equivalence.
   Live GitHub mutation and authenticated Pi are conditional in their owning
   tracers but required at DS12 under explicit approval; withheld approval
   reports `unavailable: approval_missing` and blocks acceptance.
6. **Envelope/resources/secrets/distribution.** Use content-addressed evidence
   bound to revision/dependencies/fixtures/capability fingerprints, canary
   secret scans, and a clear V5-only installed distribution rule through DS12.
   DS13 owns the renamed canonical wheel/image.

### Identities, cuts, bounds, and verification

The catalog preserves current operation, acquisition, observation, History,
marker, branch-tip, authority, and agent identities. A human mutation grant
also binds admitted delivery, operation, intent digest, full authority,
mutation head, and coding/Git effect reference. Minimum durable owners remain
host custody/catalog/runnable/resources, readiness ingress/grant/effects/timers,
workflow observations/folds/manifest/Activities, provider transport/lookup,
and semantic-free simulation mechanics.

The predecessor manifest must cover every inbound, Activity, agent, Git,
timer, authority, catalog/runnable, and discovery cut named in the delivery
sequence. Every cut discards process-local state and reconstructs from durable
owners. Physical attempts, external acceptance, terminals, and folds are
separate evidence.

Bound every public command/call/startup/shutdown/artifact in bytes, rows,
History records/pages, calls, attempts, retries, time, actions/leaves,
draws/faults/generations, journal/artifact bytes, pending Activities, loaded
instances, custody rows, retained terminals, and workspace/archive bytes. Test
−1 / limit / +1 and lowering a budget as typed refusal/replayable failure.

The required portfolio remains the twelve named entries plus applicable timer,
revocation, hidden-acceptance, close/merge, known/unknown recovery, and fairness
overlays. Every entry declares initial state, input, production call tree,
visible outcome, authority, operations, physical counts, cuts, limits, checker
IDs, schedule dimensions, correspondence rows, and artifacts. Quick/full/
release profiles retain the canonical cumulative gate. Independent checkers
must not derive expected truth from production reducers. Real seams include
public Petrus, raw GitHub HMAC/transport/live mutation, Git objects/ref, Pi/
workspace/authenticated Pi, SQLite/filesystem/process death, timers/leases/
concurrency, discovery/rate, and installed source/wheel/CLI/disabled service.
TDD applies to qualification-envelope parsing, catalog/overlay selection,
manifest completeness, checker sensitivity, shrink/replay identity, and report
outcomes. Properties generate manifest/catalog/overlay permutations, evidence
substitutions, truncation, missing approvals, and resource edges. DST executes
the versioned journey catalog and required overlays with fresh-generation
replay and semantic shrinking. Mutation follows the curated
risk→mutant→expected-checker manifest; every expected survivor blocks. Any
production behavior gap discovered while qualifying returns to the predecessor
tracer that owns it; DS12 records the missing obligation and must not implement
or redefine that behavior.

### Oracle, targets, and completion

Oracle said the ledger is necessary but insufficient; every acceptance clause
needs a row, required phases must be separate, supersession append-only, DS12
cannot manufacture predecessor evidence, and approval-dependent live GitHub/Pi
must become DS12-required. It also required production-equivalent capability
fingerprints. The audit adopted all findings.

Canonical update targets: DS12, API contracts, delivery sequence, ledger,
owner-authored DS1–DS11 obligation rows, and an accepted qualification/report
owner. **Design-complete** requires the manifest, catalog/matrix, schemas,
requiredness, commands, correspondence, approval classes, artifact identities,
and numeric profiles. **Implementation-complete** means every declared row
executes and induced defects fail through the intended checker while shrink/
replay preserves identity. **Qualification-complete** additionally requires
exact-candidate reruns and approved live GitHub/Pi evidence before DS13.

## DS13 — Cut over and remove V5

### Provenance and current state

- Audit: [DS13 archived audit](https://ampcode.com/threads/T-01a04631-0742-706d-bdae-52b892d628f3)
- Audited baseline: `5139af7848de4925c8326da12f7a53066ad76d7b`
- Audit report: complete read-only audit; Oracle completed; no cutover or shared
  action authorized by the audit.
- Current story: `Planned`, dependent on accepted DS12 and separate cutover
  approval.
- Current concept analysis traces the final-language filter, opaque rollback
  custody, and no-return as cutover safeguards, not accepted API design.

### Finding reconciliation

| ID | Audit finding | Reconciliation |
|---|---|---|
| P0-1 | Persistent mutation permit and relay ingress generation/cut are absent. | **Current blocker** |
| P0-2 | V5 marker ownership and canonical no-return evidence are undefined. | **Conflicting marker/cutover semantics; blocker** |
| P0-3 | Durable journal/phase invariants are unspecified. | **Current blocker** |
| P0-4 | “Navigator/operator approval” conflates distinct authorities. | **Current blocker** |
| P0-5 | Ordinary V5 rollback after canonical accepted work is unsafe. | **Current blocker/correction** |
| P1-6 | DS12 pre-rename evidence does not qualify the changed post-rename artifact. | **Current required ruling** |
| P1-7 | Fresh-root and old-access removal are underspecified. | **Current required ruling** |
| P1-8 | Deletion ledger omits repository/runtime/distribution surfaces. | **Current required ruling** |
| P1-9 | `hamsterdan2 → hamsterdan` is an import-package rename; distribution is already `hamsterdan`. | **Current required correction** |
| P1-10 | Strict isolated replacement gate must become default without weakening. | **Current required ruling** |
| P1-11 | Finite cutover bounds are absent. | **Current required ruling** |
| P1-12 | Distribution/secret verification is not exhaustive, especially image layers and build token. | **Current required ruling** |
| P1-13 | Historic CV19 deployment evidence is not current deployment authority. | **Requires revalidation immediately before any shared action** |
| P1-14 | Reversible cuts and irreversible/destructive actions are not classified. | **Current required ruling** |
| P1-15 | No single ruling bundle joins current decisions, DS12 evidence, target, relay/marker, phases, grants, bounds, and rollback. | **Current required ruling** |
| P1-16 | Completion is not machine-readable enough. | **Current required ruling** |

### Proposed ruling bundles

1. **Ingress generation, marker ownership, and mutation permit.** A delivery can
   be retained/processed by V5 while the relay loses receipt validation and
   later retries into canonical fresh state. V5 can have already emitted the
   same marker namespace, and canonical lookup can return `existing` before a
   fence. Add a durable relay generation/cut, inventory/drain/quarantine of all
   old-generation deliverables, fail-closed old-generation canonical
   admission, and persistent default-denied mutation permits. Rule each V5
   marker family as reject, reconciliation evidence only, or supersede. No
   existing lookup result can satisfy no-return.
2. **Journal, grants, and rollback.** Use durable idempotent phases:

   ```text
   prepared → V5 mutation-fenced → relay cut recorded → V5 unresolved=0
   → snapshot verified → canonical artifact staged → fresh root verified
   → canonical running mutation-denied → no-return grant spent
   → one post-cut effect accepted/reconciled → committed/cleanup
   ```

   Split grants for Plan, local preparation/history, shared stop/fence/snapshot/
   stage/deploy, no-return live effect, post-effect cleanup, and later
   destruction. Bind each to revision/evidence/target/expiry/spent state.
   Before no-return, rollback restores old package/snapshot and discards fresh
   roots. After no-return, default to fenced canonical forward-repair; any V5
   restart needs a new exceptional ruling.
3. **Post-rename artifact and fresh root.** Bind DS12 report/revision to the
   post-rename revision through machine-readable no-semantic-drift evidence and
   rerun release/journey/correspondence/install/image checks. Fresh roots must be
   absent/empty, real non-symlink ancestry, exact owner/mode, canonical schema
   marker, physically separate/inaccessible across runtimes, and guarded by a
   closed environment allowlist.
4. **Census, gate, bounds, and secrets.** Extend deletion disposition across
   package metadata/lock/scripts/CI/services/relay/setup/env/container/release/
   deployment/systemd/docs, distributions, clean installs, OCI files/config/
   history/layers, caches, and bytecode. Promote the strict replacement gate.
   Bound drain/relay/snapshot/census/artifact/startup/journal/operation work and
   test −1 / limit / +1. Secret scans cover every build/distribution/image/
   runtime layer without disclosing secrets, especially
   `PETRUS_GITHUB_TOKEN`.
5. **Deployment, irreversible actions, and completion.** Re-observe and bind
   current VM/service/container/image/unit/config/App/install/repository/relay/
   root identities immediately before action. Classify preparation, stop/fence,
   relay cut, snapshot, stage, fresh validation, external no-return, cleanup,
   and later deletion separately. One ruling packet includes current decisions,
   accepted DS12 digest, exact target, phase machine, grants, markers, bounds,
   rollback, and machine-readable completion. Explicitly supersede the V5-only
   operational decision.

### Authority, cuts, bounds, and verification

A mutation permit is persistent, default-denied, single-use, restart-safe, and
bound to exact operation, authority, revision, report/artifact/image/config/
unit/install digests, environment, target, expiry, and spent state. Relay
generation is durable custody independent of V5 state. A provider acceptance
after that exact canonical permit opens is no-return; lookup evidence alone is
not.

Crash before/after every phase write and external acknowledgement. Ambiguous
V5 operations block because canonical cannot read old state. Every phase resumes
or stops closed; process exit proves nothing. Snapshot custody remains opaque,
read-only, and access-controlled. Old-state deletion, image/tag cleanup, secret
rotation/revocation, VM deletion, App/webhook changes, release/publication,
commit, and push are separate actions, not implied by cutover.

Bound snapshot files/bytes/time; V5 unresolved rows/operations/pages/calls/
time; relay backlog; census files/bytes/matches/time; wheel/image members/
layers/bytes; startup/restart/deadlines/retries; journal/evidence bytes/
retention; and exactly one approved no-return operation. Any unknown,
truncation, timeout, or budget refusal keeps mutation denied.

TDD starts with journal, census, distribution, fresh-root, and permit tests.
Property/DST covers every phase/crash, relay receipt loss, hidden provider
acceptance, package install, fresh filesystem/process death, and deployment
staging. Mutation targets the post-rename canonical tree. Checker/gate evidence
promotes the strict replacement gate and runs release after rename. Real seams
cover relay custody ambiguity, marker lookup/hidden acceptance, filesystem
isolation, process death, clean install, image/layer inspection, and inactive
deployment staging. Secret checks use non-disclosing canaries and residue scans.

### Oracle, targets, and completion

Oracle supplied the relay receipt-loss sequence in which V5 publishes effect E,
the old delivery retries into canonical, and `existing` is falsely credited as
canonical no-return. The audit adopted the relay-generation cut, old-generation
admission refusal, and post-permit provider-acceptance requirement. It retained
an external uncertainty: the inspected relay plugin exposed no pause,
generation, inventory, or drain API; another Amp facility was not verified.

Canonical update targets after ruling span CV20's active index/sequence/
architecture/API/ledger/DS13, roadmap/briefing/README/AGENTS/process/gate,
active decisions/debt/operator/deployment, package/lock/scripts/CI/setup/env,
relay/services, and distribution/deployment files. Dated history remains
unchanged provenance.

**Design-complete** requires the ingress/marker/phase/grant/target/bounds/
fresh-root/rollback/deletion/distribution/secret/completion ruling packet.
**Implementation-complete** requires all thirteen stories accepted, explicit
shared-action approval, exact post-rename artifacts, one mutation authority,
canonical-only relay generation, fresh state with no old reader, zero forbidden
active matches, explicit V5 ruling supersession, no active old package/image/
config, and spent temporary grants with cutover selectors/commands removed.
Opaque old snapshot custody may remain; deletion is outside CV20 completion.

## Navigator review order

The audits are linear and should not be ruled as ten isolated designs. A safe
review order is:

1. Resolve the adjacent Petrus occurrence/resume seams that block DS2–DS5.
2. Rule DS4 marker/publication semantics and narrow safeguard.
3. Rule DS5 accepted-delivery identity, narrow start witness, route bind, and Pi
   process-loss behavior.
4. Rule DS6 accepted-delivery causality and Git object/ref recovery.
5. Rule DS7 causal Actions evidence and keep time in DS8.
6. Rule DS8 identity/order/time/retention and its DS11 liveness boundary.
7. Rule DS9 root/incarnation/authority basis and operation matrix.
8. Rule DS10 operational pass completion and atomic register-and-due.
9. Rule DS11 runnable-target fairness, lease fencing, terminal retention, and
   process topology.
10. Rule DS12's predecessor manifest and qualification catalog before treating
    any aggregate report as cutover evidence.
11. Rule DS13 relay generation, marker disposition, mutation permit, phase
    journal, grants, and no-return before any shared cutover action.

At each step, accepted decisions must move into the owning canonical DS/API/
architecture/decision records. This register remains provenance and should not
be edited into a substitute acceptance record.
