# ES-003 theory reference ledger

Literature, authors, and named concepts behind the AX-series findings —
captured so future digging starts from names, not from memory. Each
entry states why it matters to this exploration and which experiments
it touches. Entries are leads, not endorsements; none were inspected as
authoritative sources during the experiments.

## Structured control flow (the "combinators are the only control flow" argument)

- **Structured program theorem** — Corrado Böhm & Giuseppe Jacopini,
  *Flow Diagrams, Turing Machines and Languages with Only Two Formation
  Rules*, CACM 9(5), 1966. All control flow reduces to sequence,
  choice, iteration. The formal license for a closed combinator set
  (AX1, AX8, AX22 candidate).
- **Goto considered harmful** — Edsger W. Dijkstra, *Go To Statement
  Considered Harmful*, CACM 11(3), 1968; and *Notes on Structured
  Programming*, 1972. The Navigator's "Petri nets can express
  everything, but is everything desired?" is this argument: arbitrary
  arcs are gotos; restriction buys analyzability.
- **SESE regions / program structure tree** — Richard Johnson, David
  Pearson, Keshav Pingali, *The Program Structure Tree: Computing
  Control Regions in Linear Time*, PLDI 1994. The compiler-theory name
  for the single-entry/single-exit fractal AX20 tested; the nesting of
  blocks is the program structure tree.

## Petri net and workflow theory

- **Petri nets** — Carl Adam Petri, *Kommunikation mit Automaten*,
  dissertation, 1962. The substrate.
- **Coloured Petri nets** — Kurt Jensen, *Coloured Petri Nets* (3 vols,
  1992–1997); Jensen & Lars M. Kristensen, *Coloured Petri Nets:
  Modelling and Validation of Concurrent Systems*, 2009. Typed tokens;
  Petrus's nominal string colors are a restricted CPN.
- **Workflow nets and soundness** — Wil van der Aalst, *The Application
  of Petri Nets to Workflow Management*, Journal of Circuits, Systems
  and Computers 8(1), 1998. One entry, one exit, every node on an
  entry→exit path, no residual marking, no dead transitions — the
  property AX20 turned into tests ("no interior marking survives").
- **Block-structured (well-structured) workflow models** — Bartek
  Kiepuszewski, Arthur ter Hofstede, Christoph Bussler, *On Structured
  Workflow Modelling*, CAiSE 2000. Nets built only by recursive
  sequence/AND/XOR/loop composition are sound by construction — the
  theorem behind the AX22 candidate ("control statements may only call
  functions").
- **Workflow patterns** — van der Aalst, ter Hofstede, Kiepuszewski,
  Alistair Barros, *Workflow Control-Flow Patterns*, Distributed and
  Parallel Databases 14(1), 2003; <http://www.workflowpatterns.com>.
  The catalog the AX1–AX8 combinator set should be checked against for
  coverage claims. AX23 leans on three named distinctions: **Simple
  Merge (WCP-5)** vs **Synchronization (WCP-3)** — convergence never
  pairs or waits, the AND-join does; **Structured Loop (WCP-21)** —
  the tree-expression cycle; and the separate **Workflow Resource
  Patterns** catalog (Nick Russell, ter Hofstede, van der Aalst, David
  Edmond) for what `holding` is a fragment of.
- **Contextual nets / read arcs** — Ugo Montanari & Francesca Rossi,
  *Contextual Nets*, Acta Informatica 32(6), 1995. The formal
  semantics of an arc that checks without consuming — concurrent
  readers do not conflict. The frozen engine's read arcs, and AX23's
  `reads=` context ports, are this construct.
- **YAWL** — van der Aalst & ter Hofstede, *YAWL: Yet Another Workflow
  Language*, Information Systems 30(4), 2005. Prior art for a
  patterns-complete workflow language over Petri-net semantics.
- **Free-choice nets** — Jörg Desel & Javier Esparza, *Free Choice
  Petri Nets*, Cambridge Tracts in Theoretical Computer Science 40,
  1995. The analyzable subclass where conflict and synchronization
  never mix; a candidate constraint class for what the composition
  layer should be allowed to generate (the AX20/AX21 complementary-exit
  pairs are free-choice-like conflicts).

## Structured concurrency

- **Nurseries / "go statement considered harmful"** — Nathaniel J.
  Smith, *Notes on structured concurrency, or: Go statement considered
  harmful*, njs blog, 2018 (the Trio library's design essay; Python).
  Parallel branches may not outlive their enclosing block — AX4's
  AND-join discipline stated as a language rule.

## Functional composition theory (the vocabulary the Navigator asked for)

- **Why Functional Programming Matters** — John Hughes, The Computer
  Journal 32(2), 1989. The general case for composition and laziness as
  glue; the best first read.
- **Functional core, imperative shell** — Gary Bernhardt, *Boundaries*
  talk, 2012. Pure interiors, effects at the edges — AX20's
  prepare-then-commit shape in program-design form.
- **Monads for effects** — Eugenio Moggi, *Notions of Computation and
  Monads*, Information and Computation 93(1), 1991. Sequencing effectful
  computation; `sequence` as Kleisli composition.
- **Applicative functors** — Conor McBride & Ross Paterson,
  *Applicative Programming with Effects*, JFP 18(1), 2008. The
  static/dynamic divide: applicative structure is fully known before
  execution — the theoretical reason the combinator AST (AX1, AX10) is
  serializable and replayable while generator workflows are not.
- **Selective applicative functors** — Andrey Mokhov, Georgy Lukyanov,
  Simon Marlow, Jérémie Dimino, ICFP 2019. Branching without losing
  static analyzability — the exact shape of `choice(case(...), ...)`
  (AX6/AX7).
- **Arrows** — John Hughes, *Generalising Monads to Arrows*, Science of
  Computer Programming 37, 2000; Ross Paterson, *A New Notation for
  Arrows*, ICFP 2001. The algebra of boxes with input/output ports
  composed by sequence (`>>>`), parallel (`***`), choice (`|||`) — the
  mathematical home of the combinator set, and its laws are free design
  tests for the composition layer.
- **Railway-oriented programming** — Scott Wlaschin,
  *Railway Oriented Programming*, NDC Oslo 2014;
  <https://fsharpforfunandprofit.com/rop/>. The two-track (success /
  failure) composition picture behind binary `Result` pipelines —
  composable-functions is this pattern industrialized. Relevant to the
  AX25 question: can a uniform failure rail be authoring sugar that
  expands into *visible* net structure rather than a hidden channel?
- **Validation applicative (error accumulation)** — the
  accumulate-all-errors-instead-of-failing-fast composition, e.g. Jane
  Street's / Scalaz-cats `Validation` and McBride & Paterson §"monoidal
  accumulation". The semantics of composable-functions' `all` (every
  branch finishes, every failure aggregated) and the theory behind an
  AND-join policy choice (AX24).
- **Composable Functions (inspected, not a lead)** — Seasoned,
  <https://github.com/seasonedcc/composable-functions>, v5.0.0,
  TypeScript; successor to their `domain-functions`. Deep-inspected
  2026-08-12; full comparison in
  [composable-functions.md](composable-functions.md). Key transferable
  facts: total `Result`-returning functions, all-errors parallel
  aggregation, `FailToCompose<A, B>` non-callable diagnostic types,
  closure-threaded ambient context, and two removals that validate our
  doctrines (`merge` for non-totality, `first` for racing effects).

## Effects as values

- **Algebraic effects and handlers** — Gordon Plotkin & John Power,
  *Algebraic Operations and Generic Effects*, Applied Categorical
  Structures 11(1), 2003; Gordon Plotkin & Matija Pretnar, *Handlers of
  Algebraic Effects*, ESOP 2009. Effects described as data, interpreted
  by handlers at a boundary — the theory behind AX9's Interpretation A
  (effects interpreted inside one activity).
- **Free monads / extensible effects** — Wouter Swierstra, *Data Types
  à la Carte*, JFP 18(4), 2008; Oleg Kiselyov & Hiromi Ishii, *Freer
  Monads, More Extensible Effects*, Haskell Symposium 2015. Programs as
  data structures interpreted later; the `stateless` Python library
  (already a standing ES-002 input) descends from this line.

## Linear logic and resources (why the AX20 claim token is principled)

- **Linear logic** — Jean-Yves Girard, *Linear Logic*, Theoretical
  Computer Science 50(1), 1987. Propositions as consumable resources.
- **Petri nets as linear logic models** — Uffe Engberg & Glynn Winskel,
  *Petri Nets as Models of Linear Logic*, CAAP 1990; Narciso
  Martí-Oliet & José Meseguer, *From Petri Nets to Linear Logic*,
  Mathematical Structures in Computer Science 1(1), 1991. The formal
  correspondence: a token is a linear value, consumed exactly once.
  AX20's structural mutex ("neither lost nor duplicated") is the
  linearity law made physical.
- **Linear types** — Philip Wadler, *Linear Types Can Change the
  World!*, IFIP TC2 Programming Concepts and Methods, 1990. The typed
  claim/release discipline, if the composition layer ever wants to
  check it statically.
- **Semaphores and mutual exclusion** — Edsger W. Dijkstra,
  *Cooperating Sequential Processes*, EWD 123, 1965 (published 1968).
  AX23's `holding` bracket is a binary semaphore made structural: the
  context place is the semaphore, claim is P, release is V, and an
  AX19 arc weight would make it counting.
- **Resource bracketing** — the acquire/use/release-on-every-exit
  shape: Haskell's `Control.Exception.bracket` (Marlow et al., GHC),
  Python's context managers (PEP 343, Guido van Rossum & Nick
  Coghlan, 2005), C++ RAII (Bjarne Stroustrup, *The C++ Programming
  Language*). `holding` compiles this shape into net structure — one
  release transition per terminal exit, so the failure path returns
  the resource too.
- *Peripheral:* session types — Kohei Honda et al.; Philip Wadler,
  *Propositions as Sessions*, ICFP 2012. Only relevant if subnet
  boundaries ever become bidirectional protocols.

## Idempotency and distributed effects engineering (AX21's territory)

- **Idempotence as a design requirement** — Pat Helland, *Idempotence
  Is Not a Medical Condition*, ACM Queue 10(4), 2012. The at-least-once
  world where AX21's outcome classification lives.
- **Life beyond distributed transactions** — Pat Helland, CIDR 2007.
  Operation identity, activity-based dedup, no global transactions —
  the doctrine behind lookup-first recovery.
- **Sagas** — Hector Garcia-Molina & Kenneth Salem, *Sagas*, SIGMOD
  1987. Compensation for long-lived transactions — the machinery AX20
  *deliberately excluded* (discard-and-restart instead of compensate);
  cite when explaining that exclusion.
- **Event sourcing** — Martin Fowler, bliki entry *Event Sourcing*,
  2005; Greg Young's CQRS/ES writings. The Petrus History posture;
  AX21's replay test (recorded outcomes, fresh ledger untouched) is
  this discipline verified.
- **Durable execution** — Temporal/Cadence documentation on
  deterministic replay and the workflow/activity split. Engineering
  (not academic) prior art for "the net is durable, the effect executor
  is not"; matches Petrus's dispatcher/worker boundary and the
  no-live-generator-frames rule.

## Net metrics (the arc/node and hub-degree discussion)

- **Control-flow complexity (CFC)** — Jorge Cardoso, *How to Measure
  the Control-Flow Complexity of Web Processes and Workflows*, in
  Workflow Handbook 2005; *Business Process Control-Flow Complexity:
  Metric, Evaluation, and Validation*, IJWSR 5(2), 2008.
- **Process model metrics** — Jan Mendling, *Metrics for Process
  Models*, LNBIP 6, 2008. Density and connector-degree metrics; the
  measured finding (2026-08-12) that global arcs/nodes barely moves
  (1.43 → 1.31) while hub degree is the real smear witness (authority
  degree 6 and growing per concern vs bounded ≤ 3) refines these for
  this project — **bounded place degree independent of net size** is
  the candidate lint invariant (AX23 candidate).

## Suggested first digs

1. Smith 2018 (structured concurrency) — closest to home for a Python
   specialist, directly motivates the composition layer.
2. Kiepuszewski/ter Hofstede/Bussler 2000 — the soundness-by-
   construction theorem AX22 would rest on.
3. Helland 2012 — the idempotency taxonomy AX21 implemented.
4. Hughes 2000 (arrows) — the algebra the combinator core should
   satisfy before it grows.
