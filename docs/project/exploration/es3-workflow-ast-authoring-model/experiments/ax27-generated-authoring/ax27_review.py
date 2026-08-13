"""AX27 — ``review``: the composition authority as a machine feedback loop.

A generator (an agent, a scaffolder, any producer of authoring source)
needs a total, deterministic reviewer: every candidate source, however
broken, must come back as structured feedback — never a crash, never a
silent pass, and **never execution of the net**. This module is that
reviewer, general by construction: it knows the authoring contract
(the candidate defines ``workflow() -> Block``), not any workflow.

Stages, in the order a candidate meets them:

- ``source`` — the text does not parse (``SyntaxError``).
- ``author`` — executing the authoring source or calling ``workflow()``
  is refused: the algebra's eager ``CompositionError``s land here, as
  does any other exception generated code can produce.
- ``sound`` — the composed Block fails ``compile_block``'s
  ``check_sound``. Combinator-only source rarely reaches this stage
  (the algebra refuses eagerly); it exists for candidates that descend
  to dataclass surgery on Block internals.

What this module deliberately does NOT do: create an Engine, seed a
token, or advance anything. Motion is a separate, explicit stage the
loop's operator opts into (AX28's ``first_motion``). Reviewing DOES
execute the candidate's *authoring* code — composition in this design
is ordinary Python — so a generation loop runs review with exactly the
trust it extends to the generated source itself; the static stage
(pyright over the AX26 façade) is the no-execution alternative.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from ax23_blocks import Block, BoundaryTransition, CompositionError, KernelPlace, compile_block
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition


@dataclass(frozen=True)
class Feedback:
    """One candidate's structured review result."""

    candidate: str
    verdict: str  # "ok" | "refused"
    stage: str | None  # "source" | "author" | "sound" when refused
    error: str | None  # exception type name when refused
    message: str | None  # the authority's message, verbatim
    line: int | None  # offending line in the candidate source, when known
    places: int  # net statistics when ok
    transitions: int
    exits: tuple[str, ...]
    definition_bytes: int


def _refused(name: str, stage: str, exc: BaseException, line: int | None) -> Feedback:
    return Feedback(
        candidate=name,
        verdict="refused",
        stage=stage,
        error=type(exc).__name__,
        message=str(exc),
        line=line,
        places=0,
        transitions=0,
        exits=(),
        definition_bytes=0,
    )


def _candidate_line(exc: BaseException, filename: str) -> int | None:
    """The deepest frame of the failure that lies in the candidate's own
    source — the line a mechanical repair should look at first."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == filename]
    return frames[-1].lineno if frames else None


def review(name: str, source: str) -> Feedback:
    """Review one candidate authoring source. Total: any outcome is a
    ``Feedback``, and no net is ever executed."""
    filename = f"<candidate:{name}>"
    try:
        code = compile(source, filename, "exec")
    except SyntaxError as exc:
        return _refused(name, "source", exc, exc.lineno)

    namespace: dict = {"__name__": f"ax27_candidate_{name}"}
    try:
        # Reviewing generated authoring source IS executing Python — the
        # composition layer is ordinary code by design. The module
        # docstring states the trust contract; the static stage is the
        # no-execution alternative.
        exec(code, namespace)  # noqa: S102 — the spike's very subject
        factory = namespace.get("workflow")
        if not callable(factory):
            raise CompositionError(
                "candidate defines no callable 'workflow'; the authoring contract is workflow() -> Block"
            )
        block = factory()
        if not isinstance(block, Block):
            raise CompositionError(f"workflow() returned {type(block).__name__}, not a Block")
    except BaseException as exc:  # noqa: BLE001 — total by contract: all failures become feedback
        return _refused(name, "author", exc, _candidate_line(exc, filename))

    try:
        lowered = compile_block(f"review-{name}", block)
    except BaseException as exc:  # noqa: BLE001
        return _refused(name, "sound", exc, _candidate_line(exc, filename))

    definition = serialize_net_definition(project_net_definition(lowered.built.net))
    return Feedback(
        candidate=name,
        verdict="ok",
        stage=None,
        error=None,
        message=None,
        line=None,
        places=sum(isinstance(node, KernelPlace) for node in block.nodes),
        transitions=sum(isinstance(node, BoundaryTransition) for node in block.nodes),
        exits=tuple(sorted(block.exits)),
        definition_bytes=len(definition),
    )
