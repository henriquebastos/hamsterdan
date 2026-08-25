# ES-009 candidate review

Captured 2026-08-24 from `main` at `33494f1` and extended at `1546b11` after the
reminder-timer journey. This review compares the clean-green, automatic-repair,
Git-ambiguity, and reminder-recovery journeys. It separates modules that earn
their depth from friction that may justify Refinement.

No candidate is pulled by this document. Production behavior, test behavior,
package contents, and operator behavior remain unchanged.

## Navigator disposition

On 2026-08-24, the Navigator ruled that this ES-009 session remains dedicated to
human learning. Every actionable finding is captured for another session, and
all Change Requests remain parked:

- [RS-021](../../workbench/rs-021-fence-inline-v5-activities-after-route-revocation.md)
  owns inline Activity fencing after route revocation;
- [RS-022](../../workbench/rs-022-retain-mutation-fault-until-recovery-terminates.md)
  owns fail-closed mutation recovery until a known terminal;
- [RS-023](../../workbench/rs-023-inspect-current-v5-activity-identities.md)
  owns current V5 operator inspection;
- [RS-019](../../workbench/rs-019-improve-v5-test-reading-locality.md)
  owns the amended semantic-journey and reminder-evidence locality changes;
- [RS-024](../../workbench/rs-024-consolidate-import-architecture-rules.md)
  owns import-rule test consolidation;
- [RS-025](../../workbench/rs-025-make-v5-maintainer-route-explicit.md)
  owns the maintainer route, current terminology, and local documentation; and
- [RS-026](../../workbench/rs-026-clarify-full-gate-build-ownership.md)
  owns the full-gate build contract; and
- [RS-027](../../workbench/rs-027-define-reminder-eligibility-and-stopping-policy.md)
  owns the reminder eligibility and stopping-policy question.

[RS-020](../../workbench/rs-020-fail-closed-on-missing-canonical-history.md)
continues to own destructive canonical-History loss. Retired pre-V5 source and
test-support packaging remain with the
public release preparation.
The raw-History projection and Pi response-descriptor ideas remain unpromoted
signals below until recurring change or performance evidence supplies a trigger.

## Overall assessment

The current V5 production path has deep modules with distinct seams:

- `HostService` owns runtime custody and concrete composition.
- webhook custody owns verified, sanitized, durable provider ingress;
- V5 ingress owns atomic manifest and host-grant admission;
- `V5Runtime` adapts Hamsterdan's topology to Petrus Engine, History, Dispatch,
  Worker, and recovery;
- the concern loops own separate durable workflow decisions;
- typed Activities keep provider and agent effects behind host-owned seams;
- the mutation gate, Git publisher, provider authority, and GraphQL transport
  own different authority checks; and
- agent protocol validation, Pi execution, and route custody own different
  parts of credential-free agent work.

The deletion test does not support a broad production reorganization. Removing
one of these modules would move its invariants into a caller with a different
responsibility. Large files on the three journeys are navigation signals, not
proof that their modules are shallow.

The initial review found three correctness or operator candidates, two
test-locality candidates, and a small maintainer-navigation candidate. The
fourth journey added one test-evidence locality request and one product-policy
question. Other signals remain deferred or rejected below.

## Candidate 1: fence inline Activities after route revocation

### Finding

A persisted PR with an inactive installation or repository route can still open
from its strict V5 binding so canonical History may settle. Durable publication
Activities pass through `HostService._guard_durable_activity`, which checks the
current registry route before a provider call. The five identified inline
Activities execute through `InlineDispatch` and do not pass through that guard:

- `review_agent`;
- `publish_gate`;
- `rerun_gate`;
- `git_gate`; and
- `reminder_gate`.

The inline gates perform lookup-first recovery, which is necessary. After a
lookup proves that an operation is absent, their claim readers compare the host
grant and fresh provider truth but do not check whether the host registry still
admits the installation and repository.

Concrete scenario: an unresolved `git_gate` survives a restart, the repository
route is then revoked, and startup settles the PR's intact History. Reconciliation
must still be allowed to prove that the old operation already landed. If lookup
proves absence, current code can continue toward agent execution and Git
publication without a current registry-route check.

### Evidence

- `src/hamsterdan/host/service.py`: `_application`, `sweep`,
  `_activate_instance`, and `_guard_durable_activity`;
- `src/hamsterdan/host/v5/runtime.py`: `_CompositeDispatch` and
  `V5Runtime.open`;
- `src/hamsterdan/readiness/net_v5/gating.py`:
  `DURABLE_PUBLICATION_GATES` and `_IDENTIFIED_INLINE_GATES`;
- `src/hamsterdan/host/v5/application.py`: Activity composition and
  `current_claim`;
- `src/hamsterdan/host/v5/mutation.py`: `V5MutationGate.git_gate`; and
- `tests/integration/host/test_service.py`:
  `test_v5_revoked_route_settles_instance_queue_as_typed_blocked_without_provider_calls`,
  which covers only the three durable publication gates.

A read-only exploration probe observed an unresolved inline `git_gate` reaching
publisher reconciliation after route suspension. The branch from absent lookup
to later agent and provider work follows directly from the gate code, but this
review did not execute a provider mutation after revocation.

### Candidate boundary

Preserve lookup-first reconciliation. Once lookup proves absence, require current
registry admission before any new agent execution, comment, rerun, reminder, Git
object write, or ref compare-and-swap.

Add restart tests for each inline Activity under a revoked route:

- an existing marker or commit settles without a duplicate effect; and
- an absent operation produces no new external or agent effect.

Likely files include `host/service.py`, the V5 application composition seam, and
focused host restart tests. The design must avoid giving provider or agent
packages registry knowledge.

### Assessment

This is a high-priority correctness candidate. It reinforces the settled
host-custody architecture rather than contradicting it.

## Candidate 2: retain mutation ambiguity until recovery terminates

### Finding

A mutation fault is global because it must survive admission of a newer head.
`mutation._recover` currently clears that global fault when a human authorizes a
new proof attempt. It also emits a pending mutation fact under the original
incarnation.

When the provider head has already entered lifecycle as a newer incarnation,
readiness ignores the stale pending fact but applies the global fault clear. The
snapshot can therefore become ready while the replacement `git_gate` Activity is
still unresolved.

Concrete scenario:

1. Git publication moves H0 to H1 but ends as durable `FaultM`.
2. H1 enters lifecycle as incarnation 2 and its CI, review, and human facts are
   green.
3. A human authorizes recovery of the original incarnation-1 operation.
4. The replacement `git_gate` remains held without a terminal.
5. Readiness ignores its incarnation-1 pending fact, clears the global fault,
   and can mark incarnation 2 announced.

### Evidence

- `src/hamsterdan/readiness/net_v5/mutation.py`: `_fold_fault` and `_recover`;
- `src/hamsterdan/readiness/net_v5/readiness.py`: `_current`,
  `_apply_mutation_pending`, `_apply_fault_cleared`, and the authorize mailbox
  inhibitors;
- `tests/unit/readiness/net_v5/test_mutation_loop.py`:
  `TestFaultAndRecovery`; and
- `tests/integration/testing/test_readiness_world.py`:
  `test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash`.

A held-Activity reproduction using the existing V5 harness left `git_gate`
pending while `ready.snap` for incarnation 2 had an empty pending ledger, an
empty fault ledger, and `announced == [1, 2]`.

Production currently executes `git_gate` through `InlineDispatch`, which usually
runs the gate and Engine advancement serially. The unsafe ordering is proven in
the supported topology harness, but this review did not prove that the current
single-owner production composition can pause at that exact cut. Crash and
future Dispatch changes still make the invariant worth expressing directly.

### Candidate boundary

Keep the operation-keyed mutation fault until the replacement Activity records a
known terminal. `Pushed`, `MovedM`, or `DeclinedM` may clear it. A repeated
`FaultM` must retain or replace it.

Add a held recovery test after head-first admission and green incarnation-2
evidence. Assert that readiness cannot authorize before the recovery terminal.
Include crash cuts after recovery admission, after `ActivityRequested`, and
before terminal projection.

Likely files are `readiness/net_v5/mutation.py`, typed fault-settlement wiring,
and focused mutation, readiness, and World tests.

### Assessment

This is a high-priority correctness candidate with one explicit confidence
limit: topology reachability is proven, while current production reachability is
not.

## Candidate 3: inspect current V5 Activity identities

### Finding

The read-only `inspect-instance` command assumes that every Activity request has
`input.work.operation` or `input.command.operation`. Current V5 work types use
several identity fields, including `op`, `op_key`, `id`, `digest`, and
`timer_id`.

Concrete scenario: a valid unresolved `mut.git_gate` request contains
`work.op_key`. `inspect-instance` reads only `work.operation` and raises
`ValueError("Activity operation is malformed")` instead of reporting the
unresolved operation.

### Evidence

- `src/hamsterdan/host/__main__.py`: `inspect_instance`;
- `src/hamsterdan/readiness/net_v5/gating.py`:
  `DurablePublicationActivityHandler.prepare` and
  `IdentifiedInlineActivityHandler.prepare`;
- `src/hamsterdan/host/agenticus.py`: current mutation operation extraction;
- `tests/integration/host/test_service.py`:
  `test_instance_inspection_is_bounded_and_excludes_payloads_and_errors`, which
  uses former synthetic `execute.*` records with an `operation` field; and
- `docs/operator/README.md`, which directs operators to this command.

### Candidate boundary

Give inspection one sanitized operation-identity decoder for every current V5
Activity type. Test it against real V5 History for unresolved, completed, failed,
malformed, and colliding records. Continue excluding request payloads and error
text from output.

Likely files are `host/__main__.py`, a current V5 identity helper under a neutral
host owner, and focused operator/host tests.

### Assessment

This is a bounded operator correctness candidate. Its failure is direct and does
not depend on a concurrency schedule.

## Candidate 4: improve V5 test reading locality

[RS-019](../../workbench/rs-019-improve-v5-test-reading-locality.md) remains the
right owner for two existing changes:

1. assert directly that H1 is green but mutation ambiguity still blocks
   readiness before recovery; and
2. construct `JourneyResult` with keyword arguments.

The review found the same positional-construction problem in `DraftPhase`,
`StaleBasePhase`, and `CollaborationPhase` inside the shared journey runner.
Extending the second Change Request to name all four aggregate constructions
would give the test module one consistent rule without redesigning the harness.

The reminder-timer journey added a third parked request under RS-019. The fixed
World resolves its lost provider response before the later host crash, while a
reminder-loop repeated-maturity test stops at the exact-clock guard before a
second lookup. Their names should distinguish response recovery, terminal-loss
recovery, timer reconstruction, and stale maturity suppression.

The candidate remains test-only. Splitting the 2,500-line semantic journey file
is not justified by the deletion test.

## Candidate 5: give import architecture rules one test owner

### Finding

Two test modules scan production imports:

- `tests/test_architecture.py` resolves relative imports and checks sibling and
  host-only composition rules; and
- `tests/unit/host/test_host_architecture.py` repeats the sibling rule with a
  scanner that does not resolve relative imports, while also owning several
  unique architecture assertions.

Concrete scenario: `from ..agents import X` resolves to `hamsterdan.agents` in
the root scanner but appears only as `agents` in the host-unit scanner. The
nominally duplicate rules do not interpret the same source syntax.

### Candidate boundary

Let `tests/test_architecture.py` own all repository import-direction rules using
its relative-aware scanner. Move the unique import assertions there. Keep the
credential-free request-field assertion in the host unit area because it tests a
contract rather than repository imports.

This is a two-test-file consolidation with no production behavior change.

## Candidate 6: make the maintainer reading route explicit

The three ES-009 journeys form a useful vertical reading route once a maintainer
finds the exploration index. The normal README path lists production modules but
does not link to those journeys.

A bounded documentation and terminology refinement could:

- add direct README links to clean green, automatic CI repair, and ambiguous Git
  recovery;
- correct `docs/project/briefing.md` so it says runtime projections are rebuilt
  from intact canonical History, rather than saying canonical History itself is
  reconstructible;
- add the observed test-layer taxonomy to `docs/process/development-guide.md`;
- clarify that `real_provider_acceptance` is an intentionally reserved opt-in
  marker;
- rename private `_terminal_operations` to describe logical agent operations
  settled by History; and
- add a semantic `lose_git_publication_response` Timeline helper while retaining
  the accepted low-level `ref_cas` fault vocabulary.

These are separable Change Requests. They should not be used to rename durable
V5 colors or operation identities.

## Candidate 7: define reminder eligibility and stopping policy

### Finding

Current V5 reminder eligibility follows lifecycle rather than human readiness.
An active head starts a recurring timer; draft pauses it; ready-for-review
resumes it; close ends it. Human approval and readiness publication do not enter
the reminder loop.

Concrete scenario: the deterministic World requires zero approvals, has no
requested reviewer, and publishes readiness. Timer maturity still asks the
author to assign a reviewer and arms the next timer. Existing product documents
do not state whether every active PR should receive this cadence or whether a
named human-readiness blocker should control it.

### Candidate boundary

Require a product ruling before changing or blessing the behavior. If the
lifecycle policy is retained, document it and characterize ready and approved
PRs directly. If eligibility becomes blocker-driven, name the exact facts and
cover cancellation, resumption, stale maturity, response loss, and head movement
without moving policy into host timer custody or provider rendering.

Likely files depend on the ruling. The behavior owner remains the readiness Net;
`V5TimerStore` remains a policy-free custody adapter.

### Assessment

This is a product-policy candidate, not evidence of a shallow module or an
immediate production defect. RS-027 captures it without pulling implementation.

## Deferred signals

### Retired pre-V5 source vocabulary

`contracts/readiness.py` and `readiness/payloads.py` retain substantial former
workflow vocabulary. A current maintainer can encounter unsupported concepts
while searching the production package. Some current neutral values and paused
explorations still refer to these files.

The existing post-production open-source audit already owns disposition of
historical executable residue. Removing or relocating these modules before CV19
would add release scope without a current runtime benefit. Keep this signal for
that audit.

### Distribution status of test support modules

`hamsterdan.testing` and `hamsterdan.host.testing` call themselves supported test
surfaces and ship in built artifacts, but no external package consumer is known.
Their source ownership is sound: the independent model remains neutral and
host-owned World composition stays under `host`.

Whether these modules are source-only support or a distributable test kit is a
package-contract decision. Defer it to the post-production package and
open-source audit rather than mixing it into ES-009 or CV19.

### Duplicate build in the full gate

`scripts/check full` builds directly, then `tests/test_distribution.py` builds
again to inspect wheel and source artifacts. The responsibilities overlap, but
the current macOS shell cannot run the Bun-dependent full gate and this review
did not measure the cost or prove that no external workflow expects `dist/`.
Keep the signal until the full environment is available.

### Repeated raw History interpretation

`V5Runtime` scans raw History for ingress, active publications, operation
settlement, timers, and wake integrity. A typed History projection might improve
locality, but the scans are already concentrated in one module and no performance
or change-error evidence supports a new module yet.

### Pi prompt and validator coupling

The Pi adapter imports private field sets and validators from the agent protocol,
then separately renders model-facing instructions. Parity tests currently catch
drift. Wait for another real protocol change before introducing a shared public
descriptor.

## Refactorings rejected by the evidence

- Do not split `host/service.py`, V5 ingress, V5 timers, readiness, or
  `contracts/readiness_v5.py` by size alone.
- Do not collapse lifecycle, CI, escalation, mutation, review, conversation,
  dashboard, reminder, and readiness loops. Each owns a durable decision and
  baton.
- Do not consolidate host grants, lifecycle admission, gate claim reads, Git
  publisher checks, and exact ref compare-and-swap. They fence different race
  cuts.
- Do not merge provider transport, provider authority, publication gates, and Git
  publication. Their interfaces hide different implementations.
- Do not replace `repair` with `change`. Automatic repair is evidence-authorized;
  conversational change is human-authorized.
- Do not globally rename `generation` to `incarnation`. Host-process,
  independent-model, and lifecycle counters have different owners.
- Do not rename durable `FaultM` or `ProvisionalHead` types from this
  exploration.
- Do not split the shared semantic journey laboratory without a concrete
  locality failure beyond the bounded RS-019 changes.
- Do not move real-Engine Net tests out of `tests/unit/readiness/net_v5`; that
  layer isolates the Net from host and provider effects.

## Validation and limits

Executed during this review:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest -q -p no:cacheprovider \
  tests/unit/readiness/net_v5/test_mutation_loop.py \
  tests/integration/testing/test_readiness_world.py::test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash \
  tests/integration/host/test_service.py::test_v5_revoked_route_settles_instance_queue_as_typed_blocked_without_provider_calls \
  tests/integration/host/test_service.py::test_instance_inspection_is_bounded_and_excludes_payloads_and_errors
```

Result: 35 passed in 6.32 seconds.

The reminder-timer extension executed 59 focused Net, timer, application, host,
World, gate, and publisher tests plus the generated reminder campaign. All 60
passed. The campaign completed in 17.49 seconds with one Hypothesis warning that
the recursion limit changed during execution.

A separate read-only harness reproduction held the replacement `git_gate` after
head-first recovery admission and observed incarnation 2 marked announced before
that Activity terminal.

No live provider route, authenticated operation, host launch, production state,
OS-level process kill, or package build was used. The full project gate was not
rerun. The baseline's Bun and macOS GNU `stat` limits still apply.
