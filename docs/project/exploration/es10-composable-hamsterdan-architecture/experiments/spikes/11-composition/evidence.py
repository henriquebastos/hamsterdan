"""Execute the retained Experiment 11 causal proof, sensitivity, and reduction."""

from __future__ import annotations

import json
from typing import Any

from composition import run_causal_composition, run_workflow_failure_proof
from runtime import Artifact


def _artifact_summary(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_bytes": len(artifact.encode()),
        "journal_digest": artifact.journal_digest,
        "journal_entries": len(artifact.journal),
        "operations": len(artifact.operations),
        "scenario": artifact.scenario_id,
    }


def run() -> dict[str, Any]:
    causal = run_causal_composition()
    changed_result = run_causal_composition(proposed_commit_message="Apply bounded rename")
    cross = run_causal_composition(corrupt_handoff_authority=True)
    work_substitution = run_causal_composition(
        substitute_work_instruction="composition substituted this instruction",
    )
    local = run_workflow_failure_proof()
    return {
        "causal_composition": {
            **_artifact_summary(causal.artifact),
            "causal_blockers": causal.report.causal_blockers,
            "cross_violations": causal.report.cross_violations,
            "local_passed": causal.report.local_passed,
            "metrics": causal.metrics,
            "replay_exact": causal.replay.exact,
        },
        "coding_result_sensitivity": {
            "same_work": causal.metrics["workflow_work"] == changed_result.metrics["workflow_work"],
            "same_request": causal.metrics["delivered_request"] == changed_result.metrics["delivered_request"],
            "same_publication_payload_digest": (
                causal.metrics["publication_payload_digest"] == changed_result.metrics["publication_payload_digest"]
            ),
            "coding_result_digests": [
                causal.metrics["publication_coding_result_digest"],
                changed_result.metrics["publication_coding_result_digest"],
            ],
            "result_heads": [
                causal.metrics["publication_result_head"],
                changed_result.metrics["publication_result_head"],
            ],
            "replay_exact": causal.replay.exact and changed_result.replay.exact,
        },
        "composition_authority_observation": {
            **_artifact_summary(cross.artifact),
            "causal_blockers": cross.report.causal_blockers,
            "cross_violations": cross.report.cross_violations,
            "local_passed": cross.report.local_passed,
            "replay_exact": cross.replay.exact,
            "scope": cross.report.scope,
        },
        "composition_work_substitution_observation": {
            **_artifact_summary(work_substitution.artifact),
            "causal_blockers": work_substitution.report.causal_blockers,
            "cross_violations": work_substitution.report.cross_violations,
            "local_passed": work_substitution.report.local_passed,
            "readiness_instruction": work_substitution.metrics["readiness_work"]["instruction"],
            "replay_exact": work_substitution.replay.exact,
            "scope": work_substitution.report.scope,
            "workflow_instruction": work_substitution.metrics["workflow_work"]["instruction"],
        },
        "workflow_localization": {
            **_artifact_summary(local.artifact),
            "local_violations": local.report.local_violations,
            "reducible_to": local.report.reducible_to,
            "reduced": {
                **_artifact_summary(local.reduced_artifact),
                "replay_exact": local.reduced_replay.exact,
                "violations": local.reduced_violations,
            },
            "replay_exact": local.replay.exact,
            "scope": local.report.scope,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
