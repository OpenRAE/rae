"""Public RFC 8785/JCS canonical byte and digest helpers."""

from pydantic import BaseModel

from ._canonical import (
    UNSERIALIZABLE_CARRIER_PREFIX,
    JsonValue,
    canonical_json_bytes,
    canonical_json_digest,
    jsonable_fallback,
)


def canonical_contract_digest(model: BaseModel) -> str:
    """Return a JCS SHA-256 digest for one closed contract model."""

    return canonical_json_digest(model.model_dump(mode="json"))


__all__ = [
    "UNSERIALIZABLE_CARRIER_PREFIX",
    "JsonValue",
    "canonical_contract_digest",
    "canonical_json_bytes",
    "canonical_json_digest",
    "jsonable_fallback",
]
