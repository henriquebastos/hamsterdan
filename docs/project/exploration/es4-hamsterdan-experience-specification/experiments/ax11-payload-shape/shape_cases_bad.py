"""AX11 static fixtures — three marked shape mistakes, each the
static twin of a runtime ShapeError. Unlike AX26's generic-parameter
mistakes (ty 0.0.63 missed 4/9), these are STRUCTURAL — attribute,
argument, return — and the harness asserts BOTH checkers catch all
three."""

from __future__ import annotations

from hamsterdan.contracts.readiness import ChangeResult, FindingPublicationRequest, RepairResult


def phantom_field(result: RepairResult) -> str:
    bad_attribute = result.risk_score  # expect-error
    return bad_attribute


def lying_adapter(result: RepairResult) -> FindingPublicationRequest:
    bad_return = result  # the twin of fuse_through's second fusion refusing
    return bad_return  # expect-error


def wants_repair(result: RepairResult) -> int:
    return result.epoch


change = ChangeResult(epoch=1, head="h", ok=True)
bad_argument = wants_repair(change)  # expect-error
