"""Atomic, local-only evidence output schema and semantic ownership registry."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from functools import cache, lru_cache
from types import MappingProxyType
from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import TypeAdapter
from referencing.exceptions import Unresolvable

from ._domain_profile_schema_registry import profile_schema_registry
from .corpus import SCHEMAS, corpus_family_root
from .json_ingress import parse_bounded_json_object

_MAX_SCHEMA_BYTES = 1024 * 1024


@dataclass(frozen=True)
class EvidenceOutputRegistration:
    """One governed entry; eligibility requires every component to resolve."""

    schema_path: str
    root: Literal["object", "array"]
    semantic_validator: Callable[[object], object]


@dataclass(frozen=True)
class EvidenceOutputContract:
    """An output owner resolved together with its exact published schema."""

    root: Literal["object", "array"]
    _schema_validator: Draft202012Validator = field(repr=False)
    _semantic_validator: Callable[[object], object] = field(repr=False)

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/json", "application/jsonl"} if self.root == "array" else {"application/json"})

    def validate(self, document: object) -> None:
        """Require schema and owning semantics; schema references never fetch."""

        try:
            if next(self._schema_validator.iter_errors(document), None) is not None:
                raise ValueError("schema validation failed")
            self._semantic_validator(document)
        except (ValueError, Unresolvable) as exc:
            raise ValueError("emitted evidence does not satisfy the declared output_contract") from exc


@cache
def evidence_output_registrations() -> Mapping[str, EvidenceOutputRegistration]:
    """Closed eligibility list, distinct from the corpus publication ledger."""

    # Lazy model imports keep offer parsing independent of contract import order.
    from .contracts.experiment_evidence import ExperimentEvidenceRecordModel
    from .contracts.participant_runtime import ParticipantBehaviorHistoryEventModel

    return MappingProxyType(
        {
            "experiment-evidence-record-v1": EvidenceOutputRegistration(
                "experiment-core/experiment-evidence-record-v1.json",
                "object",
                TypeAdapter(ExperimentEvidenceRecordModel).validate_python,
            ),
            "participant-behavior-history-event-stream-v1": EvidenceOutputRegistration(
                "control-plane/participant-behavior-history-event-stream-v1.json",
                "array",
                TypeAdapter(list[ParticipantBehaviorHistoryEventModel]).validate_python,
            ),
        }
    )


def resolve_evidence_output_contract(output_contract: str) -> EvidenceOutputContract:
    """Resolve both parts atomically or refuse evidence eligibility."""

    registration = evidence_output_registrations().get(output_contract)
    if registration is None:
        raise ValueError("evidence output_contract is not present in the authoritative contract registry")
    if not callable(registration.semantic_validator):
        raise ValueError("evidence output_contract has no owning semantic validator")
    try:
        path = corpus_family_root(SCHEMAS) / registration.schema_path
        with path.open("rb") as source:
            content = source.read(_MAX_SCHEMA_BYTES + 1)
        validator = _checked_schema_validator(content, registration.root)
    except (OSError, RuntimeError, ValueError, KeyError, SchemaError) as exc:
        raise ValueError("evidence output_contract has no valid published schema") from exc
    return EvidenceOutputContract(registration.root, validator, registration.semantic_validator)


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


def validate_evidence_output_contract(output_contract: str, document: object) -> None:
    """Validate with the complete registered owner, never a semantic-only lookup."""

    resolve_evidence_output_contract(output_contract).validate(document)


def validate_evidence_output_offer(output_contract: str, media_types: Collection[str]) -> None:
    """Require the offered encodings to be supported by the same content owner."""

    contract = resolve_evidence_output_contract(output_contract)
    if not set(media_types).issubset(contract.media_types):
        raise ValueError("capture offer media types cannot be validated against its output_contract")


def validate_evidence_media_declaration(output_contract: str, media_types: Collection[str]) -> None:
    """Reject required encodings with no registered content-proof path."""

    declared = set(media_types)
    if not declared and not output_contract:
        return
    supported = set().union(
        *(resolve_evidence_output_contract(contract_id).media_types for contract_id in evidence_output_registrations())
    )
    unsupported = sorted(declared - supported)
    if unsupported:
        raise ValueError("unsupported required evidence media type(s): " + ", ".join(unsupported))
    if output_contract:
        contract = resolve_evidence_output_contract(output_contract)
        if not declared.issubset(contract.media_types):
            raise ValueError("required evidence media types cannot be validated against its output_contract")


__all__ = [
    "EvidenceOutputContract",
    "evidence_output_registrations",
    "resolve_evidence_output_contract",
    "validate_evidence_output_contract",
    "validate_evidence_output_offer",
    "validate_evidence_media_declaration",
]
