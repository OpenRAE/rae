"""Atomic, local-only registry of evidence output schemas and their encodings.

``evidence_output_schemas`` is the closed list of evidence output contracts and
their published schemas. ``raes_contracts.contracts.evidence_output_contracts``
binds each entry to the semantic validator of its owning model. Evidence
eligibility requires both parts; a declaration of required encodings needs only
the published schema.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from functools import cache, lru_cache
from types import MappingProxyType
from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ._domain_profile_schema_registry import profile_schema_registry
from .corpus import SCHEMAS, corpus_family_root
from .json_ingress import StrictJsonIngressError, parse_bounded_json_object

_MAX_SCHEMA_BYTES = 1024 * 1024
_UNREGISTERED = "evidence output_contract is not present in the authoritative contract registry"


@dataclass(frozen=True)
class EvidenceOutputSchema:
    """One governed entry: the published schema path and its JSON root."""

    schema_path: str
    root: Literal["object", "array"]

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/json", "application/jsonl"} if self.root == "array" else {"application/json"})


@cache
def evidence_output_schemas() -> Mapping[str, EvidenceOutputSchema]:
    """Closed eligibility list, distinct from the corpus publication ledger."""

    return MappingProxyType(
        {
            "experiment-evidence-record-v1": EvidenceOutputSchema(
                "experiment-core/experiment-evidence-record-v1.json", "object"
            ),
            "participant-behavior-history-event-stream-v1": EvidenceOutputSchema(
                "control-plane/participant-behavior-history-event-stream-v1.json", "array"
            ),
        }
    )


def published_schema_validator(entry: EvidenceOutputSchema) -> Draft202012Validator:
    """Return the checked validator of the exact published schema, or refuse it."""

    # Validators call this resolver, so a damaged published schema stays a ValueError (E3).
    try:
        path = corpus_family_root(SCHEMAS) / entry.schema_path
        with path.open("rb") as source:
            content = source.read(_MAX_SCHEMA_BYTES + 1)
        return _checked_schema_validator(content, entry.root)
    except (OSError, RuntimeError, StrictJsonIngressError, ValueError, KeyError, SchemaError) as exc:
        raise ValueError("evidence output_contract has no valid published schema") from exc


def resolve_evidence_output_schema(output_contract: str) -> EvidenceOutputSchema:
    """Return a registered entry whose published schema resolves, or refuse it."""

    entry = evidence_output_schemas().get(output_contract)
    if entry is None:
        raise ValueError(_UNREGISTERED)
    published_schema_validator(entry)
    return entry


@lru_cache(maxsize=16)
def _checked_schema_validator(content: bytes, root: str) -> Draft202012Validator:
    """Check one exact published schema once.

    The key is the complete file content, so a changed schema is checked again.
    The local registry binds only that document, and a refusal is never cached.
    """

    schema = parse_bounded_json_object(content, max_bytes=_MAX_SCHEMA_BYTES)
    if schema.get("type") != root:
        raise ValueError("unexpected schema root")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=profile_schema_registry(schema))


def validate_evidence_media_declaration(output_contract: str, media_types: Collection[str]) -> None:
    """Reject required encodings with no registered content-proof path."""

    declared = set(media_types)
    if not declared and not output_contract:
        return
    supported = set().union(
        *(resolve_evidence_output_schema(contract_id).media_types for contract_id in evidence_output_schemas())
    )
    unsupported = sorted(declared - supported)
    if unsupported:
        raise ValueError("unsupported required evidence media type(s): " + ", ".join(unsupported))
    if output_contract and not declared.issubset(resolve_evidence_output_schema(output_contract).media_types):
        raise ValueError("required evidence media types cannot be validated against its output_contract")


__all__ = [
    "EvidenceOutputSchema",
    "evidence_output_schemas",
    "published_schema_validator",
    "resolve_evidence_output_schema",
    "validate_evidence_media_declaration",
]
