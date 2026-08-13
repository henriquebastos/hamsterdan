"""AX11 static fixtures — the well-typed adapter path. Must be
diagnostic-free under both pyright and ty: ordinary signatures on
production models, no casts, no explicit type arguments."""

from __future__ import annotations

from hamsterdan.contracts.readiness import FindingPublicationRequest, RepairResult


def announce_repair(result: RepairResult) -> FindingPublicationRequest:
    """The AX4 adapter, honestly typed: every field it uses exists,
    and both checkers verify the construction it returns."""
    return FindingPublicationRequest(
        epoch=result.epoch,
        head=result.head,
        operation=result.operation,
        base_head="",
        policy_digest="",
        findings=[],
        lineage=[],
    )


def repair_landed(result: RepairResult) -> bool:
    return result.ok and bool(result.provisional_head)
