"""Atomic, local-only evidence output schema and semantic ownership registry."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from functools import cache
from types import MappingProxyType
from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import TypeAdapter
from referencing.exceptions import Unresolvable

from ._domain_profile_schema_registry import profile_schema_registry
from .corpus import SCHEMAS, corpus_family_root
from .json_ingress import parse_bounded_json_object


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
            schema = parse_bounded_json_object(source.read(1024 * 1024 + 1), max_bytes=1024 * 1024)
        if schema.get("type") != registration.root:
            raise ValueError("unexpected schema root")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, registry=profile_schema_registry(schema))
    except (OSError, RuntimeError, ValueError, KeyError, SchemaError) as exc:
        raise ValueError("evidence output_contract has no valid published schema") from exc
    return EvidenceOutputContract(registration.root, validator, registration.semantic_validator)


def validate_evidence_output_contract(output_contract: str, document: object) -> None:
    """Validate with the complete registered owner, never a semantic-only lookup."""

    resolve_evidence_output_contract(output_contract).validate(document)


def validate_evidence_output_offer(output_contract: str, media_types: Collection[str]) -> None:
    """Require the offered encodings to be supported by the same content owner."""

    contract = resolve_evidence_output_contract(output_contract)
    if not set(media_types).issubset(contract.media_types):
        raise ValueError("capture offer media types cannot be validated against its output_contract")


__all__ = [
    "EvidenceOutputContract",
    "evidence_output_registrations",
    "resolve_evidence_output_contract",
    "validate_evidence_output_contract",
    "validate_evidence_output_offer",
]
