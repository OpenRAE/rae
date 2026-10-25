"""Exact optional participant composition of an already settled world inject."""

from __future__ import annotations

import base64
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from .backend_operation import OperationArtifactReferenceModel, OperationContractModel, OperationIdentifier
from .base import PrefixedDigestString
from .inject_occurrence_outcome import InjectOccurrenceCorrelationModel


class ParticipantInjectControlReferenceModel(OperationContractModel):
    """One accepted application, never a reusable permission or latest-event query."""

    event_id: OperationIdentifier
    occurrence_revision: StrictInt = Field(ge=1, le=1_000_000)
    digest: PrefixedDigestString


class ParticipantInjectApplicationModel(OperationContractModel):
    """Caller selection; the runtime resolves and authorizes every join independently."""

    schema_version: Literal["participant-inject-application/v1"] = "participant-inject-application/v1"
    request_key: OperationIdentifier
    world_operation_id: OperationIdentifier
    delivery_address: OperationIdentifier
    delivery_digest: PrefixedDigestString
    participant_address: OperationIdentifier
    episode_id: OperationIdentifier
    expected_snapshot_revision: StrictInt = Field(ge=0)
    control: ParticipantInjectControlReferenceModel | None = None


class ParticipantInjectContentModel(OperationContractModel):
    """Owner-projected content with explicit encoding; no implicit world-evidence copy."""

    schema_version: Literal["participant-inject-delivery/v1"] = "participant-inject-delivery/v1"
    view_id: OperationIdentifier
    participant_address: OperationIdentifier
    episode_id: OperationIdentifier
    application: ParticipantInjectApplicationModel
    source_snapshot_ref: OperationIdentifier
    correlation: InjectOccurrenceCorrelationModel
    disclosed_item: OperationArtifactReferenceModel
    visibility_projection_ref: OperationIdentifier
    observation_boundary_ref: OperationIdentifier
    media_type: str = Field(
        default="text/plain", min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+$"
    )
    content_encoding: Literal["utf-8", "base64"] = "utf-8"
    content: str = Field(max_length=87_384)

    @model_validator(mode="after")
    def _recipient(self) -> ParticipantInjectContentModel:
        if (self.participant_address, self.episode_id) != (
            self.application.participant_address,
            self.application.episode_id,
        ):
            raise ValueError("inject content must retain the exact application recipient")
        try:
            data = (
                self.content.encode("utf-8")
                if self.content_encoding == "utf-8"
                else base64.b64decode(self.content, validate=True)
            )
        except ValueError:
            raise ValueError("inject content encoding is invalid") from None
        if len(data) > 65_536:
            raise ValueError("inject content exceeds its byte bound")
        if self.source_snapshot_ref != f"runtime.snapshot.revision.{self.application.expected_snapshot_revision}":
            raise ValueError("inject content must retain its admitted snapshot cut")
        return self


class ParticipantInjectDeliveryReceiptModel(OperationContractModel):
    """Durable delivery operation identity and its governed local result."""

    schema_version: Literal["participant-inject-delivery-receipt/v1"] = "participant-inject-delivery-receipt/v1"
    operation_id: OperationIdentifier
    delivery: ParticipantInjectContentModel

    @model_validator(mode="after")
    def _operation_identity(self) -> ParticipantInjectDeliveryReceiptModel:
        if self.operation_id == self.delivery.application.world_operation_id:
            raise ValueError("world and delivery operations must remain distinct")
        return self
