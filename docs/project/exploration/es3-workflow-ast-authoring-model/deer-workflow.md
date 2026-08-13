# Deer Workflow — external comparison across ES-001…ES-004

**Source:** <https://github.com/deerwork-ai/deer-workflow> —
TypeScript/Bun, Deerwork AI, inspected at exact revision
`b20823012eeec15d41f4969f09964401e00f56e0` on 2026-08-13 via full local
clone and source verification. Upstream had not moved past that
revision at inspection time (`origin/HEAD == b208230`).
**Provenance:** a Navigator-transferred evidence report from Petrus
local commit `6f5642c` (Deer-vs-Petrus, not reachable through
Hamsterdan history) was used as input, independently cross-checked
claim by claim against the Deer source, and its durable meaning folded
into this note; the transferred scratch file was then removed.
**Why it is here:** the Navigator asked how Deer's developer experience
and workflow-authoring model bears on ES-001–ES-004 — especially the
ES-003 candidate spec and the ES-004 experience specification.

Evidence grades: `[D]` verified directly in Deer source at the pinned
revision (file:line cited); `[E]` backed by executed Hamsterdan
captures already in this repository; `[X]` refuted claim.

## What it is, in one paragraph

A small structured-concurrency library around complete coding-agent
CLI subprocesses. A workflow is an ordinary TypeScript module: an
async handler using `await`, conditionals, loops, `parallel([...])`
(a `Promise.all` wrapper), and `pipeline(items, ...stages)`; agents
(Codex, Claude Code, Pi) are invoked through one tiny
`run(prompt, options)` interface over subprocesses. Seven typed
lifecycle events feed a first-party TUI and a JSONL print mode. There
is no graph object, no durable state, no checkpoint, no replay, no
resume, no workflow retry/timeout/cancellation protocol, and no
persistence reader — the call stack is the topology and lexical
variables are the state. Version 0.2.0, 47 commits, 3 authors, 15
calendar days of history, 78.7 % of commits on day one `[D]`.

## Cross-check of the transferred Petrus report

All twelve architectural claims in the transferred report were
re-verified against the Deer source. Ten confirmed exactly; two need
nuance, recorded here so the folded conclusions stay honest:

1. **Cancellation testing is Pi-only.** The report says "cancellation
   is tested"; active `AbortSignal` process termination is tested only
   for the Pi adapter (`tests/agents/pi-agent.test.ts:270-278`); Codex
   and Claude adapters implement but do not test it `[D]`.
2. **Phase/view separation is embryonic but real.** Static
   `meta.phases` is a display-only plan (`src/flow/types.ts:113-127`)
   distinct from the runtime `phase()` mutation — a two-layer
   plan/progress split the report's flat "mutable phase" reading
   undersells. The mutable half still races under concurrency, exactly
   as reported (`docs/index.md:207-210` asks authors not to change
   phase inside branches) `[D]`.

Everything else held: `parallel`/`pipeline` catch every branch failure
— including abort rejections — and return `null`, typed as
`Awaited<TOutput> | null` (`src/flow/parallel.ts:25-31`,
`src/flow/types.ts:20-25`); fan-out is unbounded and documented as
such ("Neither primitive silently retries, queues, fails fast, or
limits concurrency", `docs/index.md:201-203`); event listeners run
synchronously on the execution path with no isolation
(`src/events/emitter.ts:52-54`); structured output is cast, never
validated (`return JSON.parse(lastMessage) as TOutput`,
`src/agents/codex-agent.ts:189-190`; the contract explicitly delegates
enforcement to the provider, `src/agents/types.ts:16-18`); the
convenience `agent()` is hard-wired to Codex
(`src/agents/index.ts:29-47`); nesting is capped at one level with a
useful error (`src/flow/workflow.ts:56-59`); JSONL output has a writer
and no reader (`src/events/json-writer.ts:15-20`); "agent graph" has
no graph implementation beneath it `[X]` (README marketing only).

## Reading by exploratory story

### ES-001 — boundary between product workflow and execution mechanics

**Corroborates.** Deer's crispest virtue is the same split ES-001
fought for: exact sequencing, branching, aggregation, and file
handling stay in code; agents receive semantic tasks `[D]`. Its
crispest absence is the other half of ES-001's judgment: without a
durable asynchronous-call boundary, an interrupted agent subprocess
simply never happened — no ambiguity is modeled because none *can* be.
ES-001 preserved Activity request/result places precisely because that
boundary carries meaning (work in flight, authorization, retirement);
Deer is the existence proof of what its removal costs `[E]` for the
Hamsterdan side. Per-agent `AbortSignal` with no workflow-level
cancellation state also lands on ES-001's side of the line: lifecycle
custody belongs to the runtime, not the authoring surface.

### ES-002 — imperative expression layer (archived)

**Corroborates the archive — and completes the experiment.** ES-002
closed because imperative sugar over one net had negative economics.
Deer is the control run ES-002 could not perform: the imperative
surface winning *completely*, topology and state dissolved into host
control flow. The reward is real (three-step quick start:
`bun install --global`, `deer-workflow create "…" > workflow.ts`,
`deer-workflow run ./workflow.ts --input '…'`, `README.md:49-71`
`[D]`); the price is the entire compiled artifact — nothing to
render, validate, diff, replay, resume, or map back to source. The
refinement Deer adds: the imperative surface's genuine value
concentrates in *adoption* (first file, first motion), not in
production expression. That is a product lesson, not a reversal.

### ES-003 — workflow AST and block algebra

**Corroborates the doctrines, mostly by negative example; adds one
mechanism.** Item by item against the
[unified candidate spec](synthesis/05-unified-candidate-spec.md):

- **Failure rail (AX25) / typed outcomes (AX21, AX22).** Deer's
  failure-as-`null` conflates thrown errors, cancellation, and a
  legitimate null result into one unmarked value, and authors must
  hand-filter it (`examples/deep-research/workflow.ts:254-256` `[D]`).
  This is the exact failure mode the rail's *visible* drains and the
  n-ary typed outcome vocabulary (`Applied | AlreadyApplied | Stale |
  Transient`) were designed against — the second independent
  TypeScript library (after Composable Functions) to demonstrate the
  hazard, and the first to demonstrate it by *committing* it rather
  than retreating from it.
- **Parallel with explicit join policy (AX24).** Deer's `parallel` is
  the "all" policy with unbounded admission and invisible failure;
  AX24's `par` requires branch totality so the join is sound, and
  `par_fail_fast` drains losers into a visible `abandoned` exit `[E]`.
  Deer changes nothing here; it strengthens the totality argument.
- **Authoring styles (AX10).** Deer is a live imperative/builder
  surface of the kind AX10 rejected for us — and it works *for Deer*
  because Deer has no second phase: nothing is lowered, persisted, or
  replayed. Under our two-phase requirement (compose a value, lower
  it, run it durably) the rejection stands unchanged.
- **Guards (AX6), ports, types.** No counterpart exists in Deer —
  ordinary `if` plus generics. Its unvalidated `as TOutput` cast at
  the provider boundary `[D]` is the negative image of the AX16
  posture (validate at boundaries, once) and of Hamsterdan's strict
  Pydantic conversion at readiness ownership `[E]`.
- **Phase/view.** Deer's static `meta.phases` display plan vs runtime
  mutable phase is an embryonic version of our split between policy
  lanes/source mapping (authoring metadata) and live projection. Its
  documented race corroborates the ES-004 doctrine that a presentation
  grouping must never become a second mutable execution truth.
- **The one genuinely new mechanism: the generated-authoring route.**
  `skills/workflow-creator/` packages `SKILL.md` (generation
  instructions), `references/api.md` (the API contract), 
  `references/patterns.md` (orchestration patterns), a full source
  template, and `evals/evals.json` (three generation/repair cases).
  The CLI runs the authoring agent in a **read-only sandbox**, prints
  generated source to stdout, and never auto-executes it
  (`src/cli/create.ts:81-133`; "Generated source is written to stdout
  and is not executed automatically", `docs/index.md:99-102`), with a
  15-point validation checklist (`SKILL.md:295-318`) `[D]`. This is a
  working, tested implementation of "generate, inspect, validate,
  then run" — and our layered design is structurally *better* suited
  to it than Deer's: generated block-algebra source faces
  deterministic `CompositionError`s, `check_sound`, guard-path
  validation, and pyright/ty before any lowering, where Deer can only
  offer a checklist and a type check. Candidate experiment below.

### ES-004 — Hamsterdan experience specification

**Corroborates the projection spine; changes no control semantics.**

- **Presentation as projection.** Deer's TUI and JSONL print mode are
  projections of one typed event stream (`src/cli/run.ts:40-48` `[D]`)
  — the same shape as ES-004's "control state and snapshots are
  projections; the loop is data" `[E]`. Deer then breaks its own
  discipline by running listeners synchronously on the execution path;
  a slow or throwing observer delays or breaks the lifecycle it
  observes `[D]`. Negative confirmation of the separation ES-004 keeps
  by construction (fold/decide are pure; ingress and gate exits are
  the log).
- **Control machine, gates, folds, conversations, time.** No Deer
  counterpart exists for any of it — no staleness, no epochs, no CAS,
  no idempotency identity, no supersession. Nothing to refine.
- **One-PR walkthrough.** Deer's `examples/deep-research/` — one deep,
  end-to-end, quoted-at-length example with docs, skill context, and
  tests moving together `[D]` — independently validates the ES-004
  lens-4 pedagogy (one executed deep walkthrough over shallow traces
  per feature).

## Copy, adapt, inspire, avoid, ignore (Hamsterdan lane)

**Copy** (contracts and discipline, no code):

1. The skill-package *shape* for generated authoring: instructions +
   API reference + patterns + template + evals, generation in a
   read-only context, output as reviewable source, never auto-run.
2. Channel discipline for any future one-shot host CLI: stdout for the
   declared result, stderr for human progress, one versioned JSONL
   mode.

**Adapt:**

1. The three-step first-motion path, re-founded on our artifacts: one
   file of L4/L2 authoring source → compile → render/validate → run on
   the frozen engine — the artifact chain Deer lacks becomes the
   feature, not the tax.
2. Structured-result validation stays a Petrus-/readiness-owned
   boundary (already our posture); Deer's cast-and-trust is the
   counterexample to cite, not a pattern to import.

**Inspiration:** one read-only event protocol powering dashboard, CI
output, and supervisor views; compact final results plus durable
artifacts as the agent contract; examples that teach orchestration
patterns before every concept is explained.

**Avoid** (all verified in source, none survivable under replay):
failure-as-`null`; unbounded fan-out by default; a shared mutable
phase; synchronous observers on the semantic path; casting provider
output without validation; a "neutral" convenience hard-wired to one
provider; treating writer-only JSONL as durable state.

**Ignore:** the "agent graph" language (no implementation beneath it
`[X]`); the one-level nesting cap (shortcut, not insight); Bun
source-only packaging; the HTML report renderer.

## Convenience versus genuine adoption gaps

Local-process convenience, not evidence of a gap: the TUI's polish as
such, single-binary Bun ergonomics, the hard-wired `agent()` default,
subprocess adapters as a universality claim.

Genuine gaps Deer exposes in Hamsterdan/Petrus adoption surfaces:

1. **First motion.** Deer: install → generate → run, watching live
   progress, in three commands. Petrus/Hamsterdan: compose Net,
   bindings, History Store, Dispatch, Engine, and a host loop before
   anything visibly moves. The ES-003 L4 façade shrinks the authoring
   half; the run-and-watch half has no owner yet.
2. **Live observation.** Deer ships an event-fed TUI on day one.
   Petrus has the *stronger truth* (History, telemetry, observation
   protocols) and no comparable "show this run live" surface; that
   remains Arx-/host-lane product work, deliberately outside ES-003/
   ES-004 scope.
3. **Generated authoring.** Deer ships it, tested, with evals. Ours is
   better-founded (deterministic composition errors as the generation
   feedback loop) and entirely unbuilt.
4. **Worked-example discipline.** Docs, quick start, skill context,
   examples, and tests move together in Deer; the cost is manual
   duplication, the intent (one coherent teaching surface) is right.

## Candidate deltas to the syntheses

No change to any proven mechanism in either candidate spec: the block
algebra, ports, rail, typed outcomes, guard model, control machine,
gates, and folds all stand — several now doubly corroborated by
negative example. The deltas are additive and remain candidates for
Navigator choice:

- **Candidate AX27 — generated authoring against the composition
  authority.** Spike a skill package (instructions + block-algebra API
  reference + patterns + evals) whose agent generates L4/L2 authoring
  source for a small brief; feed generation errors from
  `CompositionError`/`check_sound`/pyright back as the repair loop;
  never auto-execute; measure how often the deterministic checks catch
  generated nonsense that Deer's checklist could only ask about. The
  ES-003 spec's validation section (three layers, remedies in the
  message) was written for humans; this tests it as a machine
  interface — the strongest form of the "quality of error messages"
  question the series already asked.
- **ES-003 spec §13 (risks/open):** note that the first-motion and
  live-observation surfaces are unowned adoption work, deliberately
  out of ES-003 scope, with Deer as the evidence they matter. No spec
  text changes until the Navigator rules on the spec itself.
- **ES-004 spec:** no candidate change. Deer adds corroborating
  negative evidence for §1's projection spine and §11's validation
  posture; the open product choices tabled there are untouched.
- **Petrus lane (folded from the transferred report, cross-checked):**
  the durable conclusion survives verbatim — *preserve the explicit
  Net/History/Activity/authority model; learn from Deer how quickly a
  user can author, run, observe, and understand a small workflow; then
  deliver that immediacy through compiled frontends and read-only
  projections rather than hidden control flow.* Its concrete
  recommendations (one event-fed presentation architecture, strict CLI
  channels, adapter process hygiene, generate-inspect-validate-run,
  one immediately runnable worked example) are adoption-surface work
  crossing Arx/Agenticus/host boundaries — each needs a separately
  bounded Navigator choice, and none is promoted here. They are not
  entered in the [Petrus speculation ledger](petrus-speculation.md)
  because that ledger owns runtime-semantics speculation; this note is
  their Hamsterdan-side record.

## Verdict

Deer Workflow is prior art for the adoption and presentation layers,
not for execution semantics — there is nothing beneath its authoring
surface to compare against the algebra, and that absence is itself the
finding. It completes ES-002's experiment from the other side (the
imperative surface won completely and the artifact vanished),
doubly confirms the ES-003 failure doctrines by committing the
mistakes Composable Functions retreated from, corroborates ES-004's
projection spine by breaking its own, and contributes exactly one
mechanism worth spiking: the generated-authoring route, where our
deterministic composition errors would give the generating agent a
feedback loop Deer cannot express. The genuine gaps it exposes —
first motion, live observation — are product work above these
explorations, now on the record with evidence.
