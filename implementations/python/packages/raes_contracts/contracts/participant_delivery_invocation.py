"""Core delivery invocation coordinates, independent of autonomous scheduling."""

from typing import Literal

from pydantic import Field, StrictInt, model_validator

from .backend_operation import OperationContractModel, OperationIdentifier
from .participant_action_admission import implementation_selection_violations
from .participant_inject_application import ParticipantInjectContentModel
from .participant_manifests import ParticipantImplementationManifestModel, ParticipantImplementationSelectionModel


class ParticipantDeliveryInvocationRequestModel(OperationContractModel):
    schema_version: Literal["participant-delivery-invocation-request/v1"] = "participant-delivery-invocation-request/v1"
    request_key: OperationIdentifier
    delivery_operation_id: OperationIdentifier
    implementation_manifest: ParticipantImplementationManifestModel
    implementation_selection: ParticipantImplementationSelectionModel

    @model_validator(mode="after")
    def _selection(self) -> ParticipantDeliveryInvocationRequestModel:
        violations = implementation_selection_violations(
            self.implementation_selection.participant_address,
            self.implementation_manifest,
            self.implementation_selection,
        )
        if violations:
            raise ValueError(violations[0])
        return self


class ParticipantDeliveryInvocationContextModel(OperationContractModel):
    schema_version: Literal["participant-delivery-invocation-context/v1"] = "participant-delivery-invocation-context/v1"
    invocation_id: OperationIdentifier
    delivery_operation_ref: OperationIdentifier
    delivery: ParticipantInjectContentModel
    implementation_manifest: ParticipantImplementationManifestModel
    implementation_selection: ParticipantImplementationSelectionModel
    execution_scope_ref: OperationIdentifier
    execution_generation: StrictInt = Field(ge=0)

    @property
    def participant_address(self) -> str:
        return self.delivery.participant_address

    @property
    def episode_id(self) -> str:
        return self.delivery.episode_id

    @model_validator(mode="after")
    def _selection(self) -> ParticipantDeliveryInvocationContextModel:
        violations = implementation_selection_violations(
            self.participant_address, self.implementation_manifest, self.implementation_selection
        )
        if violations:
            raise ValueError(violations[0])
        if self.invocation_id != self.execution_scope_ref:
            raise ValueError("delivery invocation must retain its own execution scope")
        return self


class ParticipantDeliveryInvocationOutcomeModel(OperationContractModel):
    schema_version: Literal["participant-delivery-invocation-outcome/v1"] = "participant-delivery-invocation-outcome/v1"
    status: Literal["succeeded", "failed", "indeterminate"]
