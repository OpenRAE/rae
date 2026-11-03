"""Exact-cut observation records for adaptive-difficulty resolution."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import GetJsonSchemaHandler, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes_contracts.identifiers import PortableIdentifier

from .base import ContractModel, NonEmptyString, NonNegativeInteger
from .experiment_references import ExperimentReferenceModel

DifficultyThresholdValue = StrictStr | StrictInt | StrictFloat | StrictBool
_DIFFICULTY_EVIDENCE_KINDS = {"evidence", "evidence-record", "derived-measure", "result"}


def _validate_difficulty_source_reference(reference: ExperimentReferenceModel) -> None:
    if reference.ref_version is None or reference.ref_digest is None:
        raise ValueError("difficulty source definition references must be versioned and digest-bound")
    if reference.ref_path is not None:
        raise ValueError("difficulty source definition references must not depend on mutable paths")


def _validate_difficulty_evidence_reference(reference: ExperimentReferenceModel) -> None:
    if reference.ref_kind not in _DIFFICULTY_EVIDENCE_KINDS:
        raise ValueError("difficulty inputs require evidence-bearing references")
    if reference.ref_version is None and reference.ref_digest is None:
        raise ValueError("difficulty evidence references must be versioned or digest-bound")
    if reference.ref_path is not None:
        raise ValueError("difficulty evidence references must not depend on mutable paths")


class DifficultySourceDefinitionReferenceModel(ExperimentReferenceModel):
    """Immutable identity of the measurement or evidence role admitted by a policy."""

    @model_validator(mode="after")
    def _validate_source_definition(self) -> DifficultySourceDefinitionReferenceModel:
        _validate_difficulty_source_reference(self)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).append(
            {
                "required": ["ref_version", "ref_digest"],
                "properties": {
                    "ref_version": {"not": {"type": "null"}},
                    "ref_digest": {"not": {"type": "null"}},
                    "ref_path": {"type": "null"},
                },
            }
        )
        return json_schema


class DifficultyStateCutModel(ContractModel):
    """Exact ordered state cut used by one policy decision."""

    order_domain: Literal["logical-step", "decision-epoch", "event-sequence", "state-version"]
    coordinate: NonNegativeInteger
    episode_id: NonEmptyString


class DifficultyObservationReferenceModel(ContractModel):
    """Archived evidence role and cut, without the transient observed value."""

    source_id: PortableIdentifier
    source_ref: DifficultySourceDefinitionReferenceModel
    run_id: NonEmptyString
    evidence_ref: ExperimentReferenceModel
    observed_cut: DifficultyStateCutModel

    @model_validator(mode="after")
    def _validate_evidence_reference(self) -> DifficultyObservationReferenceModel:
        _validate_difficulty_evidence_reference(self.evidence_ref)
        return self


class DifficultyObservationInputModel(DifficultyObservationReferenceModel):
    """Transient typed resolver input; its value is not archived in decisions."""

    value: DifficultyThresholdValue

    @model_validator(mode="after")
    def _validate_value(self) -> DifficultyObservationInputModel:
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("difficulty observation values must be finite")
        return self


__all__ = [
    "DifficultyObservationInputModel",
    "DifficultyObservationReferenceModel",
    "DifficultySourceDefinitionReferenceModel",
    "DifficultyStateCutModel",
    "DifficultyThresholdValue",
]
