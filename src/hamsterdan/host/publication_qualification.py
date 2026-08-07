"""Closed, credential-free evidence for bounded Git publication qualification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from hamsterdan.agents import AgentCleanupCategory, AgentResultCategory
from hamsterdan.contracts.readiness import EffectResult

from .git_publish import GitPublishError, PublicationCategory


class QualificationCategory(StrEnum):
    """Non-publication failures that must remain distinct in retained evidence."""

    REPLAY_BOUNDARY = "replay_boundary"
    CLEANUP_UNVERIFIED = "cleanup_unverified"


@dataclass
class PublicationQualification:
    """First-cause-preserving state for one qualification publication."""

    original_publications: int | None = None
    agent_result_category: AgentResultCategory | None = None
    agent_cleanup_category: AgentCleanupCategory | None = None
    original_category: PublicationCategory | None = None
    schema_assertion: bool | None = None
    tree_assertion: bool | None = None
    replay_assertion: bool | None = None
    replay_category: PublicationCategory | QualificationCategory | None = None
    cleanup_verified: bool | None = None
    cleanup_category: QualificationCategory | None = None
    _assertions_started: bool = False

    def record_original(self, result: EffectResult, publications: int) -> None:
        if (
            self.original_publications is not None
            or type(result.ok) is not bool
            or type(publications) is not int
            or publications not in {0, 1}
        ):
            raise ValueError("original publication evidence is inconsistent")
        category = _category(result.publication_category, PublicationCategory, "original publication")
        result_category = _category(result.agent_result_category, AgentResultCategory, "agent result")
        cleanup_category = _category(result.agent_cleanup_category, AgentCleanupCategory, "agent cleanup")
        if category is not None and result_category is not None:
            raise ValueError("agent admission and publication causes cannot overlap")
        if result.ok and (
            publications != 1 or category is not None or result_category is not None or cleanup_category is not None
        ):
            raise ValueError("successful publication evidence is inconsistent")
        if not result.ok and (
            publications != 0 or category is None and result_category is None and cleanup_category is None
        ):
            raise ValueError("failed publication lacks a closed category")
        self.original_publications = publications
        self.agent_result_category, self.agent_cleanup_category = result_category, cleanup_category
        self.original_category = category

    @property
    def publication_assertions_allowed(self) -> bool:
        return self.original_publications == 1 and self.original_category is None

    def run_publication_assertions(
        self,
        *,
        schema: Callable[[], bool],
        tree: Callable[[], bool],
        replay: Callable[[], bool],
    ) -> None:
        if self._assertions_started:
            raise ValueError("publication assertions already started")
        self._assertions_started = True
        if not self.publication_assertions_allowed:
            return
        self.schema_assertion = _strict_assertion(schema())
        self.tree_assertion = _strict_assertion(tree())
        if not self.schema_assertion or not self.tree_assertion:
            return
        try:
            self.replay_assertion = _strict_assertion(replay())
        except GitPublishError as error:
            self.replay_assertion = False
            self.replay_category = error.category
        except RuntimeError:
            self.replay_assertion = False
            self.replay_category = QualificationCategory.REPLAY_BOUNDARY

    def record_cleanup(self, verified: bool) -> None:
        if type(verified) is not bool or self.cleanup_verified is not None:
            raise ValueError("cleanup evidence is inconsistent")
        self.cleanup_verified = verified
        if not verified:
            self.cleanup_category = QualificationCategory.CLEANUP_UNVERIFIED

    @property
    def accepted(self) -> bool:
        return (
            self.publication_assertions_allowed
            and self.schema_assertion is True
            and self.tree_assertion is True
            and self.replay_assertion is True
            and self.replay_category is None
            and self.cleanup_verified is True
            and self.cleanup_category is None
        )

    def sanitized(self) -> dict[str, object]:
        """Return a fixed-shape record containing no caller-controlled text."""

        return {
            "accepted": self.accepted,
            "original_publications": self.original_publications,
            "agent_result_category": ("" if self.agent_result_category is None else self.agent_result_category.value),
            "agent_cleanup_category": (
                "" if self.agent_cleanup_category is None else self.agent_cleanup_category.value
            ),
            "original_category": "" if self.original_category is None else self.original_category.value,
            "publication_assertions_allowed": self.publication_assertions_allowed,
            "schema_assertion": self.schema_assertion,
            "tree_assertion": self.tree_assertion,
            "replay_assertion": self.replay_assertion,
            "replay_category": "" if self.replay_category is None else self.replay_category.value,
            "cleanup_verified": self.cleanup_verified,
            "cleanup_category": "" if self.cleanup_category is None else self.cleanup_category.value,
        }


def _strict_assertion(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("qualification assertion must be boolean")
    return value


def _category[Category: StrEnum](value: object, vocabulary: type[Category], name: str) -> Category | None:
    if not isinstance(value, str):
        raise TypeError(f"{name} category is outside the closed vocabulary")
    if value == "":
        return None
    try:
        return vocabulary(value)
    except ValueError:
        raise ValueError(f"{name} category is outside the closed vocabulary") from None
