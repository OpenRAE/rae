"""Value-free lineage for the closed materialized SDL phase."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator
from raes_contracts.addressing import CompiledAddress

from ._identifiers import QUALIFIED_IDENTIFIER_MAX_LENGTH, PortableIdentifier, require_qualified_identifier
from .explicitness import ExplicitnessProvenance
from .phase_contracts import FrozenPhaseModel, SemanticDigest

MaterializationDigest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
MaterializationPointer = Annotated[str, Field(pattern=r"^(?:/(?:[^~/]|~[01])*)*$", max_length=4096)]
MaterializationIdentity = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[^\s\x00-\x1f]+$")]


class InstantiatedMaterializationDigest(SemanticDigest):
    """Identity of the original admitted input, not the materialized artifact."""

    profile: Literal["raes-sdl-instantiated-snapshot/v2"]


class MaterializationProducer(FrozenPhaseModel):
    """The selected producer and its exact configured manifest."""

    name: MaterializationIdentity
    version: MaterializationIdentity
    configuration_digest: MaterializationDigest
    manifest_digest: MaterializationDigest


class MaterializationOrigin(FrozenPhaseModel):
    """One disclosed difference; world values stay in their owning SDL fields."""

    field_pointer: MaterializationPointer
    source_pointer: MaterializationPointer | None = None
    change: Literal["added", "selected", "removed"]
    origin: ExplicitnessProvenance

    @model_validator(mode="after")
    def _validate_difference_shape(self) -> MaterializationOrigin:
        if not self.field_pointer or self.field_pointer.startswith("/materialization_provenance"):
            raise ValueError("materialization origins must address scenario content")
        if self.change == "added" and self.source_pointer is not None:
            raise ValueError("an added element has no source pointer")
        if self.change != "added" and self.source_pointer is None:
            raise ValueError("a changed or removed element requires its source pointer")
        if self.origin is not ExplicitnessProvenance.BACKEND_REALIZED:
            raise ValueError("materialization differences require backend origin; source origins remain inherited")
        return self


class MaterializedResourceBinding(FrozenPhaseModel):
    """Portable resource and source-declaration identity for one realized node."""

    address: CompiledAddress
    node_name: Annotated[str, Field(min_length=1, max_length=QUALIFIED_IDENTIFIER_MAX_LENGTH)]
    source_node: Annotated[str, Field(min_length=1, max_length=QUALIFIED_IDENTIFIER_MAX_LENGTH)] | None = None
    instance_index: int | None = Field(default=None, ge=0)

    @field_validator("node_name", "source_node")
    @classmethod
    def _validate_qualified_name(cls, value: str | None) -> str | None:
        return None if value is None else require_qualified_identifier(value, field_name="materialized node")


class MaterializationProvenance(FrozenPhaseModel):
    """Execution-bound producer assertion, separate from authoring authority."""

    profile: Literal["raes-materialization-attestation/v1"]
    attestation_id: PortableIdentifier
    authored_digest: SemanticDigest
    instantiated_digest: InstantiatedMaterializationDigest
    plan_digest: MaterializationDigest
    predecessor_digest: MaterializationDigest
    operation_id: MaterializationIdentity
    run_id: MaterializationIdentity
    recorded_at: AwareDatetime
    boundary: Literal["post-materialization"]
    producer: MaterializationProducer
    coverage_profile: Literal["raes-materialization-effects/v1"]
    origins: tuple[MaterializationOrigin, ...] = Field(max_length=4096)
    resource_bindings: tuple[MaterializedResourceBinding, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def _validate_identities(self) -> MaterializationProvenance:
        for identities in (
            [(origin.change == "removed", origin.field_pointer) for origin in self.origins],
            [(binding.address, binding.instance_index) for binding in self.resource_bindings],
            [(binding.node_name, binding.instance_index) for binding in self.resource_bindings],
        ):
            if len(identities) != len(set(identities)):
                raise ValueError("materialization provenance identities must be unique")
        return self
