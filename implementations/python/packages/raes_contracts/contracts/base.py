"""Base contract model, primitive type aliases, and RFC3339/digest helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from pydantic import Field

from raes_contracts._base import ContractModel, NonEmptyString, PrefixedDigestString
from raes_contracts.timestamps import parse_rfc3339_datetime

Sha256DigestString = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


Rfc3339DateTimeString = Annotated[
    str,
    Field(
        min_length=1,
        pattern=(
            r"^\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:(?:[0-5]\d|60)"
            r"(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
        ),
        json_schema_extra={"format": "date-time"},
    ),
]


CalendarDateString = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


HexDigestString = Annotated[str, Field(min_length=1, pattern=r"^[A-Fa-f0-9]+$")]


NonNegativeInteger = Annotated[int, Field(ge=0)]


PositiveInteger = Annotated[int, Field(ge=1)]


UnitIntervalFloat = Annotated[float, Field(gt=0, le=1)]


ClosedUnitIntervalFloat = Annotated[float, Field(ge=0, le=1)]


SemanticProfileId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+$")]


SemanticAssumptionId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


ReferenceModelId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]


JsonPointerString = Annotated[str, Field(pattern=r"^#(?:/[A-Za-z0-9_.$~-]+)+$")]


JsonInstancePathString = Annotated[str, Field(pattern=r"^#(?:/[A-Za-z0-9_.$~-]+)*$")]


InstancePath = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.(?:[a-z_][a-z0-9_]*|\*))*$")]


_CHECKSUM_VALUE_PATTERNS = {
    "sha256": r"^[A-Fa-f0-9]{64}$",
    "sha384": r"^[A-Fa-f0-9]{96}$",
    "sha512": r"^[A-Fa-f0-9]{128}$",
    "blake3": r"^[A-Fa-f0-9]{64}$",
}


_RAES_SEMANTIC_INVARIANT_PROFILE_URI = "https://openrae.github.io/rae/schemas/semantic-invariants/v1"


def casefold_digest(digest: str | None) -> str | None:
    """Return the case-insensitive comparison form of an optional digest string."""

    return digest.casefold() if digest is not None else None


def _payload_get(payload: object, field_name: str) -> object:
    if isinstance(payload, Mapping):
        return payload.get(field_name)
    return getattr(payload, field_name, None)


def _validate_rfc3339_payload_field(payload: object, field_name: str) -> None:
    value = _payload_get(payload, field_name)
    if value is not None:
        parse_rfc3339_datetime(field_name, value)


def _validate_artifact_collection_created_at(field_name: str, artifacts: object) -> None:
    for index, artifact in enumerate(artifacts or []):
        created_at = _payload_get(artifact, "created_at")
        if created_at is not None:
            parse_rfc3339_datetime(f"{field_name}/{index}/created_at", created_at)


__all__ = [
    "CalendarDateString",
    "ClosedUnitIntervalFloat",
    "ContractModel",
    "HexDigestString",
    "InstancePath",
    "JsonInstancePathString",
    "JsonPointerString",
    "NonEmptyString",
    "NonNegativeInteger",
    "PositiveInteger",
    "PrefixedDigestString",
    "ReferenceModelId",
    "Rfc3339DateTimeString",
    "SemanticAssumptionId",
    "SemanticProfileId",
    "Sha256DigestString",
    "UnitIntervalFloat",
    "casefold_digest",
]
