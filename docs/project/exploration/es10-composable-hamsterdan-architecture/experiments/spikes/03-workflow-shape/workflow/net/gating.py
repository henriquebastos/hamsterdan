"""Variant-routing gate machinery, manifest-driven (spike).

Provenance: `VariantPayloadConverter` and `VariantRoutingActivityHandler`
transcribed (trimmed) from src/hamsterdan/readiness/net_v5/gating.py at
0686067. The redesign: one `DeclaredGateHandler` parameterized by a
`GateDeclaration` replaces the per-request `isinstance` chains of
`DurablePublicationActivityHandler` and `IdentifiedInlineActivityHandler`.
`project_failure` (the durable-publication blocked synthesis) is transcribed
design and is NOT exercised by the spike run proof.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field, replace
from types import MappingProxyType, UnionType
from typing import Any, cast, get_args

from petrus.impetus.binding import ActivityHandler, Binding, Handler
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

from workflow.activities import GateDeclaration
from workflow.values import WorkflowModel

_JSON = JsonPayloadConverter()
_SINGLE_ATTEMPT = ExecutionPolicy(attempts=1)
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


@dataclass(frozen=True)
class VariantPayloadConverter:
    """Make the concrete union variant durable at the worker boundary."""

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
            payload = asdict(cast(Any, value))
            return _JSON.encode({"$variant": concrete.__name__, **payload}, annotation)
        return self.fallback.encode(value, annotation)


@dataclass(frozen=True)
class VariantRoutingActivityHandler:
    """Prepare like the derived handler; project by the durable ``$variant``."""

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

    def _decode_request(self, invocation: ActivityInvocation) -> WorkflowModel:
        payload = cast(Mapping[str, object], invocation.input)
        annotation = self.definition.parameters[self._parameter]
        request = self.definition.converter.decode(payload[self._parameter], annotation)
        if not isinstance(request, WorkflowModel):
            raise TypeError(f"gate decoded {type(request).__name__}, not a WorkflowModel")
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
class DeclaredGateHandler(VariantRoutingActivityHandler):
    """One handler for every gate, parameterized by its manifest declaration."""

    gate: GateDeclaration = field(kw_only=True)

    def prepare(self, binding: Binding) -> ActivityInvocation:
        invocation = super().prepare(binding)
        request = self._decode_request(invocation)
        if not isinstance(request, self.gate.request):
            raise TypeError(
                f"gate {self.gate.activity!r} received {type(request).__name__}, expected {self.gate.request.__name__}"
            )
        operation = self.gate.operation(request)
        if _OPERATION.fullmatch(operation) is None:
            raise ValueError(f"gate {self.gate.activity!r} operation identity is malformed")
        return replace(invocation, policy=_SINGLE_ATTEMPT, correlation=operation, idempotency=operation)

    def project_failure(self, binding: Binding, failure: ActivityFailure):
        if self.gate.blocked is None or failure.kind != "DeadlineExceeded":
            raise RuntimeError(
                f"{failure.kind} failure for gate {self.definition.declaration.name!r} cannot be projected"
            )
        invocation = super().prepare(binding)
        request = self._decode_request(invocation)
        result = self.definition.converter.encode(self.gate.blocked(request), self.definition.result)
        return self.project(binding, result)


def wire_gates(
    built: BuiltNet,
    gates: Mapping[str, str],
    definitions: Mapping[str, ActivityDefinition],
    manifest: Mapping[str, GateDeclaration],
) -> dict[NetUri | str, Handler | ActivityHandler]:
    """Bind each gate transition to a manifest-declared handler.

    `gates` maps transition path -> activity name; the manifest supplies the
    variants, lane, identity, and blocked synthesis — one source of truth
    instead of per-loop variant tuples that must match activity signatures.
    """
    handlers: dict = dict(built.handlers)
    for transition, name in gates.items():
        declaration = manifest[name]
        uri = built.net.handler_uri(NetPath(transition))
        handlers[uri] = DeclaredGateHandler(
            built.net,
            NetPath(transition),
            definitions[name],
            variants=declaration.variants,
            gate=declaration,
        )
    return handlers
