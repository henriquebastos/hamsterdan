"""Variant-routing activity gates for the V5 actor-loop topology.

Every world touch in V5 is a gate: a motus activity that classifies its
own outcome into typed terminals (e.g. ``RerunLanded | RerunMoved |
RerunFault``). The engine routes tokens by color and silently drops
tokens no arc admits, so gates split the responsibility honestly:

- ``VariantPayloadConverter`` makes the concrete variant durable — the
  worker boundary stamps ``$variant`` into the JSON-faithful result,
  refusing subclasses and unlisted types loudly;
- ``VariantRoutingActivityHandler.project`` reads the durable
  discriminator and targets exactly the matching variant place,
  raising loudly on anything unexpected.

Lifted first-class from the ES-003 AX5 spike, unchanged in semantics.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field, replace
from types import MappingProxyType, UnionType
from typing import Any, cast, get_args

from petrus.impetus.binding import ActivityHandler, Binding, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet
from petrus.impetus.petrinet import NetPath, Token
from petrus.impetus.petrinet.schema import Net, NetUri
from petrus.motus.activity import (
    ActivityDefinition,
    ActivityFailure,
    ActivityInvocation,
    DataclassPayloadConverter,
    ExecutionPolicy,
    JsonPayloadConverter,
)

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    AnnounceReq,
    DashBlocked,
    DashReq,
    MutWork,
    Publishable,
    RemReq,
    ReplyBlocked,
    ReplyReq,
    RerunReq,
    RoundOpen,
    WorkflowModel,
)

_JSON = JsonPayloadConverter()
_DURABLE_PUBLICATION_GATES = frozenset({"reply_gate", "dash_gate", "announce_gate"})
_DURABLE_PUBLICATION_POLICY = ExecutionPolicy(attempts=1)
_IDENTIFIED_INLINE_GATES = frozenset({"review_agent", "publish_gate", "rerun_gate", "git_gate", "reminder_gate"})
_IDENTIFIED_INLINE_POLICY = ExecutionPolicy(attempts=1)
_MARKER_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_GRAPHIC_OPERATION = re.compile(r"[!-~]{1,1024}\Z")

# transition path -> (activity name, declared variant colors)
GateSpec = tuple[str, tuple[str, ...]]


@dataclass(frozen=True)
class VariantPayloadConverter:
    """Make the concrete union variant durable at the worker boundary.

    ``encode`` on a union annotation requires the value to be *exactly*
    one of the declared members (a subclass is refused — its name would
    route nowhere) and stamps ``$variant`` into the JSON-faithful
    payload. Everything else delegates to the ordinary dataclass
    converter.
    """

    fallback: DataclassPayloadConverter = field(default_factory=DataclassPayloadConverter)

    def decode(self, value: object, annotation: object) -> object:
        return self.fallback.decode(value, annotation)

    def encode(self, value: object, annotation: object) -> object:
        if isinstance(annotation, UnionType):
            members = {member.__name__: member for member in get_args(annotation)}
            concrete = type(value)
            if members.get(concrete.__name__) is not concrete:
                raise ValueError(
                    f"union activity result must be exactly one of "
                    f"{sorted(members)}, got {concrete.__name__} — subclasses "
                    f"and unlisted types have no routing arc"
                )
            payload = asdict(cast(Any, value))  # membership proved it is a dataclass
            return _JSON.encode({"$variant": concrete.__name__, **payload}, annotation)
        return self.fallback.encode(value, annotation)


@dataclass(frozen=True)
class VariantRoutingActivityHandler:
    """Prepare like the derived handler; project by the durable ``$variant``.

    Single-parameter activities only. Construction validates the
    topology carries exactly one typed output arc per declared variant.
    """

    net: Net = field(repr=False)
    transition: NetPath
    definition: ActivityDefinition
    variants: tuple[str, ...]
    _parameter: str = field(init=False, repr=False)
    _source: NetPath = field(init=False, repr=False)
    _targets: Mapping[str, NetPath] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        transition = NetPath(self.transition)
        [(parameter, annotation)] = list(self.definition.parameters.items())
        color = cast(type, annotation).__name__
        inputs = [arc for arc in self.net.inputs(transition) if arc.color == color]
        if len(inputs) != 1:
            raise ValueError(
                f"variant routing for {transition}: parameter {parameter!r} "
                f"({color}) requires exactly one input arc, found {len(inputs)}"
            )
        targets: dict[str, NetPath] = {}
        for arc in self.net.outputs(transition):
            if arc.color not in self.variants:
                raise ValueError(
                    f"variant routing for {transition}: output arc to "
                    f"{arc.target} carries {arc.color!r}, not a declared "
                    f"variant of {list(self.variants)}"
                )
            if arc.color in targets:
                raise ValueError(f"variant routing for {transition}: variant {arc.color!r} has two output arcs")
            targets[arc.color] = arc.target
        missing = [v for v in self.variants if v not in targets]
        if missing:
            raise ValueError(f"variant routing for {transition}: no output arc for {missing}")
        object.__setattr__(self, "transition", transition)
        object.__setattr__(self, "_parameter", parameter)
        object.__setattr__(self, "_source", inputs[0].source)
        object.__setattr__(self, "_targets", MappingProxyType(targets))

    def prepare(self, binding: Binding) -> ActivityInvocation:
        [(place, tokens)] = list(binding.consumed)
        if place != self._source or len(tokens) != 1:
            raise ValueError(
                f"variant routing for {self.transition}: expected one token "
                f"from {self._source}, got {len(tokens)} from {place}"
            )
        return ActivityInvocation(self.definition.declaration.name, input={self._parameter: tokens[0].data})

    def _decode_request(self, invocation: ActivityInvocation, label: str) -> WorkflowModel:
        payload = cast(Mapping[str, object], invocation.input)
        annotation = self.definition.parameters[self._parameter]
        request = self.definition.converter.decode(payload[self._parameter], annotation)
        if not isinstance(request, WorkflowModel):
            raise TypeError(f"{label} decoded {type(request).__name__}, not a WorkflowModel")
        return request

    def project(self, binding: Binding, result: object) -> Mapping[NetPath, SequenceABC[Token]]:
        del binding
        if not isinstance(result, Mapping) or "$variant" not in result:
            raise ValueError(
                f"variant routing for {self.transition}: durable result lacks "
                f"the '$variant' discriminator — was the activity declared "
                f"with VariantPayloadConverter?"
            )
        payload = dict(result)
        variant = payload.pop("$variant")
        target = self._targets.get(variant)
        if target is None:
            raise ValueError(
                f"variant routing for {self.transition}: result variant "
                f"{variant!r} is not one of {list(self._targets)} — refusing "
                f"the runtime's silent drop"
            )
        return {target: (Token(variant, payload),)}


@dataclass(frozen=True)
class DurablePublicationActivityHandler(VariantRoutingActivityHandler):
    """Pin provider identity and project only known durable claim expiry."""

    def prepare(self, binding: Binding) -> ActivityInvocation:
        invocation = super().prepare(binding)
        request = self._decode_request(invocation, "Durable publication gate")
        if isinstance(request, ReplyReq):
            operation = f"reply:{request.id}"
        elif isinstance(request, DashReq):
            operation = f"dash:{request.digest}"
        elif isinstance(request, AnnounceReq):
            operation = request.op
        else:
            raise TypeError(f"Durable publication gate received unsupported request {type(request).__name__}")
        return replace(
            invocation,
            policy=_DURABLE_PUBLICATION_POLICY,
            correlation=operation,
            idempotency=operation,
        )

    def project_failure(self, binding: Binding, failure: ActivityFailure):
        if failure.kind != "DeadlineExceeded":
            raise RuntimeError(
                f"{failure.kind} failure for durable V5 publication {self.definition.declaration.name!r} "
                "cannot be projected"
            )
        invocation = super().prepare(binding)
        request = self._decode_request(invocation, "Durable publication gate")
        if isinstance(request, ReplyReq):
            blocked: WorkflowModel = ReplyBlocked(id=request.id, text=request.text)
        elif isinstance(request, DashReq):
            blocked = DashBlocked(
                entries=list(request.entries),
                digest=request.digest,
                desired_entries=list(request.desired_entries),
                desired_digest=request.desired_digest,
            )
        elif isinstance(request, AnnounceReq):
            blocked = ABlocked(
                incarnation=request.incarnation,
                head=request.head,
                base=request.base,
                policy=request.policy,
            )
        else:
            raise TypeError(f"Durable publication gate received unsupported request {type(request).__name__}")
        result = self.definition.converter.encode(blocked, self.definition.result)
        return self.project(binding, result)


@dataclass(frozen=True)
class IdentifiedInlineActivityHandler(VariantRoutingActivityHandler):
    """Freeze the provider operation used to reconcile inline redispatch."""

    def prepare(self, binding: Binding) -> ActivityInvocation:
        invocation = super().prepare(binding)
        request = self._decode_request(invocation, "Identified inline gate")
        name = self.definition.declaration.name
        if name == "review_agent" and isinstance(request, RoundOpen):
            operation = request.operation
        elif name == "publish_gate" and isinstance(request, Publishable):
            if request.effect != request.op:
                raise ValueError("V5 findings publication effect differs from its operation identity")
            operation = request.op
        elif name == "rerun_gate" and isinstance(request, RerunReq):
            operation = request.op
        elif name == "reminder_gate" and isinstance(request, RemReq):
            if _MARKER_OPERATION.fullmatch(request.timer_id) is None:
                raise ValueError("V5 identified inline gate 'reminder_gate' operation identity is malformed")
            operation = f"reminder:{request.timer_id}"
        elif name == "git_gate" and isinstance(request, MutWork):
            operation = request.op_key
        else:
            raise TypeError(f"Identified inline gate {name!r} received unsupported request {type(request).__name__}")
        grammar = _MARKER_OPERATION if name in {"publish_gate", "rerun_gate", "reminder_gate"} else _GRAPHIC_OPERATION
        if grammar.fullmatch(operation) is None:
            raise ValueError(f"V5 identified inline gate {name!r} operation identity is malformed")
        return replace(
            invocation,
            policy=_IDENTIFIED_INLINE_POLICY,
            correlation=operation,
            idempotency=operation,
        )


def wire_gates(
    built: BuiltNet,
    gates: Mapping[str, GateSpec],
    definitions: Mapping[str, ActivityDefinition],
    derived: Mapping[str, str] | None = None,
) -> dict[NetUri | str, Handler | ActivityHandler]:
    """Bind each gate transition to its activity handler.

    `gates` binds variant-routing gates (union results); `derived` binds
    single-output gates (one declared color, the stock derived handler).
    """
    handlers: dict = dict(built.handlers)
    for transition, (name, variants) in gates.items():
        uri = built.net.handler_uri(NetPath(transition))
        if name in _DURABLE_PUBLICATION_GATES:
            handler = DurablePublicationActivityHandler
        elif name in _IDENTIFIED_INLINE_GATES:
            handler = IdentifiedInlineActivityHandler
        else:
            handler = VariantRoutingActivityHandler
        handlers[uri] = handler(built.net, NetPath(transition), definitions[name], variants=variants)
    for transition, name in (derived or {}).items():
        uri = built.net.handler_uri(NetPath(transition))
        handlers[uri] = DerivedActivityHandler(built.net, NetPath(transition), definitions[name])
    return handlers
