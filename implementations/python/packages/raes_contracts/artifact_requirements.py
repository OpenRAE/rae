"""Portable artifact requirement, backend capability, and satisfaction carriers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.artifact_requirements import (
    ArtifactIdentity,
    ArtifactMechanismProfile,
    ArtifactRequirement,
    Source,
)

from ._base import ContractModel, NonEmptyString
from .apparatus import ApparatusIdentity
from .versions import ARTIFACT_REQUIREMENT_SCHEMA_VERSION

Sha256DigestString = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
_INVARIANT_VALIDATOR = "raes_contracts.artifact_requirements.validate_artifact_requirement_invariants"


def _require_unique(values: list[object], *, field_name: str) -> None:
    normalized = [repr(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")


def artifact_requirement_invariant_violations(payload: object) -> tuple[str, ...]:
    """Evaluate the cross-object invariants published in ``x-raes-invariants``."""

    source, requirement, structural_violation = _artifact_requirement_mappings(payload)
    if structural_violation is not None:
        return (structural_violation,)
    assert source is not None
    assert requirement is not None
    violations = [
        *_exact_identity_violations(source, requirement),
        *_materialization_violations(requirement),
    ]
    return tuple(dict.fromkeys(violations))


def _artifact_requirement_mappings(
    payload: object,
) -> tuple[Mapping[object, object] | None, Mapping[object, object] | None, str | None]:
    source: Mapping[object, object] | None = None
    requirement: Mapping[object, object] | None = None
    violation: str | None = None
    if not isinstance(payload, Mapping):
        violation = "artifact-requirement-document-object"
    else:
        source_payload = payload.get("source")
        if not isinstance(source_payload, Mapping):
            violation = "artifact-requirement-source-object"
        else:
            source = source_payload
            requirement_payload = source.get("artifact_requirement")
            if not isinstance(requirement_payload, Mapping):
                violation = "artifact-requirement-present"
            else:
                requirement = requirement_payload
    return source, requirement, violation


def _exact_identity_violations(
    source: Mapping[object, object],
    requirement: Mapping[object, object],
) -> list[str]:
    if requirement.get("explicitness") != "exact":
        return []
    identity = requirement.get("exact_artifact")
    if not isinstance(identity, Mapping):
        return ["exact-artifact-present"]
    violations: list[str] = []
    if source.get("name") != identity.get("artifact_id"):
        violations.append("exact-source-artifact-id-match")
    if source.get("version", "*") != identity.get("version"):
        violations.append("exact-source-version-match")
    return violations


def _materialization_violations(requirement: Mapping[object, object]) -> list[str]:
    locked_inputs = requirement.get("locked_inputs", [])
    declared_input_ids = {
        item.get("input_id")
        for item in locked_inputs
        if isinstance(item, Mapping) and isinstance(item.get("input_id"), str)
    }
    specifications = requirement.get("materialization_specifications", [])
    violations: list[str] = []
    for specification in specifications:
        violations.extend(_materialization_specification_violations(specification, declared_input_ids))
    return violations


def _materialization_specification_violations(
    specification: object,
    declared_input_ids: set[object],
) -> list[str]:
    if not isinstance(specification, Mapping):
        return []
    violations: list[str] = []
    profile = specification.get("profile")
    mechanism = profile.get("mechanism") if isinstance(profile, Mapping) else None
    governed_extension = isinstance(mechanism, str) and mechanism.startswith("x-")
    if mechanism != "materialization-specification" and not governed_extension:
        violations.append("materialization-profile-mechanism")
    referenced = specification.get("locked_input_ids", [])
    if isinstance(referenced, list) and not set(referenced).issubset(declared_input_ids):
        violations.append("materialization-locked-input-join")
    return violations


def validate_artifact_requirement_invariants(
    payload: Mapping[str, object],
) -> ArtifactRequirementContractModel:
    """Enforce the published cross-object semantic-invariant profile."""

    violations = artifact_requirement_invariant_violations(payload)
    if violations:
        raise ValueError("artifact requirement semantic invariants failed: " + ", ".join(violations))
    return ArtifactRequirementContractModel.model_validate(payload)


class ArtifactRequirementSource(Source):
    """Contract-specific source that cannot omit portable artifact demand."""

    artifact_requirement: ArtifactRequirement


class ArtifactRequirementContractModel(ContractModel):
    """Published source-artifact requirement contract."""

    schema_version: Literal[ARTIFACT_REQUIREMENT_SCHEMA_VERSION] = ARTIFACT_REQUIREMENT_SCHEMA_VERSION
    source: ArtifactRequirementSource

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["x-raes-invariants"] = [
            {
                "id": "exact-source-artifact-id-match",
                "description": (
                    "An exact requirement's immutable artifact id must equal the enclosing Source selector name."
                ),
                "level": "error",
                "validator": _INVARIANT_VALIDATOR,
                "inputs": [
                    {
                        "contract_id": "artifact-requirement-v1",
                        "instance_path": "#",
                    }
                ],
            },
            {
                "id": "exact-source-version-match",
                "description": (
                    "An exact requirement's immutable artifact version must "
                    "equal the enclosing Source selector version."
                ),
                "level": "error",
                "validator": _INVARIANT_VALIDATOR,
                "inputs": [
                    {
                        "contract_id": "artifact-requirement-v1",
                        "instance_path": "#",
                    }
                ],
            },
            {
                "id": "materialization-locked-input-join",
                "description": (
                    "Every materialization locked_input_id must resolve to a "
                    "locked input declared by the same artifact requirement."
                ),
                "level": "error",
                "validator": _INVARIANT_VALIDATOR,
                "inputs": [
                    {
                        "contract_id": "artifact-requirement-v1",
                        "instance_path": "#",
                    }
                ],
            },
        ]
        return json_schema


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
    "ARTIFACT_REQUIREMENT_SCHEMA_VERSION",
    "ArtifactAcquisitionTimingModel",
    "ArtifactAvailabilityContext",
    "ArtifactMechanismCapability",
    "ArtifactRequirementContractModel",
    "ArtifactRequirementAvailability",
    "ArtifactRequirementSource",
    "ArtifactSatisfactionDisclosureModel",
    "artifact_requirement_invariant_violations",
    "validate_artifact_requirement_invariants",
]
