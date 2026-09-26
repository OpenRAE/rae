"""Trusted native responsibility transfer and readback for staged compositions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import Field
from raes_contracts.contracts.base import ContractModel, NonEmptyString


class MixedHandoffEvidence(ContractModel):
    operation_id: NonEmptyString
    transition_id: NonEmptyString
    source_component_id: NonEmptyString
    destination_component_id: NonEmptyString
    predecessor_history_head: NonEmptyString
    phase_revision: int = Field(ge=0)
    status: Literal["committed", "failed", "pending", "stale", "unknown"]
    order_ref: NonEmptyString
    evidence_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)


class MixedHandoffReadback(ContractModel):
    operation_id: NonEmptyString
    owner_component_id: NonEmptyString
    owner_ref: NonEmptyString
    phase_revision: int = Field(ge=0)
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class MixedHandoffBinding:
    """Installed transfer service for exactly one admitted phase transition."""

    transition_id: str
    source_component_id: str
    destination_component_id: str
    source_owner_ref: str
    destination_owner_ref: str
    time_model_ref: str
    time_model_digest: str
    source_clock_address: str
    destination_clock_address: str
    mapping_ref: str
    ordering_basis: str
    time_runtime: object
    coordinate: Callable[..., object]
    invoke: Callable[..., object]
    readback: Callable[..., object]

    def __post_init__(self) -> None:
        if not all(
            (
                self.transition_id,
                self.source_component_id,
                self.destination_component_id,
                self.source_owner_ref,
                self.destination_owner_ref,
                self.time_model_ref,
                self.time_model_digest,
                self.source_clock_address,
                self.destination_clock_address,
                self.mapping_ref,
                self.ordering_basis,
            )
        ):
            raise ValueError("executable handoff requires exact admitted owner identities")
        if self.source_component_id == self.destination_component_id:
            raise ValueError("executable handoff requires distinct component owners")
        if self.ordering_basis in {"wall_clock_only", "unknown", "unsupported"}:
            raise ValueError("executable handoff requires governed order")
        if not all(callable(value) for value in (self.coordinate, self.invoke, self.readback)):
            raise TypeError("executable handoff requires time coordination, invocation and native readback")
        if not callable(getattr(self.time_runtime, "state", None)):
            raise TypeError("executable handoff requires time-runtime readback")


__all__ = ("MixedHandoffBinding", "MixedHandoffEvidence", "MixedHandoffReadback")
