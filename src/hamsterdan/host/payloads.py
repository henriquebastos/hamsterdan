"""Host-owned Petrus conversion for strict workflow models."""

from collections.abc import Mapping

from petrus.motus.activity import JsonPayloadConverter, PayloadConverter
from pydantic import TypeAdapter


class PydanticPayloadConverter:
    """Round-trip strict Pydantic dataclass Activities through canonical JSON values."""

    def __init__(self, fallback: PayloadConverter | None = None) -> None:
        self._fallback = fallback or JsonPayloadConverter()

    def decode(self, value: object, annotation: object) -> object:
        if isinstance(annotation, type) and hasattr(annotation, "__pydantic_validator__"):
            if not isinstance(value, Mapping):
                raise TypeError(f"Activity payload for {annotation.__name__} must be a mapping")
            return annotation(**dict(value))
        return self._fallback.decode(value, annotation)

    def encode(self, value: object, annotation: object) -> object:
        if isinstance(annotation, type) and hasattr(annotation, "__pydantic_validator__"):
            if not isinstance(value, annotation):
                raise TypeError(f"Activity result must be {annotation.__name__}")
            return TypeAdapter(annotation).dump_python(value, mode="json")
        return self._fallback.encode(value, annotation)
