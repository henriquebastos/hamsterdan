# Experiment 10 — GitHub simulation

GitHub fan-out session S10x. Durable inputs: the ES-010 index, accepted
[`04-ports-adapters.md`](04-ports-adapters.md), accepted
[`07-step-contract.md`](07-step-contract.md), the ruled R3 decision
[`Timeline and coroutine stepper share bounded execution`](../../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md),
and accepted [`09-simulation-runtime.md`](09-simulation-runtime.md). The
repository baseline was local `main` and `origin/main` at
`cdc685e8f2b979057f15e851c35c482322c87dac`, which records accepted S9.

Method: inventory the current GitHub provider interfaces and the S4 operation
contracts; mount one isolated GitHub module beneath S9's unchanged structural
module interface; exercise the real `GitHubAuthority` and `CommentPublisher`
against a strict deterministic transport; add only a raw-ledger checker whose
derivation differs from the adapter's result classification; and generate,
crash, reconstruct, and exactly replay an accepted-hidden response-loss
failure. R2 and R3 are fixed inputs. No production, maintained test,
configuration, index, roadmap, decision, debt, or worklog surface changed.

## Verdict

The S9 runtime can host a useful GitHub-only simulation without acquiring
GitHub semantics:

```text
Timeline
  │ exact command / observation / fault / bounded step / crash / replay
  ▼
GitHubSimulation generation
  │ one scheduled authority read or publication operation
  ▼
real GitHubAuthority or CommentPublisher
  │ production Transport request/pages interface
  ▼
strict deterministic GitHub transport ──▶ retained provider truth
                                            │
                                            ▼
                                    independent checker
```

The spike covers authority movement, a stale provider read, a rate-limited
read, accepted hidden publication, content and full-authority identity
collisions, current-authority fencing immediately before each POST, stable
operation markers, lookup-first recovery after generation loss, finite
resources, and exact replay. Commands, observations, local fault routing,
payloads, and modeled provider requests all reject unknown values.

The generated proof's provider schedule makes an accepted-hidden comment
discoverable by `CommentPublisher.immutable()`'s immediate reconciliation.
The one Timeline leaf therefore performs exactly one POST, returns after
lookup, and can crash before owner completion at S7's ruled cut. Current
`CommentPublisher.immutable()` nevertheless remains a coarse production seam:
if that reconciliation lookup is stale, the same synchronous call can fence
and POST again before S9 can cut. The proof does not use that incompatible
visibility schedule, and the gap remains recorded for Delivery.

## Production interface inventory

### Provider transport

`github_app.models.Transport` is the smallest real provider seam available
today:

```python
request(method, path, body=None) -> WireResponse
pages(path) -> tuple[dict, ...]
```

The simulation transport implements those methods directly. It accepts only
the exact pull, base-ref, comment-list, and comment-create requests emitted by
the two production owners below. An unknown method, path, pagination request,
or comment payload raises `AssertionError`; it never invents a plausible
provider response.

`WireResponse` carries status, body, and optional next path. It carries no
headers, credential, token, rate-limit reset, request ID, or provider client.
The production GitHubKit boundary owns credentials and request metadata outside
this interface. The simulation preserves that boundary: no credential-shaped
value exists in its store, command, observation, fault, or artifact.

### Authority reads

`GitHubAuthority(transport, repository, pr_number).pull_request()` is the real
authority projection used by the spike. It performs the current two-read
sequence:

```text
GET /pulls/7
GET /git/ref/heads/main
  -> PullRequestSnapshot
```

The simulated provider can return the prior retained authority version with
HTTP 200 or the current version with HTTP 429. Production code behaves
unchanged: a stale 200 becomes an ordinary `PullRequestSnapshot`; a 429 becomes
a secret-safe `GitHubBoundaryError`. Staleness is not borrowed from that result.
The independent checker derives it by comparing the raw returned provider
version with the provider version current at read completion.

### Comment effects

`CommentPublisher.immutable(kind, operation, epoch, head, body)` is the real
lookup-first comment operation used by the spike. Its production ordering is:

```text
list comments
if exact marker exists:
    require compatible payload and return existing
fence immediately before POST
POST comment
on an unproven outcome:
    list comments
    if exact marker exists, return existing
    otherwise fence and POST once more
```

The stable identity is the production final marker:

```text
<!-- hamsterdan:readiness operation=<operation> head=<head> -->
```

That marker does not encode base or policy. Before invoking the production
publisher, the local module therefore compares any retained same-operation
effect with the new full authored authority. A difference returns
`identity_collision`; otherwise current production lookup handles the marker
and body. Without that local owner check, `CommentPublisher` alone would return
`existing` for the same operation, head, and body across a base or policy
change.

The simulation's fence receives the real callback signature but compares the
complete authored `(epoch, head, base, policy)` claim captured by the scheduled
operation with current provider authority. The callback logs the provider
version and returns immediately before the transport records a POST. A moved
claim stops before mutation. This preserves R2's full-claim authority rule even
though `CommentPublisher` itself passes only epoch and head through its public
arguments; in current production, the host callback similarly resolves the
active full claim outside the provider module.

## Local simulation interface

The executable spike lives at
[`spikes/10-github-simulation/github_simulation.py`](spikes/10-github-simulation/github_simulation.py).
It imports S9's `ActionRef`, `Budget`, and `Timeline` from the accepted runtime
spike without editing or copying that runtime. `GitHubSimulation` implements
S9's exact structural methods:

```text
name
open(context)
drop(generation)
close(generation)
resource_usage(generation | None)

generation.command(name, payload, context)
generation.observe(name, payload, context)
generation.eligible_actions(context)
generation.step(action, context)
```

The module has one retained store outside each process-local generation.
Authority versions, pending requests, provider reads and calls, accepted
effects, outcomes, and observed collisions survive `drop()`. The generation
holds no unique recovery state. A restart reconstructs eligibility from the
pending request map; the production publisher then looks up the same operation
before another effect.

### Commands

| Command | Exact payload | Effect |
|---|---|---|
| `authority.set` | `epoch`, exact lowercase `head`, exact lowercase `base`, `policy` | Append one monotonically increasing provider authority version; an exact repeat is idempotent |
| `authority.read` | `request`, `at_us` | Schedule one production `GitHubAuthority.pull_request()` operation |
| `publication.request` | `request`, stable `operation`, bounded `body`, full `authority`, `at_us` | Schedule one production immutable-readiness publication operation |

Command fields are exact. Request and operation identities use a closed
128-character grammar. Publication bodies contain 1–4,096 UTF-8 bytes. Work
cannot be scheduled in the logical past, and one request identity cannot be
reused. Unknown commands and malformed values fail before a partial store
change.

### Observation

`state` accepts no payload and returns one detached strict-JSON record:

```text
authority       current full provider authority or null
authorities     complete bounded authority lineage
pending         scheduled but incomplete requests
outcomes        owner-completed operation results
effects         raw accepted provider comments and their visibility/response facts
reads           provider version returned and current at each authority read
calls           exact GET/pages/fence/POST order with stable request identities
collisions      visible same-operation content or full-authority refusals
```

`GitHubSimulation.state()` returns the same detached shape after replay so the
focused proof can compare original and replayed semantic state. It is a
read-only inspection convenience; Timeline remains the public execution and
artifact API.

### Faults

The local `github_fault()` router validates the module-owned fault vocabulary,
then calls S9's unchanged `timeline.fault()`:

| Point | Exact payload | Meaning |
|---|---|---|
| `read.response` | `outcome = stale | rate_limited` | Return the prior provider authority with status 200, or current authority with status 429 |
| `publication.acceptance` | `visibility = visible | hidden | generated`, `response = returned | lost` | Accept one comment, record its visibility at acceptance, and either return 201 or raise after acceptance |

`generated` uses the module-namespaced `github:effect_visibility` choice stream
over the exact options `visible` and `hidden`. Unknown points fail at the local
router. A hidden accepted comment becomes discoverable on the production
publisher's immediate reconciliation lookup; the retained ledger keeps both
its acceptance visibility and current visibility. Exact fault fields are
checked before arming; semantic values are checked when the named fault
occurrence is consumed. A stale response requires prior and current authority
versions or raises `GitHubSimulationContractError` with the missing setup.
Replay uses the expanded known fault operation already recorded by Timeline.

### Bounded actions and resources

Each scheduled request produces one `ActionRef` at its exact logical instant.
One owner step processes one request and offers at most one Timeline leaf. The
leaf calls one production high-level operation. The local store has these hard
bounds, repeated as S9 resource gauges:

| Gauge | Limit |
|---|---:|
| authority versions | 16 |
| pending requests | 32 |
| accepted physical effects | 32 |
| provider calls and fences | 128 |
| authority reads | 32 |
| retained canonical bytes | 262,144 |

The Timeline adds finite operation, owner-step, eligible-action, leaf-call,
choice, active-fault, generation, logical-time, journal, and artifact bounds.
Comment listing is bounded by the accepted-effect limit. Every modeled
publication leaf performs at most one POST: accepted response-loss effects are
discoverable by immediate reconciliation, while returned responses need no
reconciliation. The production publisher's latent two-attempt branch remains
the correspondence gap described below rather than a behavior exercised by
this simulation schedule.

## Independent checker

`GitHubChecker` consumes only the detached raw read, call, and accepted-effect
ledgers. It does not read module pending work, outcomes, exceptions, or desired
status. It independently derives four findings:

1. one stable operation maps to more than one retained payload or authored
   authority;
2. accepted effect authority differs from provider authority at acceptance;
3. an HTTP-200 authority read returned a provider version other than the one
   current at completion; and
4. a POST was not immediately preceded by an allowed same-request,
   same-operation fence for the same provider version.

Repeated physical effects with the same operation, payload, and authority would
not be a checker violation. Treating them as one would claim exactly-once
behavior that R2 and the product principles reject. The sensitivity contract
independently mutates detached raw effects across both content and full authored
authority and proves that the checker reports
`effect_identity_collision:ready:stable` without consulting the module's
collision outcome.

## Executed scenarios

The focused contract at
[`spikes/10-github-simulation/test_github_simulation.py`](spikes/10-github-simulation/test_github_simulation.py)
executes five scenarios.

### Strict local vocabulary

Unknown command, observation, and local fault names fail with exact exception
payloads. A missing authority field fails before state mutation. A known fault
with an unknown semantic value fails when its occurrence reaches the module.
The strict transport contains no fallback request route. Exposing `stale`
without both prior and current authority versions raises the named
`GitHubSimulationContractError` and instructs the caller to establish two
versions instead of leaking an accidental `IndexError`.

### Authority movement, stale read, and rate limit

Authority moves from epoch 1/head A/base A/policy A to epoch 2/head B/base
B/policy B. One production authority read receives version 1 under HTTP 200;
the checker derives `stale_authority_read:read-stale`. A second receives HTTP
429 and production returns the classified boundary failure. A publication
authored under epoch 1 first performs lookup, then the immediate full-claim
fence refuses it. No POST or accepted effect exists.

### Visible content and full-authority identity collisions

The first `ready:stable` publication lands visibly. A second request reuses the
operation under a different body. Production lookup finds the marker and raises
its exact collision before another POST. Authority then moves to epoch 2 while
retaining the same head but changing base and policy. A third request reuses
the same operation, head, and body under that different full authority; the
module refuses it as `identity_collision` rather than accepting the old marker
as `existing`. Provider cardinality remains one. Independent raw-ledger
sensitivity mutations prove the checker detects both conflicting accepted
content and conflicting accepted full authority.

### Generated accepted-hidden failure, crash, and replay

The bounded campaign tries at most 16 seeds. Seed 0 generated `hidden` for the
first acceptance while the fault also lost its response:

```text
pages
fence(current epoch 1)
POST accepted, hidden, response lost
pages -> marker becomes discoverable; immutable returns existing
Timeline leaf returns after exactly one POST
crash in executed phase before owner completion
restart
pages -> marker present
owner completes from lookup with status existing
```

The single physical comment retains `ready:hidden`, the exact body, the full
authority, hidden visibility at acceptance, and discoverable current
visibility. The executed-phase state contains exactly one POST and one effect
before the crash. The checker is clean. The failed provider response, generated
hidden acceptance, process-local owner-result loss, lookup-first
reconstruction, and final semantic state replay exactly.

Executed artifact evidence:

```text
discovery seed      0 of at most 16
expanded operations 11
journal entries     28
artifact bytes      15,453
final generation    2
choice draws        github:effect_visibility=1
accepted effects    1 under the stable operation and full authority
checker findings    none
journal digest      sha256:2e430362da9a341d1d24317ae3467059711f2d9ebe36affb692c6b43353f47cc
replay              exact runtime journal and exact detached GitHub state
```

Encoded artifact bytes contain no `credential`, `installation_token`, or
`private_key` field or value. S9 also excludes process-local leaf return values
and exceptions from artifacts.

## Production-seam gaps and proposed correction

### One production publication call can cross two effect attempts

Observed current state:

```text
CommentPublisher.immutable()
  lookup
  fence
  POST
  on GitHubBoundaryError: lookup
  if absent: fence + POST again
```

The revised generated proof does not enter the final branch. Its accepted
response-loss comment is hidden at acceptance but becomes discoverable on the
immediate reconciliation lookup. The leaf's raw prefix is exactly
`pages, fence, POST, pages`; the executed-phase crash follows one provider
mutation. Restart adds one lookup and no mutation.

Required target state from S7:

```text
one owner step
  lookup
  current-authority fence
  at most one POST attempt
  return landed | absent | ambiguous | rejected

later owner step after ambiguity
  repeat lookup first under the same operation identity
```

The proposed future Delivery correction is to expose a bounded publication
operation that performs at most one provider mutation attempt. Readiness should
retain the stable work and decide when another bounded step becomes eligible;
that later step starts with lookup. The correction must keep the present full
authority callback immediately before each POST and must retain the honest
at-least-once guarantee. It must not claim that an eventually hidden provider
effect can be made exactly once without provider idempotency.

This experiment does not select the final Python class or module split, and it
does not authorize a production change. S12 can carry the gap into a Delivery
slice after R4.

### Rate-limit and stale-read provenance are modeled behind the current seam

`WireResponse` does not carry rate-limit reset metadata, and
`PullRequestSnapshot` does not carry provider freshness provenance. The local
simulation can retain both facts because it owns provider truth; current
production callers receive only a boundary failure or snapshot. This is enough
for the S4 port behavior tested here: a stale read cannot bypass the separate
immediate effect fence, and rate limiting does not fabricate authority.

If future bounded scheduling requires exact provider retry time, the owner must
obtain a secret-safe classified rate-limit value at the one GitHub boundary.
This experiment does not add one because no ruled interface currently requires
it.

## Correspondence and scope limits

- The deterministic transport is not GitHub. It proves local ordering,
  identity, recovery, and classification logic, not GitHub consistency,
  authentication, permissions, headers, latency, or availability.
- `GitHubAuthority.pull_request()` and immutable readiness-comment publication
  are production-real. CI rerun, review comments, dashboard update, Git object
  creation, GraphQL ref CAS, webhook ingress, and installation routing are not
  constructed because the GitHub S10 minimum scenarios do not require them.
- A stale authority read is exactly one prior retained authority version. An
  accepted-hidden comment becomes discoverable at the immediate reconciliation
  lookup. Neither model claims a provider cache distribution or duration.
- HTTP 429 models classification only. It does not model reset headers,
  secondary limits, backoff, or transport retries.
- Generation loss is in-process against retained stores. Real process death,
  network interruption, and GitHub correspondence remain separate evidence.
- The spike mounts one module and never imports or constructs workflow,
  readiness, agents, host, Petrus testing, or whole-Hamsterdan simulation.
- S9's runtime source is unchanged. GitHub names, commands, faults, provider
  state, and checker rules live only in the local GitHub spike.

## TDD and verification evidence

The first focused collection failed because `github_simulation` did not exist.
The pre-acceptance correction first failed collection because the named
`GitHubSimulationContractError` did not exist. The implementation then made the
five behavioral contracts pass:

```text
focused pytest          5 passed in 0.18s
focused Ruff            All checks passed
focused format          2 files already formatted
focused ty              All checks passed
```

Because experiment spikes are outside the maintained test paths, those focused
checks are separate from the project gates. After syncing the locked Bun and
Playwright prerequisites prescribed by `.agents/setup`, both mandatory gates
passed without a tracked environment change:

```text
scripts/check quick
  Ruff / format / ty    passed
  architecture          10 passed in 1.95s

scripts/check full
  repeated quick        passed; 10 architecture tests in 1.96s
  webhook relay         9 passed, 0 failed
  demo-video             44 passed, 0 failed
  package build          sdist and wheel built successfully
  routine suite          1,165 passed in 98.20s
```

The final changed-file diff also passes `git diff --check`.

## Exit assessment

The isolated GitHub module runs beneath S9's exact Timeline/module interface,
uses current production provider interfaces where they exist, and has strict
bounded commands, observation, faults, provider requests, and resources. It
covers every required GitHub scenario and independently checks only raw facts
for which a different derivation is available. A generated accepted-hidden
response loss crosses a generation crash, reconstructs lookup-first, and
replays exactly without constructing whole Hamsterdan.

The experiment therefore meets the GitHub part of Experiment 10. The bounded
publication mismatch remains an explicit production-seam gap for later
candidate and Delivery work; it does not change R2, R3, or production now.
