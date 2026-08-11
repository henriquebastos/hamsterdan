# AX2 — Lowering Activity and Sequence onto the frozen Net

- State: Completed, 2026-08-11.
- Question: can the smallest possible compiler lower `Activity` and
  `Sequence` onto the existing Petrus `Net` with a clear fragment
  contract, deterministic identifiers, unchanged runtime, and working
  source mapping?
- Prototype: [ax2_workflow_ast.py](ax2_workflow_ast.py) (evolved AX1
  nodes: the leaf gains explicit `request`/`result` colors),
  [ax2_compiler.py](ax2_compiler.py) (~200 lines), 10 tests in
  [test_ax2_compiler.py](test_ax2_compiler.py). Petrus untouched at the
  pinned commit; no production change.

## Lowering contract (the AX2 answer)

**A compiled fragment is a function from an entry place to an exit
place.** Not the entry/exit-pair-with-glue model:

- An `Activity` leaf owns one transition and one exit place; it receives
  its entry place from its context.
- A `Sequence` owns *nothing*. It threads children: each step's exit
  place **is** the next step's entry place. No glue transitions, no
  adapter places.
- Colors ride on places (entry ← root request; each exit ← leaf result)
  and `Net` resolves them onto the incident arcs — which is exactly what
  the frozen `DerivedActivityHandler` matches parameters and results
  against. The compiler adds no color mechanism of its own.

For `sequence(review: Draft→Review, publish: Review→Publication)`:

```text
w.entry(Draft) ──▶ w.0.review ──▶ w.0.out(Review) ──▶ w.1.publish ──▶ w.1.out(Publication)
                   handler="review"                    handler="publish"
```

N activities → N transitions, N+1 places, 2N arcs. Byte-identical to the
same shape written in today's DSL
(`test_matches_manually_authored_equivalent` compares
`serialize_net_definition` output).

## Generated identifiers

Paths derive only from AST structure: entry `w.entry`; a leaf at
structural address (1, 0) becomes transition `w.1_0.<name>` and place
`w.1_0.out`. The activity name in the transition path keeps runtime
telemetry readable; the structural index keeps duplicate occurrences of
the same activity distinct.

Handler binding uses the one Petrus mechanism that makes duplicates safe:
the transition *declares* the activity name as its handler symbol
(readable, production convention), and the compiler binds each
occurrence's `DerivedActivityHandler` by **exact handler `NetUri`** —
`Instance._bind_symbols` prefers the exact URI and never consults the
named fallback for it.

## Runtime evidence — zero changes required

- Execution: `Engine.create` + `InlineDispatch` runs the compiled net end
  to end; the exit place holds the final `Publication` token, entry and
  intermediate places drain, and History records
  `ActivityRequested("review")`, then `"publish"`, each with its
  `ActivityCompleted` (`test_sequence_executes_end_to_end_through_dispatch`).
- Replay: a **recompiled** net loaded over the same History reaches the
  same marking (`test_replay_over_recompiled_net_reaches_same_state`) —
  the deterministic-compiler requirement is satisfied and byte-verified
  (`test_recompilation_is_byte_identical`).
- Fail-loud negative control: loading History against a *divergent*
  compilation is rejected with `cannot resume: token records on w.1.out:
  not a place of this net` — replay integrity polices compiler drift for
  free.

## Source mapping

`CompiledWorkflow.source_map` maps each AST address to its generated
transition/place paths plus the authoring `file:line`;
`generated_by` inverts it, so a runtime transition (`w.1.publish`)
resolves to its AST node (`/1`) and source line. Both directions tested.

## Error quality

- Color mismatch is caught **before** any net exists, naming both AST
  nodes with addresses and source lines:
  `cannot lower sequence at /: activity 'review' at /0 (…:145) produces
  Review but activity 'publish' at /1 (…:146) consumes Draft`.
- An unknown activity name fails with the sorted list of known
  definitions — resolving AX1's deferred validation question: the
  compiler front door is the right place.

## What the runtime still owns

Deliberately unchanged and observed working: enabledness, token
propagation, occurrence-ID dispatch, frozen results, replay projections.
The compiler emits only schema objects and standard bindings.

## Explicit, inferred, ambiguous

- Explicit: activity names, request/result colors (strings/classes on the
  leaf — inference deferred to AX3), order.
- Inferred: all paths, arcs, place colors, handler bindings, declarations.
- Still ambiguous / deferred: what happens when a step's result is *not*
  what the next step consumes but a transformation exists (AX3);
  fan-out/join data semantics (AX4); spike modules must be AX-prefixed
  (`ax2_*.py`) because all spike directories share one pytest run —
  recorded as a series rule.

## Verdict

**Promising; continue.** The threaded fragment contract lowers cleanly
onto the frozen runtime with byte-exact manual equivalence, working
dispatch, replay-proof determinism, two-way source mapping, and better
error messages than the current DSL gives for the same mistakes (which it
reports only at bind time, without authoring locations). AX3 should now
attack the honest gap: deriving colors and transformations from typed
signatures instead of explicit `request=`/`result=` declarations.
