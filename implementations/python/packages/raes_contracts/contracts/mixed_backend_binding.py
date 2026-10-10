"""Published executable bindings for admitted mixed-composition edges and handoffs.

One binding is the plain-data form of the installed bridge, time coordinator
and readback services for exactly one admitted ``sem-234/rev1`` directed edge
or component-changing phase transition. It names pinned identities and the
obligations they must honour, and each role has its own service. Decoding a
binding installs nothing, selects no provider and grants no execution
authority; trusted joins against the sealed profile live in
:mod:`raes_contracts.contracts.mixed_backend_validation`.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..addressing import CompiledAddress
from ..canonical import canonical_json_digest
from ..operation_lifecycle import OperationKind
from ..versions import MIXED_BACKEND_EXECUTION_BINDING_SCHEMA_VERSION
from .backend_operation import (
    OperationArtifactReferenceModel,
    OperationContractModel,
    OperationDigest,
    OperationIdentifier,
)
from .base import PrefixedDigestString
from .mixed_composition import MIXED_COMPOSITION_PROFILE_REVISION, MixedCompositionMappingLossModel

MIXED_BACKEND_EXECUTION_BINDING_CONTRACT_ID = "mixed-backend-execution-binding-v1"

# Ordering bases that can support a governed comparison; wall-clock-only,
# unknown and unsupported bases cannot be promoted to an executable order.
GovernedOrderingBasis = Literal[
    "total_order",
    "partial_order",
    "simultaneous",
    "serialized_backend_order",
    "simulation_tick",
    "control_plane_order",
    "logical_clock",
    "vector_clock",
]
_EvidenceRefs = Annotated[tuple[OperationIdentifier, ...], Field(min_length=1, max_length=64)]


class MixedBackendServiceModel(OperationContractModel):
    """Pinned installed implementation identity; never a module, path, URL or command."""

    service_ref: OperationIdentifier
    version: OperationIdentifier
    digest: OperationDigest


def _require_distinct_services(*services: MixedBackendServiceModel | None) -> None:
    # A service pinned to two roles could report two stages itself, such as a
    # bridge reading back its own delivery, so no two roles share a reference
    # or a digest.
    pinned = [service for service in services if service is not None]
    references = {service.service_ref for service in pinned}
    digests = {service.digest for service in pinned}
    if len(references) != len(pinned) or len(digests) != len(pinned):
        raise ValueError("a mixed binding must pin a distinct service for each role")


class MixedBackendTimeRequirementModel(OperationContractModel):
    """Named clocks, mapping and governed order a coordinator must grant before invocation."""

    time_model_ref: OperationIdentifier
    time_model_digest: PrefixedDigestString
    source_clock_address: CompiledAddress
    destination_clock_address: CompiledAddress
    mapping_ref: CompiledAddress
    ordering_basis: GovernedOrderingBasis
    required_comparison: Literal["ordered"] = "ordered"
    coordinator: MixedBackendServiceModel


class MixedBackendEdgeTimeRequirementModel(MixedBackendTimeRequirementModel):
    """Edge time requirement that also carries the admitted edge's temporal coupling."""

    temporal_coupling: Literal["tight", "bounded-asynchronous", "asynchronous"]


class MixedBackendEdgeBindingModel(OperationContractModel):
    """Bridge, coordinator and readers for one admitted directed edge.

    The destination provider executes the mapped action under one RAES
    participant-crossing operation; owning the effect confers no controller,
    disclosure or terminal-commit authority. Native translation stays inside
    the pinned bridge, so the compiled action subject is preserved. Each role
    is a distinct service, so the bridge never grants its own order or reads
    back its own delivery or observation.
    """

    kind: Literal["edge"]
    edge_id: OperationIdentifier
    operation_kind: Literal[OperationKind.PARTICIPANT_CROSSING] = OperationKind.PARTICIPANT_CROSSING
    owner_component_id: OperationIdentifier
    owner_allocation_id: OperationIdentifier
    participant_address: CompiledAddress
    audience_scope_ref: OperationIdentifier
    source_action_address: CompiledAddress
    destination_action_address: CompiledAddress
    subject_transformation: Literal["compiled-identity"] = "compiled-identity"
    bridge: MixedBackendServiceModel
    time: MixedBackendEdgeTimeRequirementModel
    mapping_loss: MixedCompositionMappingLossModel
    delivery_reader: MixedBackendServiceModel
    observation_reader: MixedBackendServiceModel | None = None
    required_evidence_refs: _EvidenceRefs

    @model_validator(mode="after")
    def _compiled_subject_preserved(self) -> Self:
        if self.source_action_address != self.destination_action_address:
            raise ValueError("compiled-identity mapping must preserve the authorized action address")
        return self

    @model_validator(mode="after")
    def _distinct_services(self) -> Self:
        _require_distinct_services(self.bridge, self.time.coordinator, self.delivery_reader, self.observation_reader)
        return self


class MixedBackendHandoffBindingModel(OperationContractModel):
    """Native responsibility transfer for one admitted component-changing transition.

    The transfer service, coordinator and owner reader are distinct services,
    so a transfer never grants its own order or reads back its own owner.
    """

    kind: Literal["handoff"]
    transition_id: OperationIdentifier
    operation_kind: Literal[OperationKind.COMPOSITION_PHASE] = OperationKind.COMPOSITION_PHASE
    source_component_id: OperationIdentifier
    destination_component_id: OperationIdentifier
    source_owner_ref: OperationIdentifier
    destination_owner_ref: OperationIdentifier
    transfer: MixedBackendServiceModel
    time: MixedBackendTimeRequirementModel
    owner_reader: MixedBackendServiceModel
    required_evidence_refs: _EvidenceRefs

    @model_validator(mode="after")
    def _distinct_owners(self) -> Self:
        if self.source_component_id == self.destination_component_id:
            raise ValueError("native handoff requires distinct source and destination components")
        return self

    @model_validator(mode="after")
    def _distinct_services(self) -> Self:
        _require_distinct_services(self.transfer, self.time.coordinator, self.owner_reader)
        return self


MixedBackendSubjectBinding = Annotated[
    MixedBackendEdgeBindingModel | MixedBackendHandoffBindingModel,
    Field(discriminator="kind"),
]


class MixedBackendExecutionBindingModel(OperationContractModel):
    """One installed executable binding, joined to its sealed profile by identity and digest."""

    schema_version: Literal[MIXED_BACKEND_EXECUTION_BINDING_SCHEMA_VERSION] = (
        MIXED_BACKEND_EXECUTION_BINDING_SCHEMA_VERSION
    )
    binding_id: OperationIdentifier
    profile_id: OperationIdentifier
    profile_revision: Literal[MIXED_COMPOSITION_PROFILE_REVISION] = MIXED_COMPOSITION_PROFILE_REVISION
    profile_digest: PrefixedDigestString
    subject: MixedBackendSubjectBinding


def mixed_backend_binding_reference(binding: MixedBackendExecutionBindingModel) -> OperationArtifactReferenceModel:
    """Return the content-bound command reference a shared operation request must carry."""

    return OperationArtifactReferenceModel(
        contract_id=MIXED_BACKEND_EXECUTION_BINDING_CONTRACT_ID,
        artifact_id=binding.binding_id,
        digest=canonical_json_digest(binding.model_dump(mode="json")),
    )


__all__ = [
    "GovernedOrderingBasis",
    "MIXED_BACKEND_EXECUTION_BINDING_CONTRACT_ID",
    "MixedBackendEdgeBindingModel",
    "MixedBackendEdgeTimeRequirementModel",
    "MixedBackendExecutionBindingModel",
    "MixedBackendHandoffBindingModel",
    "MixedBackendServiceModel",
    "MixedBackendTimeRequirementModel",
    "mixed_backend_binding_reference",
]
