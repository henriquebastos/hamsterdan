# 16 — How the authoring compiles

**Rely on this: every construct is a mechanical rewrite into places,
transitions, and arcs — leaves add nodes, composition only renames —
so the net you get is exactly the net you can count.**

This chapter is the shared mechanics behind every "What it compiles
to" section in chapters 3–8. The pseudocode is **condensed from exact
spike code** (files linked per rule) — shortened for reading, not
idealized: each rule's shape, names, and refusals are the ones that
ran on the frozen engine.

## The compiled unit

Everything lowers into one value. A `Block` is a bag of kernel nodes
plus a typed boundary:

```python
# condensed exact — ax23_blocks.py
@dataclass(frozen=True)
class Block:
    name: str
    nodes: tuple[KernelPlace | BoundaryTransition, ...]  # the subnet
    entry: Port                    # one typed entry place
    exits: dict[str, Port]         # named typed exit places
    pure: bool                     # metadata with teeth (concept 3)
    contexts: dict[str, Port]      # declared ambient reads/holds
```

A `Port` is just `(place_name, color)`. The boundary is real net
structure — entry and exits *are* places in `nodes` — so composing
blocks and composing nets are the same operation.

## Leaves add nodes

`step` (spike name `transform`) — one pure 1→1 leaf:

```python
# condensed exact — ax23_blocks.py::transform
def step(name, fn, *, accepts, returns) -> Block:
    entry, out = f"{name}_in", f"{name}_out"
    nodes = (
        KernelPlace(entry, accepts),
        KernelPlace(out, returns),
        BoundaryTransition(name, arcs=(consume(entry), produce(out)),
                           work=wrap(fn)),
    )
    return Block(name, nodes, Port(entry, accepts),
                 {"out": Port(out, returns)}, pure=True)
```

```diagram
┌──────────┐   ┌────────────┐   ┌───────────┐
│ name_in  │──▶│ name (T)   │──▶│ name_out  │     2 places, 1 transition,
│ accepts  │   └────────────┘   │ returns   │     2 arcs
└──────────┘                    └───────────┘
```

`outcomes` (spike name `classify`) — one typed-routing leaf. One exit
place **per outcome**; the handler returns `(exit_name, data)` and the
token goes to that exit's place. Exit colors must be distinct — color
is how the handler addresses exits:

```python
# condensed exact — ax23_blocks.py::classify
def outcomes(name, fn, *, accepts, outcomes) -> Block:
    nodes = (
        KernelPlace(f"{name}_in", accepts),
        *(KernelPlace(f"{name}_{exit}", color)
          for exit, color in outcomes.items()),
        BoundaryTransition(name,
            arcs=(consume(f"{name}_in"),
                  *(produce(f"{name}_{exit}") for exit in outcomes)),
            work=wrap_selecting(fn)),      # fires once, emits ONE token
    )
    ...
```

```diagram
                              ┌──▶ name_approved (Approved)
┌─────────┐   ┌────────────┐ │
│ name_in │──▶│ name (T)   │─┼──▶ name_manual (ManualReview)
└─────────┘   └────────────┘ │
                              └──▶ name_failed (Failure)
```

The transition *has* an arc to every exit but *emits* exactly one
token per firing. Fan-out in structure, one path per token.

## Composition only renames

The single most load-bearing mechanic: `then`, `merge`, and `loop` add
**zero** nodes and **zero** arcs. They rewrite place names inside the
existing arcs and drop the absorbed place:

```python
# condensed exact — ax23_blocks.py::_rename, ::then
def then(a, b, *, on) -> Block:
    exit_port = a.exits[on]                       # refuse: no such exit
    require(exit_port.color == b.entry.color)     # refuse: colors differ
    mapping = {b.entry.place: exit_port.place}    # b's front door BECOMES
    return Block(                                 # a's named exit place
        nodes=a.nodes + rename(b.nodes, mapping),
        entry=a.entry,
        exits={**(a.exits - {on}), **b.exits},
    )
```

```diagram
before:  a_in ─▶ [a] ─▶ a_out      b_in ─▶ [b] ─▶ b_out
                              (fuse)
after:   a_in ─▶ [a] ─▶ a_out ─▶ [b] ─▶ b_out     no glue place,
                                                   no glue transition
```

`merge(block, "x", "y", into="z")` renames the places of same-colored
exits `x` and `y` to one surviving place. `loop(block, on="retry")`
renames the looping exit's place to the block's **own entry place** —
that one rename is what turns the tree expression into a cyclic graph
(chapter 7). Both refuse if the rewrite would give one transition two
arcs to the same place.

## Parallel adds a split and a join

`par` is the only combinator that adds transitions — the fork and the
join are real, visible nodes (chapter 6):

```python
# condensed exact — ax24_parallel.py::par
split = BoundaryTransition(name,
    arcs=(consume(entry), *(produce(b.entry.place) for b in branches)),
    work=copy_input_to_every_branch)
join = BoundaryTransition(f"{name}_join",
    arcs=(*(consume(b.exit_place) for b in branches), produce(out)),
    work=aggregate_by_branch_name)    # {branch_name: branch_data}
```

Refusals: fewer than two branches; a branch with more than one exit
(the join would wait forever on a token that cannot come).

## The rail is arrangement, not machinery

Chapter 8's rail composes the rules above — no new lowering exists:

```python
# condensed exact — ax25_rail.py
attempt(name, fn, ...)      # = outcomes(name, totalized(fn),
                            #     outcomes={"out": returns, "failed": FAILURE})
                            #   totalized: fn raises → failure envelope token
rail_then(a, b, on="out")   # = then(a, b, on) + merge both "failed"
                            #   exits into ONE rail place
recover(block, handler)     # = then(block, handler, on="failed")
                            #   + merge recovery back into the ok exit
```

After any chain there is exactly one failure place because `merge`
made it so — countable in the net, not promised by a convention.

## The claim bracket adds passthrough transitions

`holding(block, resource=...)` (chapters 3, 9) wraps the block in a
structural mutex made of handler-less transitions:

```python
# condensed exact — ax23_blocks.py::holding
claim = BoundaryTransition(f"claim_{ctx}",
    arcs=(consume(gate), consume(ctx),            # take the resource token
          produce(block.entry.place), produce(held)))
release_X = BoundaryTransition(f"release_{X}",    # one per exit
    arcs=(consume(exit_place), consume(held),
          produce(outer_exit), produce(ctx)))     # give the resource back
```

An empty resource place blocks every rival `claim` — mutual exclusion
as topology, no lock API anywhere.

## Value guards lower to CEL filters on arcs

Chapter 5's expression objects compile to CEL strings; the branch
lowers to one router per case, each admitted by a filtered arc
(spike: [AX6](../es3-workflow-ast-authoring-model/experiments/ax6-guard-branching/ax6_compiler.py)):

```diagram
                [score > 700]   ┌─────────────┐
             ┌─────────────────▶│ case_fast   │──▶ fast subtree
┌────────────┴─┐                └─────────────┘
│ branch_in    │
│ Application  │                ┌─────────────┐
└────────────┬─┘   [otherwise]  │ case_slow   │──▶ slow subtree
             └─────────────────▶└─────────────┘
```

In today's spec DSL the same thing is written directly:
`p.branch_in >> arc(filter="score > 700") >> t.case_fast` — the
filter string is what the expression object's `.cel()` produced.

## The node economy

What each construct costs, exactly:

| Construct | Places | Transitions | Arcs |
|---|---|---|---|
| `step` | +2 | +1 | +2 |
| `outcomes` (n exits) | +1+n | +1 | +1+n |
| `then` / `merge` / `rename` | −1 / −(n−1) / 0 | 0 | 0 |
| `loop` | −1 | 0 | 0 |
| `par` (n branches) | +2 | +2 | +2+2n |
| `holding` (n exits) | +3+n | +1+n | +4+4n |
| `attempt` | = `outcomes` with 2 exits | | |
| `rail_then` | = `then` + `merge` | | |

Composition being subtractive is why authored nets hit the
`arcs/(P+T) ≈ 1` signal from concept 10: linear flow adds no
connective tissue, so density comes only from real decisions,
parallelism, and shared state.

## From expression to running marking

The whole pipeline, with what each stage validates — captured live in
the ES-003 walkthrough
([04-end-to-end-walkthrough.md](../es3-workflow-ast-authoring-model/synthesis/04-end-to-end-walkthrough.md),
real output in
[walkthrough-capture.txt](../es3-workflow-ast-authoring-model/synthesis/walkthrough-capture.txt)):

```diagram
 AUTHORING TIME                                   RUNTIME
┌─────────────────────────────────────────────┐  ┌──────────────────────────┐
│ 1 authoring expression                      │  │ 6 engine execution       │
│     pyright/ty reject bad compositions      │  │     firings append to    │
│         ▼                                   │  │         ▼                │
│ 2 typed value (advisory static layer)       │  │ 7 persisted History      │
│         ▼  .inner                           │  │     replay recompiles    │
│ 3 Block value — eager CompositionError      │  │         ▼                │
│         ▼  nodes                            │  │ 8 identical marking      │
│ 4 kernel places/transitions/arcs            │  └──────────────────────────┘
│         ▼  check_sound + lower                          ▲
│ 5 serialized NetDefinition (deterministic) ─────────────┘
└─────────────────────────────────────────────┘   byte-identical recompilation
                                                  is what makes replay legal
```

Stages 1–5 run with no engine and no side effects. Nothing durable
ever holds a live Python object: stage 5 is plain data, and replay
(stage 8) recompiles from source and replays History over it
(concept 1).

## Where the exact code lives

| Rule | Exact source |
|---|---|
| `Block`, `step`, `outcomes`, `then`, `merge`, `loop`, `holding` | [ax23_blocks.py](../es3-workflow-ast-authoring-model/experiments/ax23-completed-algebra/ax23_blocks.py) |
| `par`, `par_fail_fast` | [ax24_parallel.py](../es3-workflow-ast-authoring-model/experiments/ax24-parallel-blocks/ax24_parallel.py) |
| `attempt`, `rail_then`, `recover` | [ax25_rail.py](../es3-workflow-ast-authoring-model/experiments/ax25-failure-rail/ax25_rail.py) |
| guard branch → CEL-filtered arcs | [ax6_compiler.py](../es3-workflow-ast-authoring-model/experiments/ax6-guard-branching/ax6_compiler.py) |
| AST → NetSpec lowering with source map | [ax2_compiler.py](../es3-workflow-ast-authoring-model/experiments/ax2-lower-sequence/ax2_compiler.py) |
| the staged pipeline, executed and captured | [capture_walkthrough.py](../es3-workflow-ast-authoring-model/synthesis/capture_walkthrough.py) |
