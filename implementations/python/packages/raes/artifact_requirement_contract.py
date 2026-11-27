"""The published source-artifact requirement contract (``artifact-requirement-v1``).

The contract extends the SDL ``Source`` model, so the SDL package owns it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes_contracts.contracts.base import ContractModel
from raes_contracts.versions import ARTIFACT_REQUIREMENT_SCHEMA_VERSION

from ._source import ArtifactRequirement, Source

_INVARIANT_VALIDATOR = "raes.artifact_requirement_contract.validate_artifact_requirement_invariants"


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


__all__ = [
    "ArtifactRequirementContractModel",
    "ArtifactRequirementSource",
    "artifact_requirement_invariant_violations",
    "validate_artifact_requirement_invariants",
]
