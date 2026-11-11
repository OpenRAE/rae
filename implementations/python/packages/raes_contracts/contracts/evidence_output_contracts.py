"""Evidence output contracts: each published output schema bound to its owning model.

``raes_contracts.evidence_output_validation`` lists the published output
schemas. This module binds each entry to the semantic validator of its owning
model. Evidence eligibility requires both parts, so an offer or emitted content
never degrades to a schema-only check (issue #1237).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from functools import cache
from types import MappingProxyType
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import TypeAdapter
from referencing.exceptions import Unresolvable

from ..evidence_output_validation import EvidenceOutputSchema, evidence_output_schemas, published_schema_validator
from .experiment_evidence import ExperimentEvidenceRecordModel
from .participant_runtime import ParticipantBehaviorHistoryEventModel


@dataclass(frozen=True)
class EvidenceOutputRegistration:
    """One governed entry; eligibility requires every component to resolve."""

    schema: EvidenceOutputSchema
    semantic_validator: Callable[[object], object]


@dataclass(frozen=True)
class EvidenceOutputContract:
    """An output owner resolved together with its exact published schema."""

    schema: EvidenceOutputSchema
    _schema_validator: Draft202012Validator = field(repr=False)
    _semantic_validator: Callable[[object], object] = field(repr=False)

    @property
    def root(self) -> Literal["object", "array"]:
        return self.schema.root

    @property
    def media_types(self) -> frozenset[str]:
        return self.schema.media_types

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
    """Bind each published output schema to the validator of its owning model."""

    validators: dict[str, Callable[[object], object]] = {
        "experiment-evidence-record-v1": TypeAdapter(ExperimentEvidenceRecordModel).validate_python,
        "participant-behavior-history-event-stream-v1": TypeAdapter(
            list[ParticipantBehaviorHistoryEventModel]
        ).validate_python,
    }
    schemas = evidence_output_schemas()
    if set(validators) != set(schemas):
        raise ValueError("evidence output validators must cover exactly the published output schemas")
    return MappingProxyType(
        {
            contract_id: EvidenceOutputRegistration(entry, validators[contract_id])
            for contract_id, entry in schemas.items()
        }
    )


def resolve_evidence_output_contract(output_contract: str) -> EvidenceOutputContract:
    """Resolve both parts atomically or refuse evidence eligibility."""

    registration = evidence_output_registrations().get(output_contract)
    if registration is None:
        raise ValueError("evidence output_contract is not present in the authoritative contract registry")
    if not callable(registration.semantic_validator):
        raise ValueError("evidence output_contract has no owning semantic validator")
    validator = published_schema_validator(registration.schema)
    return EvidenceOutputContract(registration.schema, validator, registration.semantic_validator)


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
    "EvidenceOutputRegistration",
    "evidence_output_registrations",
    "resolve_evidence_output_contract",
    "validate_evidence_output_contract",
    "validate_evidence_output_offer",
]
