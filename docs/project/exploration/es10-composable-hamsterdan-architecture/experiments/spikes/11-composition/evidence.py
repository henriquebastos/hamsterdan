"""Execute the retained Experiment 11 co-mounting counterexample and reduction."""

from __future__ import annotations

import json
from typing import Any

from composition import run_co_mounting_counterexample, run_workflow_failure_proof
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
    comounting = run_co_mounting_counterexample()
    cross = run_co_mounting_counterexample(corrupt_handoff_authority=True)
    local = run_workflow_failure_proof()
    return {
        "co_mounting_counterexample": {
            **_artifact_summary(comounting.artifact),
            "causal_blockers": comounting.report.causal_blockers,
            "cross_violations": comounting.report.cross_violations,
            "local_passed": comounting.report.local_passed,
            "metrics": comounting.metrics,
            "replay_exact": comounting.replay.exact,
        },
        "co_mounting_authority_observation": {
            **_artifact_summary(cross.artifact),
            "causal_blockers": cross.report.causal_blockers,
            "cross_violations": cross.report.cross_violations,
            "local_passed": cross.report.local_passed,
            "replay_exact": cross.replay.exact,
            "scope": cross.report.scope,
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
