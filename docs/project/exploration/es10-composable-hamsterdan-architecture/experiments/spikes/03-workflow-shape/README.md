# Spike: pure workflow package shape (experiment 3)

Throwaway structural prototype for ES-010 S3. Never production code; never
imported from `src/` or `tests/`. It exists to prove four structural claims
recorded in [`../../03-workflow-shape.md`](../../03-workflow-shape.md):

1. The `net_v5 <-> topology` package-initializer cycle disappears when the
   composer imports loop modules by full module path and no package
   initializer re-exports.
2. The workflow builds and runs one decision (observation → fact → Activity
   request → typed terminal fold) importing only Petrus definition modules,
   pydantic, and the stdlib — no `hamsterdan.*`, host, GitHub, agent, or
   simulation imports.
3. Hydration works without `vars()` discovery: `values()` hydrates by the
   color of each requested type, and the composer builds an explicit
   token-class registry validated at build time.
4. A gate manifest owned by `workflow/activities.py` (request type, result
   variants, lane, operation identity, blocked synthesis) replaces the
   per-request `isinstance` chains in today's `gating.py` handler subclasses.

Deliberate reductions against the real workflow: three mini loops (life, ci,
escalation) instead of nine; reduced value fields; one identified-inline gate
and no durable-publication gate, so `GateDeclaration.blocked` and
`DeclaredGateHandler.project_failure` are transcribed design, **not exercised
by the run proof**; `seed_marking` validates the subject but no mini loop
consumes it.

Run from this directory:

```
uv run --frozen python prove.py
```

Copied-code provenance is noted per file; the source is `src/hamsterdan` at
commit `0686067`.
