"""Correlated stage reports for one mixed-backend invocation, never terminal commits.

Each report proposes one fact for one shared backend operation invocation: a
time grant, bridge execution, destination delivery, participant observation,
native handoff or owner readback. Every stage names the pinned service that
produced it. Execution, delivery and observation are separate stages, so one
success flag cannot imply another; partial and unknown execution keep their own
status. A reader must validate reports against the installed binding, the
shared operation transcript and its own trusted readbacks; only RAES may commit
operation state, composition history and terminal outcomes.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..addressing import CompiledAddress
from ..versions import MIXED_BACKEND_STAGE_REPORT_SCHEMA_VERSION
from .backend_operation import (
    BackendOperationBindingModel,
    OperationContractModel,
    OperationCounter,
    OperationDigest,
    OperationIdentifier,
    OperationPositive,
)
from .mixed_backend_binding import GovernedOrderingBasis, MixedBackendServiceModel
from .time_model import TimeCoordinateModel

MIXED_BACKEND_STAGE_REPORT_CONTRACT_ID = "mixed-backend-stage-report-v1"

_Refs = Annotated[tuple[OperationIdentifier, ...], Field(default=(), max_length=64)]
_RequiredRefs = Annotated[tuple[OperationIdentifier, ...], Field(min_length=1, max_length=64)]


class MixedBackendTimeGrantStageModel(OperationContractModel):
    """Coordinator grant at the committed clock coordinates; incomparable grants permit no invocation."""

    stage: Literal["time-grant"]
    producer: MixedBackendServiceModel
    mapping_ref: CompiledAddress
    ordering_basis: GovernedOrderingBasis
    order_ref: OperationIdentifier
    comparison: Literal["ordered", "incomparable"]
    source_coordinate: TimeCoordinateModel
    destination_coordinate: TimeCoordinateModel
    mapping_evidence_refs: _RequiredRefs
    timing_evidence_refs: _RequiredRefs


class MixedBackendExecutionStageModel(OperationContractModel):
    """Bridge execution readback; it establishes no delivery or participant observation."""

    stage: Literal["execution"]
    producer: MixedBackendServiceModel
    source_action_address: CompiledAddress
    destination_action_address: CompiledAddress
    status: Literal["succeeded", "failed", "partial", "unknown"]
    evidence_refs: _Refs
    mapping_loss_refs: _Refs
    cessation_evidence_refs: _Refs

    @model_validator(mode="after")
    def _honest_status(self) -> Self:
        if self.status in {"succeeded", "partial"} and not self.evidence_refs:
            raise ValueError("known execution effects require readback evidence")
        if self.status == "failed" and not self.cessation_evidence_refs:
            raise ValueError("known execution failure requires cessation evidence")
        return self


class MixedBackendDeliveryStageModel(OperationContractModel):
    """Destination receipt read back by the pinned delivery reader, not the bridge."""

    stage: Literal["delivery"]
    producer: MixedBackendServiceModel
    destination_component_id: OperationIdentifier
    receipt_ref: OperationIdentifier
    evidence_refs: _RequiredRefs


class MixedBackendObservationStageModel(OperationContractModel):
    """Participant and audience readback after delivery; delivery alone is not observation."""

    stage: Literal["observation"]
    producer: MixedBackendServiceModel
    participant_address: CompiledAddress
    audience_scope_ref: OperationIdentifier
    observation_ref: OperationIdentifier
    evidence_refs: _RequiredRefs


class MixedBackendHandoffStageModel(OperationContractModel):
    """Native transfer disposition at the exact predecessor history head and phase revision."""

    stage: Literal["handoff"]
    producer: MixedBackendServiceModel
    status: Literal["committed", "failed", "pending", "stale", "unknown"]
    predecessor_history_head: OperationIdentifier
    phase_revision: OperationCounter
    order_ref: OperationIdentifier
    evidence_refs: _Refs


class MixedBackendOwnerReadbackStageModel(OperationContractModel):
    """Native responsibility owner read back by the pinned owner reader after a transfer attempt."""

    stage: Literal["owner-readback"]
    producer: MixedBackendServiceModel
    owner_component_id: OperationIdentifier
    owner_ref: OperationIdentifier
    phase_revision: OperationCounter
    evidence_refs: _RequiredRefs


MixedBackendStage = Annotated[
    MixedBackendTimeGrantStageModel
    | MixedBackendExecutionStageModel
    | MixedBackendDeliveryStageModel
    | MixedBackendObservationStageModel
    | MixedBackendHandoffStageModel
    | MixedBackendOwnerReadbackStageModel,
    Field(discriminator="stage"),
]


class MixedBackendStageReportModel(OperationContractModel):
    """One stage fact bound to the exact shared operation invocation and request commitment."""

    schema_version: Literal[MIXED_BACKEND_STAGE_REPORT_SCHEMA_VERSION] = MIXED_BACKEND_STAGE_REPORT_SCHEMA_VERSION
    binding: BackendOperationBindingModel
    request_digest: OperationDigest
    sequence: OperationPositive
    stage: MixedBackendStage


__all__ = [
    "MIXED_BACKEND_STAGE_REPORT_CONTRACT_ID",
    "MixedBackendDeliveryStageModel",
    "MixedBackendExecutionStageModel",
    "MixedBackendHandoffStageModel",
    "MixedBackendObservationStageModel",
    "MixedBackendOwnerReadbackStageModel",
    "MixedBackendStageReportModel",
    "MixedBackendTimeGrantStageModel",
]
