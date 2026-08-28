# Engineering conventions

This document owns reusable implementation practice for Hamsterdan. Product and
architecture choices belong in decision records, accepted structural costs
belong in the debt ledger, and one change's findings belong in its roadmap,
Refinement, Exploration, or worklog record. Add a convention here only when a
practice should guide future changes.

A more specific decision, specification, or roadmap constraint overrides a
general convention. Surface the conflict during planning or review rather than
choosing silently. Promote mechanically checkable structure into the repository
quality gate when one clear test owner can enforce it.

## Architecture and boundaries

1. Import Petrus concepts from their defining ownership modules; never from the
   empty `petrus` root and never from an `impetus` compatibility namespace.
2. The host is the only concrete application composition root. In current V5,
   Engine, concrete Dispatch, and Worker custody remain under `host`, and
   provider/domain siblings share only neutral contracts. In non-selectable
   `hamsterdan2`, the more specific CV21/CV22 architecture applies: readiness
   owns one-PR Petrus execution and receives concrete capabilities from host
   composition; workflow owns pure boundary and later Net meaning.
3. The workflow Net owns routing and workflow state. In current V5 it lives
   under readiness; in CV22 it lives under the workflow owner behind CV21's
   unchanged boundary. Activities perform typed, Petri-agnostic work and return
   frozen JSON-faithful results. If an Activity cannot derive cleanly, first
   inspect whether routing, classification, a join, reservation, or authority
   transfer is hidden outside the Net.
4. Normalize provider data at the boundary. GitHubKit and provider HTTP values
   remain in `github_app`; FastAPI remains at the host HTTP boundary. Do not let
   SDK or HTTP types cross into contracts, readiness, or the Net. A third-party
   library gets exactly one boundary module; code above it speaks domain
   vocabulary and cannot tell which library is underneath.
5. Keep CLIs, servers, workers, and transports as thin adapters over importable
   operations. Parse syntax and operator intent at the outside edge; inner
   operations return values or structured reports rather than printing or
   exiting.
6. Prefer coherent modules over one file per noun, but split responsibilities
   before provider, workflow, and hosting concerns accumulate in one module.
   Use a function for a narrow operation with little state. Use an object when
   bound state materially reduces the interface or enforces an invariant. No
   `utils.py` or `helpers.py`; module names are singular for one concept and
   plural for a family.

## Durable values and effects

7. Validate semantic invariants at the boundary that owns them and before
   recording an irreversible fact. Once a webhook, History fact, or Activity
   result becomes durable, later code may rely on it without repeating foreign
   input validation.
8. Snapshot a payload into its canonical durable representation when equality
   controls deduplication, acknowledgement, conflict detection, or recovery.
   Reject an unencodable value at the admitting boundary rather than after a
   partial durable write.
9. Pass a ruled seam contract across the seam whole. An Activity receives the
   typed invocation fields needed for execution and recovery, including current
   authority, operation identity, correlation, and resolved policy. Do not
   replace that carrier with a convenient projection that drops a ruled field.
10. Effects are at-least-once. Spend operation identity at the provider call,
    fence current authority immediately before mutation, and recover uncertain
    outcomes lookup-first. Tests and documentation state the weakest honest
    guarantee and never claim exactly-once effects.
11. An Activity retry policy follows mutation order. Retry failures that happen
    before mutation. A mutating Activity earns retries only through a permanent
    callee-owned idempotency key or an equivalent lookup-first recovery contract.
12. Credentials are opaque, redacted, host-owned values. Logs use identifiers,
    request IDs, rate-limit facts, and bounded error classes, never tokens, keys,
    authorization headers, or indiscriminate payloads. Agent territory receives
    only bounded credential-free values.

## Tests and evidence

13. Test public behavior and the reason it matters rather than incidental helper
    decomposition. A pure semantic unit still earns a direct test when that test
    names a failure more precisely than broader pipeline coverage.
14. Patch at the seam the unit owns. Prefer strict, small fakes whose unknown
    inputs fail loud. A stand-in must not invent plausible responses. Fake only
    the expensive or nondeterministic seam; use real objects everywhere else.
15. Assert complete records when shape is the contract, including ordering,
    multiplicity, payload, operation identity, and correlation. Use partial
    assertions only for fields that are genuinely dynamic and irrelevant to the
    behavior under test. Exception payloads are contract too: assert their args
    and `__cause__` chains exactly.
16. Performance claims require a named bounded workload, concurrency and
    environment, timing or memory evidence, observed failures, and relevant
    ordering or cache caveats. An architectural improvement alone is not a
    throughput claim.
17. Production functions should ordinarily have cyclomatic complexity at most
    10. Values from 11 through 15 require review; values above 15 require a
    focused refactoring candidate or a narrow documented exception for a
    cohesive parser, state machine, workflow fold, or lifecycle operation. Until
    RS-030 classifies the existing baseline, `C901` remains a non-blocking audit.
18. Prefer composition and dependency injection over patching. Pass
    collaborators through owned typed ports and inject strict fakes in tests.
    `unittest.mock` and monkeypatching remain available at seams the module
    does not own, but a test that can receive its collaborator should receive
    it. Effect sources — randomness, environ, clock, sleep, paths, secrets —
    enter as keyword-default parameters that tests override; never a DI
    framework.

## Python style defaults

These Python style defaults apply to new Hamsterdan code from 2026-08-26
onward. Departures require a design reason during review. This document contains
the repository's maintained guidance; each item keeps its stable rule slug.
The existing V5 tree is not retrofitted. Mechanical enforcement of the tier (a)
subset belongs to the `hamsterdan2` gate owned by CV21.DS1. Rules already covered
by conventions 4, 6, 14, 15, and 18 are merged into those items.

### Types and values

19. *(concepts-as-native-subtypes)* A domain concept that IS one value — an
    id, a path, an amount, a country — is a subtype of the native type it
    refines. Validation lives at instantiation so an invalid instance cannot
    exist: in `__new__` when the parent type is immutable (`str`, `tuple`,
    `Decimal`), in `__init__` when it is mutable. Format and algebra live on
    the type; Pydantic schema dunders where serialization matters.
20. *(behavior-lives-with-data)* A container-shaped concept carries its domain
    verbs, so call sites read as domain sentences instead of dict plumbing.
    Choose the shape by how close the behavior stays to the native container,
    escalating only as far as the divergence requires:
    1. Use the bare container when there is no behavior to carry.
    2. Inherit the container when the behavior is the container's own plus
       domain verbs.
    3. Encapsulate the data and implement the fitting abstract base classes
       when the contract diverges from the parent's — a read-only view
       implements an immutable `Mapping` over an internal dict rather than
       inheriting `dict`.
    4. Encapsulate the data and derive further structures from it — indexes
       over the original data — implementing the protocols each view needs.
21. *(payload-shaped-helpers)* When an object's whole purpose is to be a
    serialized payload, subclass the payload shape and populate it in
    `__init__`; no class-plus-`.to_dict()` wrapper.
22. *(sentinels-guard-intent)* When `None`, `''`, and `False` are all legal
    values, guard "not provided" with a module-level sentinel checked by
    identity; reach for stdlib ready-mades before hand-rolling.
23. *(null-objects-over-none-checks)* Close a missing-collaborator case with a
    read-only empty implementation instead of `if x is not None` branches on
    the composition path.
24. *(dataclass-earns-its-place)* Use a dataclass only where it removes real
    boilerplate, never as a category default. Frozen at real boundaries;
    internal plumbing stays plain tuples, dicts, and sets.
25. *(no-post-init-validation)* A primitive validated in `__post_init__` wants
    a more expressive type validating at instantiation. Only when several
    objects must be validated together may a dumb `__post_init__` call a
    staticmethod validator.
26. *(pydantic-at-the-boundary)* Pydantic models are shape authority for
    external input and serialized output, never the internal default. Native
    subtypes carry their own schema hooks so they compose into models.

### Composition and structure

27. *(pure-core-effectful-rim)* Domain logic raises and returns; only the rim
    — CLI, server, worker, `__main__` — prints, exits, renders, or touches the
    network. Dependencies point inward.
28. *(extend-hosts-at-their-seams)* Slot capability into the host library's
    own extension points, presenting the host's own interface; nothing a user
    of the host already knows becomes wrong.
29. *(named-factories-own-composition)* Wiring lives in intention-named
    constructors (`from_config`, `in_memory`, `for_session`); `__init__` stays
    assignment.
30. *(class-attribute-config)* Defaults are class attributes with instance
    override; consumers configure by declarative subclassing.
31. *(layered-precedence-in-one-sentence)* Layered overrides carry a
    precedence the user can state in one sentence, with each layer
    independently omittable.
32. *(composed-default-exposed-phases)* Offer a one-call default that composes
    public phases, so platforms that must interpose between phases can while a
    plain caller uses the one-liner.
33. *(vocabulary-tables-over-branching)* Flat dispatch is a named module-level
    constant table; `match`/`case` is for structural destructuring only, never
    a substitute for a type/value → handler map.
34. *(magic-sized-to-behavior)* Python magic only to unlock behavior: name the
    user-visible behavior the magic unlocks, or delete the magic.
35. *(use-the-languages-leverage)* Prefer the stdlib's own algebra and dunder
    protocols where the protocol matches the concept, over hand-rolled loops
    and methods.
36. *(strategy-objects-minimal-weight)* Strategies are tiny objects with a
    test/apply contract; the base class exists only for what it truly shares;
    composition is a module-constant tuple; no ABC, no registration framework.
37. *(returns-designed-for-composition)* Design return values for the sentence
    the caller wants to write, and raise before mutating so a composed
    expression cannot half-complete.
38. *(structural-cost-awareness)* Encode cost-awareness in structure, not
    flags: do expensive work only when a declared consumer exists.
39. *(events-encapsulated-at-their-seam)* Capture progress and events in an
    object at the seam where they occur, consumed through a native protocol —
    no callbacks, polling flags, or shared counters in user code.
40. *(optional-deps-degrade-in-isolation)* An optional integration lives in
    its own module and degrades to a typed shim or empty table; the core never
    imports the optional dependency.
41. *(protocols-disfavored)* `typing.Protocol` is disfavored as a default; the
    remedy is not ABC-everywhere either. Prefer native-type subtypes,
    composition, and small callable contracts.
42. *(imports-at-the-top)* Imports live at the top of the module. A
    function-local import is legal only at a composition rim to break a
    genuine circular import, with the cycle named in a comment — and such a
    cycle is itself a design smell to surface. In `src/hamsterdan2` the ban is
    outright: a cycle means the module graph is wrong.

### Errors

43. *(exceptions-name-domain-outcomes)* Conditions worth naming get a type,
    and business errors get their hierarchy from the start: a base domain
    exception — on plain `Exception`, or whatever base makes more sense —
    with the named outcomes as its empty subclasses, separating business
    errors from technical ones so callers choose their granularity and an
    except clause catches the family instead of enumerating members. Routing
    them IS the business rule. Taxonomies respect the host contract
    (traversal errors subclass `KeyError`); chain causes with
    `raise ... from`; args carry location context. Beyond the base, the
    deeper hierarchy is a nudge, not a mandate: grow it as usage reveals the
    need, and earlier when the exceptions carry custom values beyond a
    message.
44. *(failure-as-data-when-persisted)* Where the system must store or replay
    failures, failure becomes persisted state instead of an exception taxonomy
    — a design-dependent variant, not a preference reversal.
45. *(errors-instruct-next-action)* An error message is part of the API: name
    the fix, list what was expected and what is available.
46. *(fail-fast-accumulated)* Construction validates bindings and
    configuration fast and reports every problem in one message, not
    one-at-a-time; expose the same check statically for design-time use.

### Naming and language

47. *(names-state-capability)* Names state capability or intention; objects
    converse in domain verbs. Tell, don't ask: internal state is revealed
    through predicate methods — `is_*`/`can_*`/`has_*`, returning booleans —
    never by exporting its representation for callers to compare. The
    predicate encapsulates the check, so tests and callers need not know
    whether the state is an enum, an attribute, or a combination of several
    internal data, and the interface can express a higher-level state than
    any single field holds.
48. *(nouns-verbs-and-english)* Distinguish what a class has (noun) from what
    it does (verb); themed role-specific names over generic `Service`
    suffixes; a method name never repeats its class name; the simplest
    unambiguous name is the right name; never shadow builtins.
49. *(narrative-principle)* The public interface of a class reads like a clear
    sentence: a reviewer inspecting the object should immediately understand
    what it represents, what state it tracks, and what it can do.
50. *(adopt-the-specs-vocabulary)* When an authoritative external spec exists,
    use its vocabulary wholesale in names, docstrings, and test claims.
51. *(state-machine-vocabulary)* A state machine is a transitions table, a
    `transition()` validator raising a domain exception naming both states,
    verb transition methods, `is_*` predicates, and past-tense state names —
    no gerunds. Enums stay private to the owning class; readers use the
    predicates.
52. *(resume-points-named-for-persistence)* Cursor fields are named for the
    persisted resume boundary, not `cursor`. Vocabulary: "batch" is a durable
    work unit; "page" is a transient query window.

### Comments and documentation

53. *(why-invariants-only)* Comments state the why or invariant the code
    cannot show, or the foreign mechanism being interposed on — never what the
    next line does. A governing invariant is deliberately duplicated verbatim
    at every enforcement site.
54. *(docstrings-are-contracts)* Docstrings are rare and load-bearing, stating
    semantics a reader cannot recover from the code. No paraphrase docstrings.
55. *(readme-is-a-tested-demo)* The README develops one realistic worked
    example, and a test executes that example verbatim so the demo cannot rot.
56. *(main-blocks-as-executable-docs)* A leaf or tool module may end with a
    `if __name__ == '__main__':` block running a realistic demo a reader can
    learn usage from. Permitted, not mandated.

### Tests

57. *(scenario-classes-with-contract-docstrings)* Test classes are scenarios
    with a one-line contract docstring; methods are tiny behavior sentences;
    arrange/act/assert separated by blank lines, near-zero comments. Test
    files split by behavior seam, encoding subject and scenario with `__`.
58. *(test-environment-is-a-domain-dsl)* Test helpers live on the test class
    or a conftest builder and speak the domain, with custom assertions naming
    outcomes.
59. *(pin-the-full-state-transition)* State-machine tests assert the complete
    relevant delta — marking plus rows plus identity, register plus flag. This
    is the ruled exemption to one-behavior-per-test.
60. *(one-behavior-per-test-scoped)* One reason to fail, applied to unrelated
    assertions; full-state pinning (convention 59) is the explicit exemption.
61. *(assert-truthiness-with-contract-precision)* `assert results` over
    `assert len(results) > 0`; but keep `is None` where None-ness is the
    contract. Never trade contract precision for brevity.
62. *(ceremony-sized-to-weight)* Test ceremony scales with project weight, but
    some executable safety net exists from the first commit; a golden master
    is the cheapest one when refactoring working code.

### Call-site expression

63. *(kwargs-for-clarity)* Keyword arguments for calls with three or more
    arguments, or any boolean argument. Guidance, not a blanket mandate.
64. *(walrus-for-simple-expressions)* The walrus operator is preferred for
    simple assign-then-check, avoided on complex expressions, never mandatory.
65. *(guard-clauses-with-reasons)* Flat functions with sequential early
    returns, no else-ladders; each guard states its domain reason.
66. *(dependencies-earn-their-place)* Near-zero runtime dependencies: every
    new dependency is justified by what the stdlib cannot do.

### Process

67. *(history-as-designed-narrative)* One design move per commit, named for
    its intent and reviewable alone; one ruling is one commit naming the
    incident.
68. *(operator-safety-surface)* Destructive scope is explicit and opt-in; all
    options validate before any side effect; dry-run is implemented at the
    real seam so it rehearses the exact production path.

### The typed-data decision boundary

The organizing question is not "what kind of class is this?" but how far the
data travels, and whether it is a concept or a record: the wider a piece of
data travels, the stronger its shape must be. First match wins:

1. One value with domain meaning → native-type subtype validating at
   instantiation (`__new__` for an immutable parent, `__init__` for a mutable
   one). Never a one-field dataclass, never Pydantic.
2. External input or durable/serialized output at a system boundary →
   Pydantic model; partial updates as all-optional models.
3. The object is itself the serialized contract and carries behavior →
   dict/list subtype populating itself in `__init__`; no `.to_dict()` wrapper.
4. Dict-shaped data with a known shape crossing a seam → TypedDict names the
   shape. `dict[str, Any]` in a public signature is the smell; the fix is a
   name, not a class.
5. A several-field record whose class would be `__init__` boilerplate →
   dataclass, frozen at real boundaries; field types validate themselves, and
   a dumb `__post_init__` calls a staticmethod validator only for
   multi-object checks.
6. Transient internal plumbing → plain tuples, dicts, sets, and dict
   expressions; the ceremony saved is the point.
7. A primitive → return it bare.
