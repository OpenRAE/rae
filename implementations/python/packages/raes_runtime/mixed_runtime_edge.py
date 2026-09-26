"""Trusted executable bindings for admitted mixed-composition edges."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from re import fullmatch
from typing import Literal

from pydantic import Field, model_validator
from raes_contracts.addressing import require_compiled_address
from raes_contracts.contracts.base import ContractModel, NonEmptyString
from raes_contracts.contracts.time_model import TimeCoordinateModel


class MixedTimeCoordinationEvidence(ContractModel):
    """Correlated service grant checked against live time-runtime readback."""

    operation_id: NonEmptyString
    mapping_ref: NonEmptyString
    ordering_basis: NonEmptyString
    order_ref: NonEmptyString
    comparison: Literal["ordered", "incomparable"]
    source_coordinate: TimeCoordinateModel
    destination_coordinate: TimeCoordinateModel
    mapping_evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=64)
    timing_evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=64)


class MixedBridgeExecutionEvidence(ContractModel):
    """Separate execution, destination delivery, and audience readback facts."""

    operation_id: NonEmptyString
    bridge_ref: NonEmptyString
    bridge_version: NonEmptyString
    bridge_digest: NonEmptyString
    source_action_address: NonEmptyString
    destination_action_address: NonEmptyString
    execution_status: Literal["succeeded", "failed", "partial", "unknown"]
    execution_evidence_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    delivery_evidence_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    observation_evidence_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    mapping_loss_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    cessation_evidence_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def _stage_dependencies(self) -> MixedBridgeExecutionEvidence:
        if self.delivery_evidence_refs and not self.execution_evidence_refs:
            raise ValueError("delivery requires execution evidence")
        if self.observation_evidence_refs and not self.delivery_evidence_refs:
            raise ValueError("participant observation requires delivery evidence")
        if self.execution_status == "succeeded" and not self.execution_evidence_refs:
            raise ValueError("successful execution requires readback evidence")
        if self.execution_status == "failed" and not self.cessation_evidence_refs:
            raise ValueError("known failure requires cessation evidence")
        return self


class MixedDeliveryReadback(ContractModel):
    """Destination receipt observed independently of the bridge result."""

    operation_id: NonEmptyString
    destination_component_id: NonEmptyString
    receipt_ref: NonEmptyString
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=64)


class MixedObservationReadback(ContractModel):
    """Participant/audience observation observed after authorized delivery."""

    operation_id: NonEmptyString
    participant_address: NonEmptyString
    audience_ref: NonEmptyString
    observation_ref: NonEmptyString
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=64)


@dataclass
class MixedEdgeExecutionCapture:
    """Transient outcome of one authorized bridge call, never a second ledger."""

    provider_calls: int = 0
    provider_started: bool = False
    method_completed: bool = False
    stage_readback_failed: bool = False
    time: MixedTimeCoordinationEvidence | None = None
    time_confirmed: bool = False
    bridge: MixedBridgeExecutionEvidence | None = None
    delivery_confirmed: bool = False
    observation_confirmed: bool = False


@dataclass(frozen=True)
class MixedEdgeExecutionBinding:
    """Installed bridge, mapping and time service for one admitted edge."""

    edge_id: str
    bridge_ref: str
    bridge_version: str
    bridge_digest: str
    source_action_address: str
    destination_action_address: str
    mapping_ref: str
    mapping_loss_ref: str
    time_runtime: object
    map_action: Callable[..., object]
    coordinate: Callable[..., object]
    bridge: Callable[..., object]
    delivery_readback: Callable[..., object] | None = None
    observation_readback: Callable[..., object] | None = None

    def __post_init__(self) -> None:
        if not self.edge_id or not self.bridge_ref or not self.bridge_version:
            raise ValueError("executable edge binding requires pinned bridge identity")
        if fullmatch(r"sha256:[a-f0-9]{64}", self.bridge_digest) is None:
            raise ValueError("executable edge binding requires a pinned bridge digest")
        for address in (self.source_action_address, self.destination_action_address, self.mapping_ref):
            require_compiled_address(address)
        if not self.mapping_loss_ref:
            raise ValueError("executable edge binding requires a declared mapping loss")
        if not all(callable(value) for value in (self.map_action, self.coordinate, self.bridge)):
            raise TypeError("executable edge binding requires mapping, coordination and bridge callables")
        if not callable(getattr(self.time_runtime, "state", None)):
            raise TypeError("executable edge binding requires time-runtime readback")
        for name in ("delivery_readback", "observation_readback"):
            reader = getattr(self, name)
            if reader is not None and not callable(reader):
                raise TypeError(f"executable edge {name} must be callable")


__all__ = (
    "MixedBridgeExecutionEvidence",
    "MixedEdgeExecutionBinding",
    "MixedEdgeExecutionCapture",
    "MixedDeliveryReadback",
    "MixedObservationReadback",
    "MixedTimeCoordinationEvidence",
)
