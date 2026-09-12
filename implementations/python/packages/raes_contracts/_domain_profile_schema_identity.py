"""Offline schema identity checks shared by the pinned profile models."""

from pydantic import JsonValue as PydanticJsonValue

from .uri_safety import validate_safe_absolute_uri


def _validate_inert_uri(value: str, *, field_name: str) -> str:
    validate_safe_absolute_uri(
        value,
        field_name=field_name,
        forbidden_schemes={"data", "file"},
        forbid_fragment=True,
    )
    return value


def _validate_schema_vocabularies(
    schema_document: dict[str, PydanticJsonValue],
    required_vocabularies: tuple[str, ...],
) -> None:
    if required_vocabularies != tuple(sorted(set(required_vocabularies))):
        raise ValueError("domain profile required vocabularies must be sorted and unique")
    for vocabulary in required_vocabularies:
        _validate_inert_uri(vocabulary, field_name="domain profile required schema vocabulary")
    declared = schema_document.get("$vocabulary", {})
    if not isinstance(declared, dict) or any(
        not isinstance(uri, str) or not isinstance(required, bool) for uri, required in declared.items()
    ):
        raise ValueError("domain profile schema $vocabulary must map URI strings to booleans")
    declared_required = tuple(sorted(uri for uri, required in declared.items() if required))
    if declared_required != required_vocabularies:
        raise ValueError("domain profile required vocabularies must match required $vocabulary entries")
