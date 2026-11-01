"""Portable artifact requirement, backend capability, and satisfaction carriers."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from raes_contracts.artifact_identity import ArtifactIdentity, ArtifactMechanismProfile

from ._base import ContractModel, NonEmptyString
from .apparatus import ApparatusIdentity

Sha256DigestString = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


def _require_unique(values: list[object], *, field_name: str) -> None:
    normalized = [repr(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")


class ArtifactAcquisitionTimingModel(ContractModel):
    """One exact acquisition/timing combination supported by a backend."""

    acquisition: Literal["pull", "copy", "import", "local-lookup", "none"]
    timing: Literal["publication", "pack-ingestion", "backend-preparation", "realization"]


class ArtifactMechanismCapability(ContractModel):
    """Mechanism-indexed backend support without Cartesian-product overclaim."""

    mechanism: ArtifactMechanismProfile
    supported_requirement_kinds: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    supported_routes: list[ArtifactAcquisitionTimingModel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_capability(self) -> ArtifactMechanismCapability:
        _require_unique(
            list(self.supported_requirement_kinds),
            field_name="artifact mechanism supported_requirement_kinds",
        )
        _require_unique(
            [(route.acquisition, route.timing) for route in self.supported_routes],
            field_name="artifact mechanism supported_routes",
        )
        return self


class ArtifactRequirementAvailability(ContractModel):
    """Trusted operational facts scoped to one compiled artifact requirement."""

    address: NonEmptyString

    available_artifact_digests: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    available_candidate_ids: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    verified_locked_input_ids: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    satisfied_constraint_ids: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    available_materialization_specification_digests: list[Sha256DigestString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    verified_integrity_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    verified_authenticity_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    verified_admission_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    verified_provenance_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    verified_evidence_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def validate_unique_facts(self) -> ArtifactRequirementAvailability:
        for field_name in (
            "available_artifact_digests",
            "available_candidate_ids",
            "verified_locked_input_ids",
            "satisfied_constraint_ids",
            "available_materialization_specification_digests",
            "verified_integrity_refs",
            "verified_authenticity_refs",
            "verified_admission_refs",
            "verified_provenance_refs",
            "verified_evidence_refs",
        ):
            _require_unique(
                list(getattr(self, field_name)),
                field_name=f"artifact availability {field_name}",
            )
        return self


class ArtifactAvailabilityContext(ContractModel):
    """Processor-owned artifact facts, partitioned by compiled address."""

    requirements: list[ArtifactRequirementAvailability] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def validate_unique_addresses(self) -> ArtifactAvailabilityContext:
        _require_unique(
            [item.address for item in self.requirements],
            field_name="artifact availability requirement addresses",
        )
        return self

    def for_address(self, address: str) -> ArtifactRequirementAvailability:
        """Return trusted facts for ``address`` or an empty scoped carrier."""

        return next(
            (item for item in self.requirements if item.address == address),
            ArtifactRequirementAvailability(address=address),
        )


class ArtifactSatisfactionDisclosureModel(ContractModel):
    """Typed realized artifact and mechanism disclosure.

    Mutable provider/account/project/region/registry/channel locations are
    deliberately absent. They belong to operational evidence, not artifact or
    scenario identity.
    """

    requirement_id: NonEmptyString
    artifact: ArtifactIdentity
    mechanism: ArtifactMechanismProfile
    acquisition: Literal["pull", "copy", "import", "local-lookup", "none"]
    timing: Literal["publication", "pack-ingestion", "backend-preparation", "realization"]
    backend: ApparatusIdentity
    candidate_id: NonEmptyString | None = None
    materialization_specification_id: NonEmptyString | None = None
    materialization_specification_digest: Sha256DigestString | None = None
    satisfied_constraint_ids: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    locked_input_ids: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    integrity_refs: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    authenticity_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    admission_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    provenance_refs: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    evidence_refs: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def validate_references(self) -> ArtifactSatisfactionDisclosureModel:
        for field_name in (
            "satisfied_constraint_ids",
            "locked_input_ids",
            "integrity_refs",
            "authenticity_refs",
            "admission_refs",
            "provenance_refs",
            "evidence_refs",
        ):
            _require_unique(
                list(getattr(self, field_name)),
                field_name=f"artifact satisfaction {field_name}",
            )
        return self


__all__ = [
    "ArtifactAcquisitionTimingModel",
    "ArtifactAvailabilityContext",
    "ArtifactMechanismCapability",
    "ArtifactRequirementAvailability",
    "ArtifactSatisfactionDisclosureModel",
]
