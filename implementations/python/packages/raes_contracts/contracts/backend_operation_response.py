"""Backend reports are correlated evidence proposals, never runtime terminal commits."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from ..addressing import CompiledAddress
from ..operation_lifecycle import OperationState
from ..versions import BACKEND_OPERATION_RESPONSE_SCHEMA_VERSION
from .backend_operation import (
    BackendOperationBindingModel,
    OperationArtifactReferenceModel,
    OperationContractModel,
    OperationDigest,
    OperationIdentifier,
    OperationPositive,
)

OperationRefusalReason = Literal[
    "unsupported-contract",
    "unsupported-kind",
    "unsupported-guarantee",
    "context-refused",
    "budget-exhausted",
    "stale-binding",
    "conflicting-effects",
    "unavailable",
]


class BackendOperationAdmissionModel(OperationContractModel):
    kind: Literal["admission"] = "admission"
    disposition: Literal["willing", "refused"]
    capability_digest: OperationDigest
    reason: OperationRefusalReason | None = None

    @model_validator(mode="after")
    def _refusal_reason(self):
        if (self.disposition == "refused") != (self.reason is not None):
            raise ValueError("only a refused admission requires a refusal reason")
        return self


class BackendOperationAcknowledgementModel(OperationContractModel):
    kind: Literal["acknowledgement"] = "acknowledgement"
    disposition: Literal["accepted", "refused"]
    reason: OperationRefusalReason | None = None

    @model_validator(mode="after")
    def _refusal_reason(self):
        if (self.disposition == "refused") != (self.reason is not None):
            raise ValueError("only a refused acknowledgement requires a refusal reason")
        return self


class BackendOperationProgressModel(OperationContractModel):
    kind: Literal["progress"] = "progress"
    phase: Literal["queued", "executing", "settling"]
    evidence_refs: tuple[OperationArtifactReferenceModel, ...] = Field(default=(), max_length=32)


class BackendOperationControlDispositionModel(OperationContractModel):
    kind: Literal["control"] = "control"
    control_id: OperationIdentifier
    control_digest: OperationDigest
    disposition: Literal["recorded", "accepted", "refused", "unsupported", "already-terminal"]


class BackendOperationEffectsModel(OperationContractModel):
    """Effect knowledge and cessation are independent, scoped backend assertions."""

    effect: Literal["absent", "complete", "partial", "unknown"]
    cessation_established: StrictBool
    evidence_refs: tuple[OperationArtifactReferenceModel, ...] = Field(default=(), max_length=32)
    residual_scope: tuple[CompiledAddress, ...] = Field(default=(), max_length=256)
    residual_state: OperationArtifactReferenceModel | None = None
    external_fence: OperationArtifactReferenceModel | None = None

    @model_validator(mode="after")
    def _evidence_boundary(self):
        if (self.effect != "unknown" or self.cessation_established or self.external_fence) and not self.evidence_refs:
            raise ValueError("known effects, cessation and external fencing require evidence")
        if bool(self.residual_scope) != (self.residual_state is not None):
            raise ValueError("residual scope and state must be reported together")
        if self.effect == "partial" and self.residual_state is None:
            raise ValueError("known partial effects require residual state and scope")
        if self.effect == "absent" and self.residual_state is not None:
            raise ValueError("absent effects cannot carry residual changes")
        if self.residual_state and self.residual_state.contract_id != "runtime-snapshot-v1":
            raise ValueError("residual state must reference the native runtime snapshot contract")
        return self


class BackendOperationOutcomeModel(OperationContractModel):
    """Proposed outcome requiring RAE's native validation and atomic publication."""

    kind: Literal["outcome"] = "outcome"
    proposed_state: Literal[
        OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED, OperationState.INDETERMINATE
    ]
    effects: BackendOperationEffectsModel
    satisfaction: Literal["satisfied", "unsatisfied", "unknown"]
    release_gates_satisfied: StrictBool
    cancellation_established: StrictBool
    result: OperationArtifactReferenceModel | None = None

    @model_validator(mode="after")
    def _honest_outcome(self):
        known = self.effects.effect != "unknown" and self.effects.cessation_established
        if self.proposed_state != OperationState.INDETERMINATE and not known:
            raise ValueError("unknown effects or unproved cessation require indeterminate outcome")
        if self.proposed_state == OperationState.SUCCEEDED:
            if self.satisfaction != "satisfied" or not self.release_gates_satisfied or self.result is None:
                raise ValueError("success requires complete satisfaction, result and release gates")
            if self.effects.effect == "partial":
                raise ValueError("partial effects cannot establish success")
        if self.proposed_state == OperationState.FAILED and self.satisfaction != "unsatisfied":
            raise ValueError("known failure requires established non-satisfaction")
        if self.cancellation_established != (self.proposed_state == OperationState.CANCELLED):
            raise ValueError("only an established cancellation may propose cancelled")
        return self


class BackendOperationReconciliationModel(OperationContractModel):
    """Observation for separately authorized resolution, with no replay instruction."""

    kind: Literal["reconciliation"] = "reconciliation"
    control_id: OperationIdentifier
    control_digest: OperationDigest
    effects: BackendOperationEffectsModel


BackendOperationMessage = Annotated[
    BackendOperationAdmissionModel
    | BackendOperationAcknowledgementModel
    | BackendOperationProgressModel
    | BackendOperationControlDispositionModel
    | BackendOperationOutcomeModel
    | BackendOperationReconciliationModel,
    Field(discriminator="kind"),
]


class BackendOperationResponseModel(OperationContractModel):
    schema_version: Literal[BACKEND_OPERATION_RESPONSE_SCHEMA_VERSION] = BACKEND_OPERATION_RESPONSE_SCHEMA_VERSION
    binding: BackendOperationBindingModel
    request_digest: OperationDigest
    sequence: OperationPositive
    message: BackendOperationMessage
