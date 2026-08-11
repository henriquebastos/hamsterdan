"""AX1 focused tests — construction, traversal, identity, canonical form.

Activity names are real Hamsterdan activity registrations (see
``ACTIVITY_TRANSITIONS`` in ``readiness/net/topology.py``); the callables
below stand in for the host activity methods so the spike stays isolated.
"""

import pytest
from workflow_ast import (
    Activity,
    Sequence,
    WorkflowShapeError,
    activity,
    canonical,
    fingerprint,
    parallel,
    render,
    sequence,
    walk,
)


def review() -> None:
    """Run the PR readiness review agent."""


def actions_discovery() -> None:
    """Observe the current GitHub Actions state for the PR head."""


def conversation() -> None:
    """Classify unresolved PR conversation into intents."""


def dashboard_publish() -> None:
    """Publish the readiness dashboard comment."""


def baseline() -> Sequence:
    return sequence(
        activity(review),
        parallel(
            activity(actions_discovery),
            activity(conversation),
        ),
        activity(dashboard_publish),
    )


class TestConstruction:
    def test_callable_contributes_name_and_first_doc_line(self) -> None:
        leaf = activity(review)
        assert leaf.name == "review"
        assert leaf.doc == "Run the PR readiness review agent."

    def test_string_reference_is_enough(self) -> None:
        leaf = activity("actions_rerun")
        assert leaf == Activity(name="actions_rerun")

    def test_combinators_coerce_bare_callables_and_strings(self) -> None:
        tree = sequence(review, "repair")
        assert [s.name for s in tree.steps] == ["review", "repair"]  # type: ignore[union-attr]

    def test_origin_captures_authoring_site(self) -> None:
        leaf = activity(review)
        assert leaf.origin is not None
        assert leaf.origin.filename.endswith("test_workflow_ast.py")


class TestIdentity:
    def test_identical_construction_yields_equal_ast(self) -> None:
        # AX0 requirement: same source must produce the same compiler input.
        assert baseline() == baseline()

    def test_origin_is_metadata_not_identity(self) -> None:
        first = activity(review)
        second = activity(review)  # different line, same structure
        assert first.origin != second.origin
        assert first == second

    def test_nodes_are_immutable(self) -> None:
        leaf = activity(review)
        with pytest.raises(AttributeError):
            leaf.name = "other"  # type: ignore[misc]


class TestTraversal:
    def test_walk_yields_deterministic_structural_paths(self) -> None:
        paths = [(path, type(node).__name__) for path, node in walk(baseline())]
        assert paths == [
            ((), "Sequence"),
            ((0,), "Activity"),
            ((1,), "Parallel"),
            ((1, 0), "Activity"),
            ((1, 1), "Activity"),
            ((2,), "Activity"),
        ]

    def test_render_is_printable_and_addressed(self) -> None:
        text = render(baseline())
        assert text == (
            "sequence [/]\n"
            "  activity review [/0]  # Run the PR readiness review agent.\n"
            "  parallel [/1]\n"
            "    activity actions_discovery [/1/0]"
            "  # Observe the current GitHub Actions state for the PR head.\n"
            "    activity conversation [/1/1]"
            "  # Classify unresolved PR conversation into intents.\n"
            "  activity dashboard_publish [/2]"
            "  # Publish the readiness dashboard comment."
        )


class TestCanonicalForm:
    def test_canonical_excludes_origin_and_carries_no_code(self) -> None:
        form = canonical(activity(review))
        assert form == {
            "kind": "activity",
            "name": "review",
            "doc": "Run the PR readiness review agent.",
        }

    def test_fingerprint_is_stable_across_builds(self) -> None:
        assert fingerprint(baseline()) == fingerprint(baseline())

    def test_fingerprint_distinguishes_topology(self) -> None:
        sequential = sequence(actions_discovery, conversation)
        concurrent = parallel(actions_discovery, conversation)
        assert fingerprint(sequential) != fingerprint(concurrent)


class TestShapeErrors:
    def test_empty_sequence_is_rejected_with_reason(self) -> None:
        with pytest.raises(WorkflowShapeError, match="at least one step"):
            sequence()

    def test_single_branch_parallel_is_rejected_with_reason(self) -> None:
        with pytest.raises(WorkflowShapeError, match="at least two branches, got 1"):
            parallel(review)
