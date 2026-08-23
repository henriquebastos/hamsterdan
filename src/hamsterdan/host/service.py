"""Process-owned composition, startup authority reconciliation, and inbox worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeHost
from petrus.motus.activity import Activity, ActivityDefinition, ActivityError

from hamsterdan.agents import AgentProtocolError, AgentRunner
from hamsterdan.contracts.readiness import AdmittedConversation
from hamsterdan.github_app.auth import GitHubAppClients
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import GitHubBoundaryError, Transport
from hamsterdan.github_app.routing import InstallationRegistry
from hamsterdan.github_app.transport import GitHubGraphQL, GitHubKitTransport
from hamsterdan.github_app.webhooks import Observation, WebhookCustody, admit_conversation
from hamsterdan.readiness.net_v5.gating import DURABLE_PUBLICATION_GATES

from .agenticus import AgentComposition, AgentRouteStore, RoutedAgentRunner
from .binding import preflight_v5_state, read_instance_binding
from .protocol import ReadinessApplication
from .runnable import RunnableIndex
from .v5.application import PrReadinessV5Application

LOG = logging.getLogger("hamsterdan.host")
_FAULT_BOUNDARIES = frozenset({"agent", "comment"})
_FAULT_PHASES = frozenset({"timed_out", "malformed", "before_call", "after_call"})
_INSTANCE_PATTERN = re.compile(r"github:([1-9][0-9]*):([1-9][0-9]*):pr:([1-9][0-9]*)\Z")


@dataclass(frozen=True)
class CustodyOneResult:
    """Detached outcome of one bounded custody attempt."""

    delivery_id: str
    disposition: Literal["completed", "disposed", "retained", "failed"]


@dataclass
class QualificationFault:
    """One exact, host-owned, disabled-by-default qualification failure."""

    repository: str
    pull_request: int
    boundary: str
    phase: str
    kind: str
    operation: str
    _spent: bool = field(default=False, init=False, repr=False)
    _spent_operation: str | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> QualificationFault | None:
        raw = (os.environ if environment is None else environment).get("HAMSTERDAN_QUALIFICATION_FAULT")
        if raw is None:
            return None
        if not 0 < len(raw.encode()) <= 4096:
            raise ValueError("qualification fault configuration is malformed")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("qualification fault configuration is malformed") from None
        names = {"repository", "pull_request", "boundary", "phase", "kind", "operation"}
        if not isinstance(value, dict) or set(value) != names:
            raise ValueError("qualification fault configuration is malformed")
        repository, boundary, phase, kind, operation = (
            value["repository"],
            value["boundary"],
            value["phase"],
            value["kind"],
            value["operation"],
        )
        pull_request = value["pull_request"]
        if (
            not isinstance(repository, str)
            or repository.count("/") != 1
            or type(pull_request) is not int
            or pull_request <= 0
            or boundary not in _FAULT_BOUNDARIES
            or phase not in _FAULT_PHASES
            or not isinstance(kind, str)
            or not kind
            or not isinstance(operation, str)
            or not operation
            or (boundary == "agent") != (phase in {"timed_out", "malformed"})
        ):
            raise ValueError("qualification fault configuration is malformed")
        return cls(repository, pull_request, boundary, phase, kind, operation)

    def _matches(
        self, repository: str, pull_request: int, boundary: str, phase: str, kind: str, operation: str
    ) -> bool:
        return (
            not self._spent
            and (repository.casefold(), pull_request, boundary, phase, kind)
            == (
                self.repository.casefold(),
                self.pull_request,
                self.boundary,
                self.phase,
                self.kind,
            )
            and self.operation in {operation, "next"}
        )

    def _consume(self, boundary: str, phase: str, kind: str, operation: str) -> None:
        self._spent = True
        self._spent_operation = operation
        LOG.warning(
            "qualification_fault boundary=%s phase=%s kind=%s operation=%s",
            boundary,
            phase,
            kind,
            operation,
            extra={"boundary": boundary, "phase": phase, "kind": kind, "operation": operation},
        )

    def publication(self, phase: str, repository: str, pull_request: int, kind: str, operation: str) -> None:
        with self._lock:
            if not self._matches(repository, pull_request, "comment", phase, kind, operation):
                return
            self._consume("comment", phase, kind, operation)
        raise GitHubBoundaryError("qualified provider outcome was deliberately withheld")

    def agent(self, repository: str, pull_request: int, kind: str, operation: str) -> None:
        with self._lock:
            if not self._matches(repository, pull_request, "agent", self.phase, kind, operation):
                return
            self._consume("agent", self.phase, kind, operation)
        if self.phase == "timed_out":
            raise AgentProtocolError("qualified agent execution timed out", timed_out=True)
        raise AgentProtocolError("qualified agent result is malformed")


class HostService:
    def __init__(
        self,
        config: HostConfig,
        *,
        clients: GitHubAppClients | None = None,
        runner: AgentRunner,
        agent_composition: AgentComposition,
        agent_routes: AgentRouteStore,
        agent_runtime: PiA2RuntimeHost | None = None,
        application_factory: Callable[..., ReadinessApplication] = PrReadinessV5Application,
        workflow_path: str = ".github/workflows/ci.yml",
        reminder_delay: float = 259200,
        poll_interval: float = 0.25,
        sweep_interval: float = 60,
        qualification_fault: QualificationFault | None = None,
        clock: Callable[[], float] | None = None,
        transport_factory: Callable[[Any], Transport] | None = None,
    ) -> None:
        self.config = config
        self.root = config.state_path
        self.application_factory = application_factory
        preflight_v5_state(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.clients = clients or GitHubAppClients(config, metadata_hook=self._request_metadata)
        self.registry = InstallationRegistry(
            self.root / "routes.sqlite3", account_id=config.account_id, allowed_repositories=config.allowed_repositories
        )
        _, secret = config._credentials()
        self._clock = time.time if clock is None else clock
        self._application_clock = clock
        self._transport_factory = GitHubKitTransport if transport_factory is None else transport_factory
        self.custody = WebhookCustody(
            self.root / "webhooks.sqlite3", webhook_secret=secret, registry=self.registry, clock=self._clock
        )
        self.runner = runner
        self.agent_composition, self.agent_routes, self.agent_runtime = agent_composition, agent_routes, agent_runtime
        self.workflow_path, self.reminder_delay, self.poll_interval = workflow_path, reminder_delay, poll_interval
        self.sweep_interval = sweep_interval
        self.qualification_fault = qualification_fault
        self.installation_id: int | None = None
        self._apps: dict[tuple[int, int, int], ReadinessApplication] = {}
        self._locks: dict[tuple[int, int, int], threading.Lock] = {}
        self._stop = asyncio.Event()
        self._closed = False
        self._instances: dict[str, tuple[int, int, int]] = {}
        self._application_lock = threading.RLock()
        self._pump_lock = threading.Lock()
        self._scheduler_errors: dict[str, str] = {}
        self.runnable = RunnableIndex(self.root / "runnable.sqlite3", clock=self._clock)
        self._dispatch_path = self.root / "activity-dispatch.sqlite3"

    def _resolve_activity(self, instance: str, name: str):
        if name not in DURABLE_PUBLICATION_GATES:
            return None
        match = _INSTANCE_PATTERN.fullmatch(instance)
        if match is None:
            return self._invalid_publication_scope
        installation_id, repository_id, pull_request_number = (int(value) for value in match.groups())
        key = installation_id, repository_id, pull_request_number
        try:
            application = self._application(*key, allow_inactive_binding=True)
            implementation = application.activity(name)
        except Exception:  # noqa: BLE001 -- recognized publications must fail closed through an implementation
            return self._invalid_publication_scope
        if implementation is None:
            return self._invalid_publication_scope
        return self._guard_durable_activity(instance, name, implementation, acquire_lock=True)

    def _guard_durable_activity(
        self,
        instance: str,
        name: str,
        implementation: ActivityDefinition,
        *,
        acquire_lock: bool = False,
    ) -> Activity | None:
        if name not in DURABLE_PUBLICATION_GATES:
            return None
        match = _INSTANCE_PATTERN.fullmatch(instance)
        if match is None:
            return self._invalid_publication_scope
        installation_id, repository_id, pull_request_number = (int(value) for value in match.groups())
        key = installation_id, repository_id, pull_request_number

        def wake(invocation, *, context):
            try:

                def invoke() -> object:
                    if self.registry.route(key[0], key[1]) is None:
                        return PrReadinessV5Application.inactive_activity_result(name, invocation, implementation)
                    return implementation(invocation, context=context)

                try:
                    if acquire_lock:
                        with self._locks[key]:
                            return invoke()
                    return invoke()
                except ActivityError:
                    raise
                except Exception as error:
                    raise ActivityError(
                        "publication invariant failed",
                        kind=type(error).__name__,
                        retryable=False,
                    ) from error
            finally:
                self.runnable.wake(instance, self._clock(), "activity-terminal", name)

        return wake

    @staticmethod
    def _invalid_publication_scope(invocation, *, context):
        raise ActivityError("publication scope is unavailable", kind="PublicationScopeError", retryable=False)

    def _request_metadata(self, metadata: Any) -> None:
        LOG.info(
            "github_response method=%s path=%s request_id=%s status=%s rate_limit_remaining=%s rate_limit_reset=%s",
            metadata.method,
            metadata.path,
            metadata.request_id,
            metadata.status,
            metadata.rate_limit_remaining,
            metadata.rate_limit_reset,
            extra={
                "github_method": metadata.method,
                "github_path": metadata.path,
                "github_request_id": metadata.request_id,
                "rate_limit_remaining": metadata.rate_limit_remaining,
                "rate_limit_reset": metadata.rate_limit_reset,
                "status": metadata.status,
            },
        )

    def reconcile_registration(self) -> dict[str, object]:
        inventory = self.clients.registration_inventory(self.config)
        count = self.registry.reconcile(inventory.installation_id, inventory.repositories)
        self.installation_id = inventory.installation_id
        return {
            "app_id": self.config.app_id,
            "app_slug": self.config.app_slug,
            "installation_id": inventory.installation_id,
            "admitted_repositories": count,
        }

    def _application(
        self,
        installation_id: int,
        repository_id: int,
        pull_request_number: int,
        *,
        allow_inactive_binding: bool = False,
    ) -> ReadinessApplication:
        key = installation_id, repository_id, pull_request_number
        with self._application_lock:
            if key in self._apps:
                return self._apps[key]
            route = self.registry.route(installation_id, repository_id)
            if route is None and not allow_inactive_binding:
                raise RuntimeError("route became inactive")
            instance = f"github:{installation_id}:{repository_id}:pr:{pull_request_number}"
            root = self.root / "applications" / str(installation_id) / str(repository_id) / str(pull_request_number)
            if route is None:
                try:
                    if root.is_symlink() or not root.is_dir():
                        raise ValueError
                    binding = read_instance_binding(root / "binding.json")
                except OSError, ValueError, RuntimeError:
                    raise RuntimeError("inactive route has no strict durable binding") from None
                if (
                    binding.topology != "v5"
                    or binding.legacy
                    or binding.instance_id != instance
                    or binding.pull_request != pull_request_number
                    or (root / "history.jsonl").is_symlink()
                    or not (root / "history.jsonl").is_file()
                ):
                    raise RuntimeError("inactive route has no strict durable binding")
                repository_full_name = binding.repository
            else:
                assert route is not None
                repository_full_name = route.repository_full_name
            operation_client = self.clients.installation(installation_id, [repository_id])
            transport = self._transport_factory(operation_client)
            authority = GitHubAuthority(
                transport,
                repository_full_name,
                pull_request_number,
                graphql=GitHubGraphQL(transport),
            )
            qualification_fault = self.qualification_fault
            routed_runner = RoutedAgentRunner(
                self.runner,
                self.agent_routes,
                self.agent_composition,
                before_call=(
                    None
                    if qualification_fault is None
                    else lambda kind, operation, attempt: qualification_fault.agent(
                        repository_full_name, pull_request_number, kind, operation
                    )
                ),
            )
            application = self.application_factory(
                root,
                f"github:{installation_id}:{repository_id}:pr:{pull_request_number}",
                authority,
                routed_runner,
                bot_login=self.config.bot_login,
                public_clone_url=f"https://github.com/{repository_full_name}.git",
                workflow_path=self.workflow_path,
                reminder_delay=self.reminder_delay,
                publication_fault=None if qualification_fault is None else qualification_fault.publication,
                agent_settle=self.agent_routes.settle,
                dispatch_path=self._dispatch_path,
                custody_path=self.root / "webhooks.sqlite3",
                durable_activity_resolver=self._guard_durable_activity,
                clock=self._application_clock,
            )
            self._locks[key] = threading.Lock()
            self._apps[key] = application
            self._instances[instance] = key
            return application

    def sweep(self, trigger: str = "periodic") -> int:
        """Reconcile durable PR Instances after restarts or missed provider events."""
        applications = self.root / "applications"
        if not applications.is_dir():
            return 0
        reconciled = 0
        for history in sorted(applications.glob("*/*/*/history.jsonl")):
            try:
                installation_id, repository_id, pull_request_number = (int(part) for part in history.parts[-4:-1])
            except ValueError:
                continue
            if min(installation_id, repository_id, pull_request_number) <= 0:
                continue
            try:
                instance = f"github:{installation_id}:{repository_id}:pr:{pull_request_number}"
                reconciled += self._activate_instance(instance, reconcile_trigger=trigger)
            except Exception as error:  # noqa: BLE001 -- one PR must not prevent repair of another
                LOG.warning(
                    "application_sweep_retry installation_id=%s repository_id=%s pull_request_number=%s error_class=%s",
                    installation_id,
                    repository_id,
                    pull_request_number,
                    type(error).__name__,
                    extra={
                        "installation_id": installation_id,
                        "repository_id": repository_id,
                        "pull_request_number": pull_request_number,
                        "error_class": type(error).__name__,
                    },
                )
        return reconciled

    def process(self, item: Observation) -> None:
        instance = self._instance(item)
        if instance is None:
            self._select_observation(item)
            return
        status = self.custody.status(item.delivery_id)
        if status not in (None, "pending"):
            return
        try:
            # A real custodied callback is only a wake hint: subject
            # loading owns strict row order and applies every due row.
            # Uncustodied direct observations remain a test/operator seam.
            self._activate_instance(instance, observation=item if status is None else None)
        except Exception:  # noqa: BLE001 -- activation already retains and classifies custody
            # Activation has already retained and classified the delivery;
            # direct callers do not own scheduler health.
            return

    def _select_observation(self, item: Observation) -> tuple[Observation, AdmittedConversation | None] | None:
        """Terminally dispose observations which cannot address a PR Instance."""
        if item.event in {"ping", "installation", "installation_repositories"}:
            self.custody.acknowledge(item.delivery_id, "non-workflow event")
            return None
        if (
            item.installation_id is None
            or item.repository_id is None
            or self.registry.route(item.installation_id, item.repository_id) is None
        ):
            self.custody.acknowledge(item.delivery_id, "inactive route")
            return None
        if item.pull_request_number is None:
            self.custody.acknowledge(item.delivery_id, "no pull request")
            return None
        if item.event == "issue_comment":
            conversation = admit_conversation(item, app_slug=self.config.app_slug, bot_login=self.config.bot_login)
            if conversation is None:
                self.custody.acknowledge(item.delivery_id, "comment not addressed")
                return None
            return item, conversation
        return item, None

    def _apply_observation(
        self,
        application: ReadinessApplication,
        item: Observation,
        conversation: AdmittedConversation | None,
    ) -> tuple[bool, str | None]:
        """Apply one eligible observation under its Instance lock, without custody effects."""
        assert item.installation_id is not None and item.repository_id is not None
        if self.registry.route(item.installation_id, item.repository_id) is None:
            return False, "route inactive before work"
        application.process_observation(item, conversation=conversation)
        return True, None

    @staticmethod
    def _observation_fields(item: Observation) -> dict[str, object]:
        return {
            "delivery_id": item.delivery_id,
            "event": item.event,
            "installation_id": item.installation_id,
            "repository_id": item.repository_id,
            "pull_request_number": item.pull_request_number,
        }

    def _acknowledge_observation(self, item: Observation, reason: str | None = None) -> None:
        self.custody.acknowledge(item.delivery_id, reason or "processed")
        LOG.info(
            "webhook_terminal delivery_id=%s event=%s installation_id=%s repository_id=%s "
            "pull_request_number=%s disposition=processed",
            item.delivery_id,
            item.event,
            item.installation_id,
            item.repository_id,
            item.pull_request_number,
            extra=self._observation_fields(item) | {"disposition": "processed"},
        )

    def _retry_observation(self, item: Observation, error: Exception) -> None:
        self.custody.retry(item.delivery_id, error)
        LOG.warning(
            "webhook_retry delivery_id=%s event=%s installation_id=%s repository_id=%s "
            "pull_request_number=%s disposition=retry error_class=%s",
            item.delivery_id,
            item.event,
            item.installation_id,
            item.repository_id,
            item.pull_request_number,
            type(error).__name__,
            extra=self._observation_fields(item) | {"disposition": "retry", "error_class": type(error).__name__},
        )

    async def worker(self) -> None:
        loop = asyncio.get_running_loop()
        await asyncio.to_thread(self.sweep, "startup")
        next_sweep = loop.time() + self.sweep_interval
        while not self._stop.is_set():
            await asyncio.to_thread(self.pump)
            if self._stop.is_set():
                break
            if loop.time() >= next_sweep:
                await asyncio.to_thread(self.sweep)
                next_sweep = loop.time() + self.sweep_interval
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    def pump(self, limit: int = 20) -> int:
        """Stage due authority custody before running durable Activities."""
        with self._pump_lock:
            # A pending draft/ready/head/close can move only the V5 host
            # grant while leaving head/base/policy unchanged. Apply all
            # due same-subject custody before an older queued publication
            # can claim execution under that stale incarnation.
            self.project_pending()
            self.run_due()
            if self._stop.is_set():
                return 0
            processed = 0
            for instance, key in tuple(self._instances.items()):
                if processed >= limit:
                    break
                application = self._apps[key]
                # V5 publications use per-instance queues. Never claim
                # one while that PR has unresolved inbox custody;
                # unrelated PR instances continue.
                if self.custody.has_pending(subject=key):
                    continue
                with self._locks[key]:
                    completed = application.run_durable_activities(limit - processed)
                    processed += completed
                    if completed:
                        self._record_posture(instance, application.settle())
            # Repair locally generated terminals which did not execute through
            # the resolver. The durable Dispatch/History remain authoritative.
            for instance, key in tuple(self._instances.items()):
                if self._apps[key].has_unresolved_publication():
                    self.runnable.wake(instance, self._clock(), "dispatch-repair", "unresolved-publication")
            return processed

    def process_one(self) -> CustodyOneResult | None:
        """Process at most one currently due custodied delivery."""
        pending = self.custody.pending(limit=1)
        if not pending:
            return None
        item = pending[0]
        if self._select_observation(item) is None:
            return CustodyOneResult(item.delivery_id, self._custody_disposition(item, completed=False))
        instance = self._instance(item)
        assert instance is not None
        try:
            completed = self._activate_instance(instance, observation=item)
        except Exception:  # noqa: BLE001 -- activation retained and classified the one delivery
            completed = False
        return CustodyOneResult(item.delivery_id, self._custody_disposition(item, completed=completed))

    def _custody_disposition(
        self,
        item: Observation,
        *,
        completed: bool,
    ) -> Literal["completed", "disposed", "retained", "failed"]:
        status = self.custody.status(item.delivery_id)
        if status == "terminal":
            return "completed" if completed else "disposed"
        if status == "failed":
            return "failed"
        return "retained"

    def run_one_activity(self) -> int:
        """Execute at most one immediately claimable durable Activity Attempt."""
        with self._pump_lock:
            if self._stop.is_set():
                return 0
            for instance, key in tuple(self._instances.items()):
                if self.custody.has_pending(subject=key):
                    continue
                application = self._apps[key]
                with self._locks[key]:
                    completed = application.run_durable_activities(1)
                    if completed:
                        self._record_posture(instance, application.settle())
                        return completed
            return 0

    def subject_state(self, installation: int, repository: int, pull_request: int) -> dict[str, object] | None:
        """Return detached application state for one loaded PR subject."""
        application = self._apps.get((installation, repository, pull_request))
        return None if application is None else application.detached_state()

    def work_state(self) -> dict[str, object]:
        """Disclose bounded eligible work without exposing runtime handles."""
        applications = self.root / "applications"
        persisted = tuple(applications.glob("*/*/*/history.jsonl")) if applications.is_dir() else ()
        loaded_roots = {
            self.root / "applications" / str(key[0]) / str(key[1]) / str(key[2]) / "history.jsonl" for key in self._apps
        }
        return {
            "pending_custody": bool(self.custody.pending(limit=1)),
            "runnable_due": self.runnable.next_due(),
            "unresolved_activity": any(application.has_unresolved_publication() for application in self._apps.values()),
            "unloaded_application": any(path not in loaded_roots for path in persisted),
        }

    def reconcile_one(self, trigger: str = "scheduled") -> bool:
        """Reconcile at most one persisted PR Instance."""
        applications = self.root / "applications"
        if not applications.is_dir():
            return False
        for history in sorted(applications.glob("*/*/*/history.jsonl")):
            try:
                installation, repository, pull_request = (int(part) for part in history.parts[-4:-1])
            except ValueError:
                continue
            if min(installation, repository, pull_request) <= 0:
                continue
            if (installation, repository, pull_request) in self._apps:
                continue
            instance = f"github:{installation}:{repository}:pr:{pull_request}"
            try:
                return self._activate_instance(instance, reconcile_trigger=trigger)
            except Exception as error:  # noqa: BLE001 -- preserve the production scheduler failure classification
                self._scheduler_errors[instance] = type(error).__name__
                return False
        return False

    @staticmethod
    def _instance(item: Observation) -> str | None:
        if item.installation_id is None or item.repository_id is None or item.pull_request_number is None:
            return None
        return f"github:{item.installation_id}:{item.repository_id}:pr:{item.pull_request_number}"

    def project_pending(self) -> int:
        """Project canonical due inbox observations into noncanonical wake hints."""
        projected = 0
        for item in self.custody.pending(limit=1000):
            instance = self._instance(item)
            if (
                instance is None
                or self.registry.route(cast(int, item.installation_id), cast(int, item.repository_id)) is None
            ):
                self.process(item)
                continue
            identity = item.delivery_id if item.event == "issue_comment" else "reconcile"
            self.runnable.wake(instance, self._clock(), "webhook", identity)
            projected += 1
        return projected

    def _record_posture(self, instance: str, outcome: object | None) -> None:
        self.runnable.replace_timer(instance, getattr(outcome, "next_maturation", None))

    def _activate_instance(
        self,
        instance: str,
        *,
        observation: Observation | None = None,
        reconcile_trigger: str | None = None,
    ) -> bool:
        match = _INSTANCE_PATTERN.fullmatch(instance)
        if match is None:
            return False
        installation_id, repository_id, pull_request_number = (int(value) for value in match.groups())
        key = installation_id, repository_id, pull_request_number
        if observation is not None and not self.custody.eligible(observation.delivery_id, subject=key):
            return False
        candidates = (observation,) if observation is not None else self.custody.pending(limit=1000, subject=key)
        selected = [selection for item in candidates if (selection := self._select_observation(item)) is not None]
        seen = {item.delivery_id for item in candidates}
        all_selected = list(selected)
        route_active = self.registry.route(key[0], key[1]) is not None
        bound = (self.root / "applications" / str(key[0]) / str(key[1]) / str(key[2]) / "history.jsonl").is_file()
        if candidates and not selected and key not in self._apps and not bound:
            return False
        if not route_active and key not in self._apps and not bound:
            return False
        succeeded: list[tuple[Observation, str | None]] = []
        handled: set[str] = set()
        attempted: set[str] = set()
        activation_error: Exception | None = None
        try:
            application = (
                self._apps[key]
                if key in self._apps
                else self._application(*key, allow_inactive_binding=not route_active)
            )
            with self._locks[key]:
                outcome = None
                activated = False
                if not selected:
                    # A topology owns observation ordering, but a bare
                    # activity/timer wake must first collect its frozen
                    # terminal before any optional provider reconciliation.
                    outcome = application.settle()
                batch = selected
                while batch:
                    for item, conversation in batch:
                        attempted.add(item.delivery_id)
                        try:
                            applied, reason = self._apply_observation(application, item, conversation)
                            activated = activated or applied
                            succeeded.append((item, reason))
                        except Exception as error:  # noqa: BLE001 -- isolate one delivery in a claimed Instance
                            self._retry_observation(item, error)
                            handled.add(item.delivery_id)
                            if activation_error is None:
                                activation_error = error
                            break
                    if activation_error is not None:
                        break
                    arrived = tuple(
                        item for item in self.custody.pending(limit=1000, subject=key) if item.delivery_id not in seen
                    )
                    if not arrived:
                        break
                    seen.update(item.delivery_id for item in arrived)
                    batch = [selection for item in arrived if (selection := self._select_observation(item)) is not None]
                    all_selected.extend(batch)
                if (
                    reconcile_trigger is not None
                    and not all_selected
                    and not self.custody.has_pending(subject=key)
                    and self.registry.route(key[0], key[1]) is not None
                ):
                    reconciled = application.reconcile(f"{reconcile_trigger}:{key[0]}:{key[1]}:{key[2]}")
                    activated = (
                        reconciled is not False
                        and not self.custody.has_pending(subject=key)
                        and self.registry.route(key[0], key[1]) is not None
                    )
                if activated:
                    outcome = application.settle()
                self._record_posture(instance, outcome)
                for item, reason in succeeded:
                    self._acknowledge_observation(item, reason)
                    handled.add(item.delivery_id)
                if activation_error is not None:
                    raise activation_error
        except Exception as error:
            retry = attempted or ({all_selected[0][0].delivery_id} if all_selected else set())
            for item, _conversation in all_selected:
                if item.delivery_id in retry and item.delivery_id not in handled:
                    self._retry_observation(item, error)
            raise
        return True

    def run_due(self, limit: int = 100) -> int:
        instances = self.runnable.take_due(limit)
        processed = 0
        for instance in instances:
            try:
                processed += self._activate_instance(instance)
                self._scheduler_errors.pop(instance, None)
            except Exception as error:  # noqa: BLE001 -- one damaged Instance must not consume later due wakes
                error_class = type(error).__name__
                self._scheduler_errors[instance] = error_class
                self.runnable.wake(instance, self._clock(), "scheduler-repair", "run-due-failure")
                LOG.warning(
                    "scheduler_instance_degraded instance=%s error_class=%s",
                    instance,
                    error_class,
                    extra={"instance": instance, "error_class": error_class},
                )
        return processed

    def stop(self) -> None:
        self._stop.set()
        with self._application_lock:
            applications = tuple(self._apps.values())
        for application in applications:
            application.stop_durable_activities()

    def health(self) -> dict[str, object]:
        return {
            "status": "degraded" if self._scheduler_errors else "ok",
            "installation_reconciled": self.installation_id is not None,
            "active_repositories": self.registry.active_count(),
            "applications": len(self._apps),
            "inbox": self.custody.counts(),
            "runnable_hints": self.runnable.count(),
            "scheduler": {
                "degraded_instances": len(self._scheduler_errors),
                "error_classes": sorted(set(self._scheduler_errors.values())),
            },
        }

    def settle_terminals_for_shutdown(self) -> None:
        """Boundedly collect terminals for loaded Instances without driving more Attempts."""
        for instance, key in tuple(self._instances.items()):
            application = self._apps.get(key)
            if application is None:
                continue
            try:
                with self._locks[key]:
                    self._record_posture(instance, application.settle())
            except Exception as error:  # noqa: BLE001 -- shutdown must continue closing all custody
                LOG.warning(
                    "shutdown_terminal_settlement_failed instance=%s error_class=%s",
                    instance,
                    type(error).__name__,
                    extra={"instance": instance, "error_class": type(error).__name__},
                )

    def abort(self) -> None:
        """Release this process generation without settling semantic work."""
        self._release(settle=False)

    def close(self) -> None:
        """Gracefully settle loaded terminals and release owned resources."""
        self._release(settle=True)

    def _release(self, *, settle: bool) -> None:
        if self._closed:
            return
        self._closed = True
        failure: Exception | None = None
        with self._pump_lock:
            if settle:
                try:
                    self.settle_terminals_for_shutdown()
                except Exception as error:  # noqa: BLE001 -- remaining resources still require closure
                    failure = error
        runtime = () if self.agent_runtime is None else (self.agent_runtime,)
        for resource in (
            *self._apps.values(),
            self.runnable,
            self.custody,
            self.registry,
            self.clients,
            *runtime,
            self.agent_routes,
        ):
            try:
                resource.close()
            except Exception as error:  # noqa: BLE001 -- every owned resource must still receive exactly one close
                if failure is None:
                    failure = error
        self._apps.clear()
        self._locks.clear()
        self._instances.clear()
        if failure is not None:
            raise failure
