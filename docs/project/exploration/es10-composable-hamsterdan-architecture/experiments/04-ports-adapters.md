# Experiment 4 — Readiness ports and effect adapters

Session S4. Durable inputs: the ES-010 index and the ruled Phase A records,
[`01-ownership-map.md`](01-ownership-map.md) and
[`02-value-ownership.md`](02-value-ownership.md). Source inspected at commit
`0796ec2`. S3 was not used as an experiment input; its index-recorded handoff is
honored: readiness supplies Activity implementations and consumes the
workflow-owned `MANIFEST`, `GATES`, and `wire_gates`; workflow `gating.py` stays
whole.

Method: trace every current effect from workflow work token through production
execution and typed terminal, then trace the equivalent deterministic model in
`host/testing`. For each seam, apply four tests:

1. the interface names a readiness need, not a GitHub, Pi, Petrus, HTTP, or
   storage API;
2. production and deterministic implementations can satisfy it without
   patching readiness;
3. operation identity, ordering, ambiguity, and authority remain explicit; and
4. deleting or merging the port would either erase a distinct invariant or
   improve the interface.

## Verdict

Readiness should not receive one broad `GitHubPort`, `AgentPort`, or generic
`EffectPort`. Those interfaces would combine operations with incompatible
authority and error semantics:

- a denied immutable comment becomes a retryable `Blocked` terminal;
- the same denial for a rerun becomes an ambiguity-preserving `Fault`;
- clean agent inability becomes `RoundUnable` or `DeclinedM`;
- a Git ref response loss becomes `FaultM` and must reconcile against commit
  trailers before another agent call; and
- timer custody is a durable local protocol, not an external effect.

The smallest honest injection seam is eight capability groups:

1. provider evidence projection;
2. current-authority evidence;
3. conversation classification;
4. the five comment-publication Activities;
5. rerun Activity execution;
6. review Activity execution;
7. mutation Activity execution, internally split into coding and Git
   publication; and
8. clock plus timer custody.

The Activity ports reuse workflow-owned work and terminal values directly. No
second request/result vocabulary is needed. Non-Activity ports use
readiness-owned values. `contracts` remains empty.

```text
host composition
  |
  +-- provider evidence adapter --------> readiness evidence port
  +-- current-authority adapter ---------> readiness authority port
  +-- conversation adapter --------------> readiness conversation port
  +-- production Activity adapters ------> readiness Activity ports
  |     publication / rerun / review / mutation
  +-- system clock ----------------------> readiness clock port
  +-- timer store factory ---------------> readiness timer-custody port

readiness application
  |
  +-- freezes evidence into workflow observations
  +-- supplies Activity implementations to workflow MANIFEST wiring
  +-- drives timer commands and observations through timer custody

deterministic readiness simulation
  |
  +-- implements the same eight groups directly
  +-- never patches the application or swaps its execution path
```

## Exact port candidates

The following is capability-signature pseudocode, not production code and not a
recommendation to implement Python `Protocol` interfaces. Names and concrete
injection form follow the ruled the engineering style contract style contract in Delivery; the method
sets and value ownership are the experiment result.

### Evidence and authority

```python
class EvidencePort:
    def project(
        self,
        *,
        event: str | None,
        action: str | None,
    ) -> tuple[HeadSeen | DraftSeen | ReadySeen | CloseSeen | HumanSeen | RunSeen, ...]: ...


@dataclass(frozen=True)
class AuthorityClaim:
    phase: Phase
    incarnation: int
    head: str
    base: str
    policy: str


class AuthorityPort:
    def current(self) -> AuthorityClaim: ...
```

`EvidencePort` is the provider-to-workflow normalization seam currently hidden
behind `V5IngressNormalizer` and `GitHubAuthority`. Source delivery identity and
door identity do not enter this port; readiness custody stamps them when it
freezes the projection. The production adapter may import `github_app`; the port
does not.

`AuthorityPort.current()` is stronger than a provider snapshot. It succeeds
only when no same-PR webhook custody is unstaged, a fresh provider read agrees
with the durable readiness grant, and all five fields are available. The claim
value is readiness-owned because it expresses authority to execute one workflow
operation. It replaces current `host/v5/claim.py` and the mixed composition in
`PrReadinessV5Application.current_claim()`.

Evidence unavailability raises a readiness-owned boundary failure before a new
fact or effect is accepted. Provider exceptions and response objects never
cross either port.

### Conversation classification

```python
@dataclass(frozen=True)
class ConversationWork:
    delivery_id: str
    comment_id: int
    text: str
    association: str
    actor_id: int
    actor_login: str
    authority: AuthorityClaim


class ConversationPort:
    def classify(self, work: ConversationWork) -> CommentSeen: ...
```

The host/provider bridge projects the GitHub-owned `AdmittedConversation` into
this readiness-owned task. The production adapter may import both `github_app`
and `agents`; neither package appears in the port. Classification uses stable
operation
`conversation:{repository}:pr:{number}:delivery:{delivery_id}`. It completes
before the immutable ingress manifest is staged, checks provider currency
during the agent attempt, and returns one authorized or unauthorized workflow
observation. Once staged, the manifest owns the result and the agent route can
settle idempotently.

### Activity implementations

```python
class PublicationActivities:
    def reply(self, work: ReplyReq) -> Replied | ReplyBlocked | ReplyFault: ...
    def publish_findings(
        self, work: Publishable
    ) -> ReviewLanded | ReviewMoved | ReviewBlocked | ReviewFault: ...
    def dashboard(
        self, work: DashReq
    ) -> DashLanded | DashDeferred | DashBlocked | DashFault: ...
    def remind(self, work: RemReq) -> RemLanded | RemBlocked | RemFault: ...
    def announce(
        self, work: AnnounceReq
    ) -> ALanded | ADeferred | AMoved | ABlocked | AFault: ...


class RerunActivity:
    def rerun(self, work: RerunReq) -> RerunLanded | RerunMoved | RerunFault: ...


class ReviewActivity:
    def review(
        self, work: RoundOpen
    ) -> AgentReview | RoundDeferred | RoundMoved | RoundUnable: ...


class MutationActivity:
    def mutate(self, work: MutWork) -> Pushed | MovedM | FaultM | DeclinedM: ...
```

These candidate methods map one-to-one to the implementations consumed by the
workflow-owned Activity manifest. Their arguments and successful
classifications are already workflow-owned. The readiness ports therefore add
no wrapper values and do not repeat the manifest's declarations.

An Activity implementation returns only its declared workflow terminals for
classified outcomes. Provider errors, agent protocol values, Git publication
errors, and deterministic fault objects do not cross the port. A raised
exception means an unclassified implementation or infrastructure failure, not
a business terminal.

### Clock and timer custody

```python
class Clock:
    def now_us(self) -> int: ...


@dataclass(frozen=True)
class TimerMaturity:
    value: TimerDue
    identity: str


class TimerCustody:
    def apply(self, command: TimerCommand) -> TimerCommandApplied: ...
    def pending_ack(self) -> TimerCommandApplied | None: ...
    def mark_ack_delivered(self, operation: str) -> None: ...
    def pending_maturity(self) -> TimerMaturity | None: ...
    def claim_due(self) -> TimerMaturity | None: ...
    def mark_maturity_delivered(self, timer_id: str) -> None: ...
    def next_due_us(self) -> int | None: ...
```

Store construction also receives accepted `TimerCommandApplied | TimerDue`
history and the one outstanding `TimerCommand` so it can rebuild or fail closed.
That construction belongs to readiness composition in S5; it does not need a
factory method on the live port.

The target clock uses signed integer microseconds. The current timer store
already persists that unit but converts `next_due()` to `float`; the replacement
port need not introduce the lossy conversion. Agent runtime timeout clocks,
webhook retry clocks, and the host runnable clock remain with their own owners.
They are not one readiness clock merely because a deterministic simulation will
synchronize them later.

## Port and adapter matrix

| Port group | Readiness need and owned values | Current production evidence | Deterministic evidence | Target owner |
|---|---|---|---|---|
| Evidence | Project current provider truth directly into workflow observations; no source identity | `host/v5/ingress.py:142-256` over `github_app/gateway.py` | `ReadinessProviderTruth` already supplies pull, policy, human-review, and run truth through strict undeclared-request failure | `readiness/ports.py`; provider bridge under `readiness/effects` or the S5-owned ingress grouping |
| Authority | Fresh complete `AuthorityClaim`; fail while same-PR custody is unstaged or provider truth differs from grant | `application.py:188-211`, `ingress.py:485-530` | modeled authority plus independently admitted grant/effect-authority checks in `readiness_world.py:899-938` | `readiness/authority.py` implementing `readiness/ports.py` |
| Conversation | One admitted message to one `CommentSeen` under a stable delivery operation | `application.py:263-318` over `AgentRunner.converse` | strict `AgentRunner.converse`, exact operation/attempt terminals, undeclared-operation failure | `readiness/effects/agents.py` implementing `ConversationPort` |
| Publications | Five workflow Activity families with family-specific terminals | `host/v5/gates.py` over `github_app.effects.CommentPublisher` | modeled comment ledger supports accepted-hidden, response-lost, collision, reveal, and lookup recovery | `readiness/effects/publication.py` implementing `PublicationActivities` |
| Rerun | One same-head rerun request with a final pre-request evidence cut | `host/v5/rerun.py` over `CommentRerunBroker` | provider truth already models exact-head runs and strict comment operations; a local adapter can expose the same terminal union directly | `readiness/effects/rerun.py` implementing `RerunActivity` |
| Review | Freeze exact credential-free request; run one authority-cancellable review attempt | `host/v5/review.py`, `V5ReviewRequestStore`, `AgentRunner.review` | exact operation/attempt review terminal and current-authority callback in the modeled runner | `readiness/effects/review.py`; request store under `readiness/custody` |
| Mutation | Reconcile before agent work; code once; recheck authority; publish with exact ref CAS | `host/v5/mutation.py` plus `host/git_publish.py` | modeled coding terminal plus `ModeledGitPublisher`, including accepted ref update with lost response | `readiness/effects/mutation.py` orchestrates; `readiness/effects/git.py` owns publication |
| Clock + timers | Apply serialized timer commands, deliver acknowledgements and maturities exactly once into History, expose next deadline | `host/v5/timers.py` with injected clock and History reconstruction | current World injects one logical clock and independently checks timer custody | `readiness/custody/timers.py` implementing `TimerCustody`; clock through `readiness/ports.py` |

### Forbidden-value check

The candidate signatures contain only:

- workflow values accepted at the ruled R1 seam;
- readiness-owned authority, conversation, and timer-custody values;
- scalar operation identities and integer time; and
- typed terminal unions already declared by the workflow.

They contain no GitHubKit client, HTTP request/response, installation token,
credential, Pi runtime or operation, Petrus `Engine`, `Dispatch`, `Worker`, or
simulation truth. Concrete production adapters may hold those collaborators;
concrete deterministic adapters may hold modeled truth. Neither leaks them into
readiness state or port values.

## Operation matrix

| Operation | Stable identity | Required ordering and authority | Classified no-effect outcome | Ambiguous or failed outcome | Recovery |
|---|---|---|---|---|---|
| Reply | `reply:{comment_id}` across heads | Lookup first; only if absent, lazily read incarnation/head for the provider marker. No full authority fence by design. | Definitive publication denial or bounded boundary exhaustion → `ReplyBlocked` | collision or unclassified status → `ReplyFault` | exact text retained; reissue same identity; lookup precedes context read |
| Findings publication | `findings:{head}:i{incarnation}` with a canonical findings digest in content | Lookup; compare full phase/incarnation/head/base/policy; publish | authority drift → `ReviewMoved`; capability denial or bounded exhaustion → `ReviewBlocked` | collision/unclassified status → `ReviewFault` | exact findings retained; same operation and compatible accepted rendering |
| Dashboard upsert | `dash:{digest}` request identity over one singleton board | In quiescent phase defer. Otherwise upsert without a provider-authority fence; workflow baton keeps one write in flight. | quiescent → `DashDeferred`; denial/exhaustion → `DashBlocked` | collision/unclassified status → `DashFault` | exact attempted entries/digest retained; desired state travels separately and self-heals after landing |
| Reminder publication | `reminder:{timer_id}` across heads | Presence lookup first; only if absent, lazily read current addressing. No full authority fence by design. | denial/exhaustion → `RemBlocked` | collision/unclassified status → `RemFault` | presence-only lookup under same identity; body may legitimately drift with recipients/dashboard link |
| Readiness announcement | workflow `ready:{head}:i{incarnation}` | Lookup; block on unstaged same-PR custody; compare full claim and strict-base evidence; publish | custody barrier → `ADeferred`; authority drift → `AMoved`; denial/exhaustion → `ABlocked` | collision/unclassified status → `AFault` | deferred wake names exact blocker; blocked reuses operation; held lookup precedes authority |
| CI rerun | workflow `rerun:{lineage}:{fingerprint}`, bound to indicted run/head | Held lookup; full claim; locate indicted run; broker's final run read establishes the evidence cut immediately before POST | claim/run movement or broker pre-effect refusal → `RerunMoved` | every unproven outcome, including denial or lost response → `RerunFault` | exact request retained; same identity; held lookup precedes claim and run reads |
| Agent review | `review:{subject}:{head}:i{incarnation}`, plus attempt | Defer on unstaged custody; recover/freeze exact request; full claim; invoke agent with continuous-current callback; recheck custody after return | authority drift → `RoundMoved`; custody barrier → `RoundDeferred`; classified agent inability → `RoundUnable` | unclassified provider evidence failure currently escapes the method | request custody is keyed by operation+attempt; deferred wake names blocker |
| Conversation classification | `conversation:{repository}:pr:{number}:delivery:{delivery_id}` | Preview target grant; provider-current callback during agent call; freeze result in manifest; settle route after manifest commit | agent protocol failure → unauthorized `CommentSeen` | no external effect is accepted; an unclassified bug aborts staging | committed manifest bypasses reclassification after restart |
| Coding attempt | `mutation:{repository}:pr:{number}:{op_key}`; Pi derives identity from operation+attempt | Git lookup first; full claim; agent with continuous-current callback; full claim again | movement → `MovedM`; unable/unchanged/correlation/admission rejection → `DeclinedM` | agent or authority uncertainty before Git acceptance → `FaultM` | if Git operation exists, no new agent call; otherwise explicit recovery reuses `op_key` |
| Git publication | workflow `op_key`; commit trailers bind operation and payload digest | Complete first-parent lookup; validate patch/tree; fresh PR read; exact ref compare-and-swap; lookup after CAS | stale authority/CAS loss without held operation → `MovedM` or `FaultM` according to proof | accepted ref update with lost response → `FaultM` until lookup proves commit | search complete first-parent history for one matching operation+digest+parents; collision fails closed |
| Timer command | `timer-command:{subject}:g{contiguous_generation}` | Apply one command transactionally; deliver oldest pending ack before another command/maturity | invalid or noncontiguous command fails closed | storage uncertainty aborts the step; no fabricated workflow result | operation row returns the exact prior result; rebuild from accepted History where possible |
| Timer maturity | `timer-due:{timer_id}:{due_at_us}` | Claim earliest `(due_at, timer_id)` under injected clock; persist maturity before delivery | cancelled/superseded timers never mature | storage uncertainty aborts the step | pending persisted maturity redelivers; accepted History marks it delivered on reconstruction |

## Adapter grouping and deletion test

### Keep the five comment publications together

`reply`, findings, dashboard, reminder, and announcement share one external
mechanism: a bot-authored PR comment ledger with stable markers, payload
collision checks, bounded recovery reads, and capability classification.
Deleting `publication.py` would repeat those rules in five Activity modules.
They still expose five typed methods because their authority and terminal
semantics differ. One generic `publish(kind, payload)` method fails the depth
test by making callers reconstruct those differences.

### Keep rerun separate

Rerun happens to use a comment marker today, but it owns a different semantic
cut: the final provider run inventory immediately before the request. It has no
blocked terminal and treats every unproven issuance as fault. Folding it into
publication would make the comment transport mechanism look like the domain
interface. `rerun.py` earns a separate module and port.

### Keep review orchestration separate; move request storage into custody

Review owns exact request freezing, unstaged-custody deferral, continuous
authority cancellation, and agent-terminal classification. The SQLite request
store is reconstructible readiness custody, not an agent adapter. Its live
interface remains the narrow `lookup/claim(operation, attempt, request)` seam,
but the implementation belongs under `readiness/custody`, while
`effects/review.py` owns orchestration.

### Split mutation orchestration from Git publication

Coding and Git publication are one workflow Activity because a `MutWork`
terminal must account for the whole attempt. They are not one adapter:

- coding owns credential-free agent request/result correlation and
  cancelability; and
- Git publication owns patch admission, object creation, operation trailers,
  complete-history lookup, and exact ref CAS.

`effects/mutation.py` therefore orchestrates the Activity while
`effects/git.py` earns a separate deep implementation. A deterministic Git
adapter can accept a ref and lose the response without simulating Pi; a
deterministic coding adapter can return a changed result without simulating Git.
This is the concrete compositional seam required by the ES-010 scenario.

### Keep agent bridges together only at the provider boundary

Review, conversation, and coding share the credential-free `agents` protocol
and host-owned route selection. A thin `effects/agents.py` bridge may adapt
those three operations. Their readiness orchestration stays separate because
they have different custody and terminals. A single `run_agent(kind, dict)`
port would discard the strict request/result types accepted in R1.

### Authority and timers are not effect modules

Authority combines readiness's durable grant with fresh provider evidence and
same-PR custody barriers. It belongs in `readiness/authority.py`. Timer custody
executes workflow timer commands but does not call an external provider; it
belongs under `readiness/custody/timers.py`. Neither should move into a generic
`effects` package merely because simulations replace it.

## Production and deterministic conformance

No executable spike was needed. Current production and deterministic evidence
demonstrates that both sides can implement each proposed seam:

- production classes perform every operation in the matrix without leaking SDK
  values into workflow tokens;
- `ReadinessProviderTruth` records exact operation, content digest, authored and
  provider authority, acceptance order, visibility, response loss, and recovery;
- the modeled agent runner fails on undeclared operations and requires exact
  operation/attempt terminals;
- `ModeledGitPublisher` implements lookup-first reconciliation, identity
  collision, accepted ref update, lost response, and later proof; and
- the World injects one logical time into the real timer store and independently
  derives expected timer state.

Today the deterministic World reaches several seams through GitHub transport
shapes and whole-host construction. The target local readiness simulation can
move the same truth behind the ports above. That is an adapter relocation, not
a need to patch readiness or add a simulation-only execution path.

## R2 tensions and handoff to S5

1. **Review evidence failure has no typed workflow category.**
   `V5ReviewGate.review_agent()` classifies agent inability but can re-raise a
   `GitHubBoundaryError` from current-authority or review-context reads. The
   workflow `RoundUnable` category has no provider-evidence member. S4 does not
   invent one or alter S3's manifest. R2 must rule whether such failure remains
   a Motus execution failure or becomes a new typed review terminal before the
   replacement tree is fixed.
2. **Unfenced publication is deliberate and must stay visible.** Replies and
   reminders are operation-scoped across heads; dashboard is a phase-suppressed
   singleton projection. They must not silently inherit the full authority
   fence used by findings and readiness announcement. R2 should accept this
   asymmetry as part of the port contract or request a separate behavior
   exploration.
3. **`ConversationWork` is the conversion seam for the ruled provider value.**
   `AdmittedConversation` remains owned by `github_app`; the readiness port owns
   only the classification task projected from it. S5 must place that conversion
   without making host decide workflow intent.
4. **Timer custody is part of readiness execution, not a host capability.** Host
   supplies construction inputs and a clock; readiness owns command ordering,
   persistence, reconstruction, acknowledgements, and maturity delivery. S5
   should place the store under readiness even though S1 found it under
   `host/v5`.
5. **S3's workflow ownership remains intact.** Readiness implementations satisfy
   the workflow-owned manifest; no gate declaration, return union, or
   `wire_gates` logic moves into readiness.

## Exit assessment

Every traced capability has one readiness-owned port group, one production
adapter route, and a deterministic implementation route. The port values contain
none of the forbidden SDK, credential, Petrus runtime, agent runtime, or
simulation objects. Stable identity, lookup-first ordering, ambiguity,
authority, and recovery are explicit per operation. Production and deterministic
adapters can satisfy the interfaces without patching readiness implementation.

Experiment 4 therefore meets its exit criterion. S5 can use this record to place
the application, runtime, authority, custody, and effects modules. The review
failure-category and unfenced-publication questions remain visible for R2 rather
than being silently resolved here.
