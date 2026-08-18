# Complex-system correctness sketch

Use this sketch only for work that is durable, concurrent, stateful, or performs
externally visible effects. A local pure transformation or ordinary UI change
does not need it.

The purpose is to make correctness and termination discussable before code is
organized around a happy path. Keep the sketch proportional: a paragraph or a
small table is often enough. Put application-specific detail in the owning
roadmap/architecture document rather than copying this checklist everywhere.

## Questions to answer in the Plan

1. **Authoritative state and authority** — What state survives restart, what is
   only a projection or wake hint, and which identity/version currently
   authorizes work? Example: a PR effect is authorized by installation,
   repository, PR, head, base, policy, and lifecycle—not merely the PR number.
2. **Safety** — What must never happen, including across retry and crash?
   Example: an accepted Git publication must not happen twice after its
   response is lost.
3. **Fair-environment liveness** — Which external failures eventually stop,
   which workers/clocks/stores remain available, and which human/provider
   prerequisites are explicitly excluded before lack of progress is a bug?
4. **Bounds and dispositions** — Bound queues, attempts, timers, payloads,
   concurrency, retained data, work loops, and diagnostics. Name what happens
   at each limit; never turn silent truncation into success.
5. **Nondeterminism** — List time, event order, IDs, provider responses,
   concurrency, randomness, and any other input that can change the result.
6. **Crash and ambiguity cuts** — Name the costly boundaries before/after
   durable acceptance, external effect, terminal, settlement, projection, and
   acknowledgement. Distinguish definite rejection from accepted-but-unknown.
7. **Independent checking** — State how expected behavior is derived without
   calling the implementation decision being tested. If an independent model
   is impractical, explain the alternative evidence and confidence limit.

## Delivery expectations

- Put executable properties at meaningful atomic boundaries, not only at the
  final happy state.
- Use one stable operation identity across at-least-once retries and recover
  ambiguous external outcomes lookup-first.
- Preserve exact replay data for modeled nondeterministic choices; a seed alone
  is discovery metadata.
- Treat one vertical scenario as plumbing proof, not coverage of mutually
  exclusive state. Use generated schedules and shrinking when the state space
  warrants them.
- Keep simulated and real-boundary evidence separate and state what each does
  not prove.

CV18's concrete readiness application of this sketch lives in
`docs/project/roadmap/cv18-deterministic-readiness-simulation/`.
