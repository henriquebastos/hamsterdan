"""Closed, credential-free evidence for bounded Git publication qualification."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from hamsterdan.agents import AgentCleanupCategory, AgentResultCategory
from hamsterdan.contracts.readiness import ChangeResult, RepairResult

from .git_publish import GitPublishError, PublicationCategory

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_GITHUB_REMOTE = re.compile(
    r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100})\.git\Z",
    re.ASCII,
)
_SETUP_MARKER = b"atomic-two-ref-v1\n"
_MAIN_REF = "refs/heads/main"
_QUALIFICATION_REF = "refs/heads/hamsterdan/ds11-live-v4"


class QualificationCategory(StrEnum):
    """Non-publication failures that must remain distinct in retained evidence."""

    REPLAY_BOUNDARY = "replay_boundary"
    CLEANUP_UNVERIFIED = "cleanup_unverified"


class SetupCategory(StrEnum):
    """Closed outcomes for private qualification setup observations and effects."""

    ALREADY_SPENT = "already_spent"
    FENCE_UNAVAILABLE = "fence_unavailable"
    BOUNDARY_UNAVAILABLE = "boundary_unavailable"
    OBSERVATION_UNCONFIRMED = "observation_unconfirmed"
    PUSH_UNCONFIRMED = "push_unconfirmed"


@dataclass(frozen=True)
class SetupPushResult:
    """Coordinate-free evidence for one admitted atomic push command."""

    attempted: bool
    command_succeeded: bool
    category: SetupCategory | None = None

    def sanitized(self) -> dict[str, object]:
        return {
            "attempted": self.attempted,
            "command_succeeded": self.command_succeeded,
            "category": "" if self.category is None else self.category.value,
        }


@dataclass(frozen=True)
class SetupObservationResult:
    """Private-input-free evidence for a setup observation."""

    confirmed: bool
    category: SetupCategory | None = None

    def sanitized(self) -> dict[str, object]:
        return {
            "confirmed": self.confirmed,
            "category": "" if self.category is None else self.category.value,
        }


def observe_setup_boundary(observer: Callable[[], bool]) -> SetupObservationResult:
    """Run a private setup observation without allowing its exception to render."""

    try:
        confirmed = observer()
    except Exception:  # noqa: BLE001 - private observation exceptions must never cross the evidence boundary
        return SetupObservationResult(False, SetupCategory.BOUNDARY_UNAVAILABLE)
    if type(confirmed) is not bool:
        return SetupObservationResult(False, SetupCategory.BOUNDARY_UNAVAILABLE)
    if not confirmed:
        return SetupObservationResult(False, SetupCategory.OBSERVATION_UNCONFIRMED)
    return SetupObservationResult(True)


class AtomicSetupPush:
    """Durably admit one exact atomic two-ref push without retaining private inputs."""

    def __init__(self, spent_path: Path) -> None:
        self._spent_path = Path(spent_path)

    def push(
        self,
        remote: str,
        base: str,
        head: str,
        runner: Callable[[tuple[str, ...]], int],
    ) -> SetupPushResult:
        command = _setup_command(remote, base, head)
        try:
            fence = self._spend()
        except Exception:  # noqa: BLE001 - private fence exceptions must never cross the evidence boundary
            return SetupPushResult(False, False, SetupCategory.FENCE_UNAVAILABLE)
        if fence is not None:
            return SetupPushResult(False, False, fence)
        try:
            returncode = runner(command)
        except Exception:  # noqa: BLE001 - private command exceptions must never cross the evidence boundary
            return SetupPushResult(True, False, SetupCategory.BOUNDARY_UNAVAILABLE)
        if type(returncode) is not int:
            return SetupPushResult(True, False, SetupCategory.BOUNDARY_UNAVAILABLE)
        if returncode != 0:
            return SetupPushResult(True, False, SetupCategory.PUSH_UNCONFIRMED)
        return SetupPushResult(True, True)

    def _spend(self) -> SetupCategory | None:
        parent_descriptor: int | None = None
        try:
            parent = self._spent_path.parent
            name = self._spent_path.name
            if name in {"", ".", ".."}:
                return SetupCategory.FENCE_UNAVAILABLE
            parent_descriptor = os.open(
                parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            metadata = os.fstat(parent_descriptor)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_uid != os.geteuid()
            ):
                return SetupCategory.FENCE_UNAVAILABLE
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                return (
                    SetupCategory.ALREADY_SPENT
                    if _valid_setup_marker(parent_descriptor, name)
                    else SetupCategory.FENCE_UNAVAILABLE
                )
            try:
                os.fchmod(descriptor, 0o600)
                marker = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(marker.st_mode)
                    or stat.S_IMODE(marker.st_mode) != 0o600
                    or marker.st_uid != os.geteuid()
                ):
                    return SetupCategory.FENCE_UNAVAILABLE
                if os.write(descriptor, _SETUP_MARKER) != len(_SETUP_MARKER):
                    return SetupCategory.FENCE_UNAVAILABLE
                os.fsync(descriptor)
                entry = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
                if (
                    (entry.st_dev, entry.st_ino) != (marker.st_dev, marker.st_ino)
                    or not stat.S_ISREG(entry.st_mode)
                    or stat.S_IMODE(entry.st_mode) != 0o600
                    or entry.st_uid != os.geteuid()
                ):
                    return SetupCategory.FENCE_UNAVAILABLE
            finally:
                os.close(descriptor)
            os.fsync(parent_descriptor)
            current_parent = parent.lstat()
            current_marker = self._spent_path.lstat()
            if (
                (current_parent.st_dev, current_parent.st_ino) != (metadata.st_dev, metadata.st_ino)
                or stat.S_ISLNK(current_parent.st_mode)
                or (current_marker.st_dev, current_marker.st_ino) != (marker.st_dev, marker.st_ino)
                or stat.S_ISLNK(current_marker.st_mode)
            ):
                return SetupCategory.FENCE_UNAVAILABLE
        except OSError:
            return SetupCategory.FENCE_UNAVAILABLE
        finally:
            if parent_descriptor is not None:
                os.close(parent_descriptor)
        return None


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

    def record_original(self, result: ChangeResult | RepairResult, publications: int) -> None:
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


def _setup_command(remote: str, base: str, head: str) -> tuple[str, ...]:
    if type(remote) is not str or type(base) is not str or type(head) is not str:
        raise ValueError("atomic setup command is invalid")
    try:
        match = _GITHUB_REMOTE.fullmatch(remote)
        repository = "" if match is None else match.group(2)
        valid = (
            match is not None
            and ".." not in repository
            and not repository.startswith(".")
            and not repository.endswith(".")
            and _SHA.fullmatch(base) is not None
            and _SHA.fullmatch(head) is not None
            and base != head
        )
    except TypeError, ValueError:
        valid = False
    if not valid:
        raise ValueError("atomic setup command is invalid") from None
    return (
        "git",
        "push",
        "--atomic",
        remote,
        f"{base}:{_MAIN_REF}",
        f"{head}:{_QUALIFICATION_REF}",
    )


def _valid_setup_marker(parent_descriptor: int, name: str) -> bool:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
            or metadata.st_size != len(_SETUP_MARKER)
        ):
            return False
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_descriptor)
        try:
            current = os.fstat(descriptor)
            value = os.read(descriptor, len(_SETUP_MARKER) + 1)
        finally:
            os.close(descriptor)
    except OSError:
        return False
    return (
        (current.st_dev, current.st_ino) == (metadata.st_dev, metadata.st_ino)
        and stat.S_IMODE(current.st_mode) == 0o600
        and current.st_uid == os.geteuid()
        and value == _SETUP_MARKER
    )
