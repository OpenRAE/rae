"""Reusable-asset trust-policy contracts and schema-bundle helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..backend_profiles import BackendProfileModel
from ..versions import REUSABLE_ASSET_TRUST_POLICY_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, PositiveInteger
from .schema_constraints import _JSON_SCHEMA_DRAFT_2020_12, _JSON_SCHEMA_KEY
from .schema_invariants import _DEFS_KEY


def backend_profile_schema() -> dict[str, Any]:
    """Lazily import :class:`BackendProfileModel` to avoid an import cycle.

    ``backend_profiles`` imports :class:`ContractModel` and ``NonEmptyString``
    from this module, so eager import at module load would cycle. The
    deferred import here keeps the schema bundle wired up while letting
    ``backend_profiles`` build on the same closed-world primitives the rest
    of the contracts surface uses.
    """

    return BackendProfileModel.model_json_schema()


def event_stream_schema(title: str, item_schema: dict[str, Any]) -> dict[str, Any]:
    item_schema = dict(item_schema)
    defs = item_schema.pop(_DEFS_KEY, None)
    schema = {
        _JSON_SCHEMA_KEY: _JSON_SCHEMA_DRAFT_2020_12,
        "title": title,
        "type": "array",
        "items": item_schema,
    }
    if defs:
        schema[_DEFS_KEY] = defs
    return schema


REUSABLE_ASSET_FAMILIES: tuple[str, ...] = (
    "reusable_scenario",
    "associated_artifact_set",
    "sdl_module",
    "experiment_task",
    "experiment_study",
    "behavior_vocabulary",
    "participant_manifest",
    "evidence_artifact",
)


_REUSABLE_ASSET_FAMILY_SET = frozenset(REUSABLE_ASSET_FAMILIES)


ReusableAssetFamily = Literal[
    "reusable_scenario",
    "associated_artifact_set",
    "sdl_module",
    "experiment_task",
    "experiment_study",
    "behavior_vocabulary",
    "participant_manifest",
    "evidence_artifact",
]


ReusableAssetEvidenceClass = Literal[
    "integrity_digest",
    "authenticity_signature",
    "provenance_lock_record",
    "governance_source",
    "artifact_checksum",
]


REUSABLE_ASSET_EVIDENCE_CLASSES: tuple[str, ...] = (
    "integrity_digest",
    "authenticity_signature",
    "provenance_lock_record",
    "governance_source",
    "artifact_checksum",
)


_INTEGRITY_EVIDENCE_CLASSES = frozenset({"integrity_digest", "artifact_checksum"})


ReusableAssetEnforcement = Literal["required", "recommended", "optional"]


class ReusableAssetEvidenceRequirementModel(ContractModel):
    """One evidence-class expectation an asset family must satisfy.

    ``mechanism_ref`` names the *existing* RAES mechanism that carries the
    evidence (e.g. ``raes.lock.json`` digest pins, ``ExperimentChecksumModel``,
    ``controlled-vocabularies-v1.source``). GOV-913 declares policy over the
    incumbent mechanisms; it does not introduce a parallel evidence store, so
    this contract never carries the evidence payload itself — only the
    requirement and a reference to where the evidence lives.
    """

    evidence_class: ReusableAssetEvidenceClass
    enforcement: ReusableAssetEnforcement
    mechanism_ref: NonEmptyString
    description: NonEmptyString


class ReusableAssetAuthenticityPolicyModel(ContractModel):
    """Trusted-signer set + M-of-N threshold for signature-bearing families.

    Threshold trust (TUF) means no single key compromise forges an asset; the
    ``trusted_signer_set_ref`` points at the governed signer set (e.g. a
    ``RegistryTrustPolicy`` trusted-signer declaration) and never embeds key
    material — portable artifacts carry public verification material only.
    """

    trusted_signer_set_ref: NonEmptyString
    threshold: PositiveInteger


def _reusable_asset_duplicate_evidence_classes(
    requirements: list[ReusableAssetEvidenceRequirementModel],
) -> list[str]:
    classes = [requirement.evidence_class for requirement in requirements]
    return sorted({value for value in classes if classes.count(value) > 1})


def _reusable_asset_has_required_integrity(
    requirements: list[ReusableAssetEvidenceRequirementModel],
) -> bool:
    return any(
        requirement.evidence_class in _INTEGRITY_EVIDENCE_CLASSES and requirement.enforcement == "required"
        for requirement in requirements
    )


def _reusable_asset_signature_enforced(
    requirements: list[ReusableAssetEvidenceRequirementModel],
) -> bool:
    return any(
        requirement.evidence_class == "authenticity_signature"
        and requirement.enforcement in {"required", "recommended"}
        for requirement in requirements
    )


def _reusable_asset_has_required_governance_source(
    requirements: list[ReusableAssetEvidenceRequirementModel],
) -> bool:
    return any(
        requirement.evidence_class == "governance_source" and requirement.enforcement == "required"
        for requirement in requirements
    )


class ReusableAssetFamilyTrustPolicyModel(ContractModel):
    """Per-family trust/authenticity/integrity policy for a reusable asset."""

    asset_family: ReusableAssetFamily
    identity_basis: NonEmptyString
    evidence_requirements: list[ReusableAssetEvidenceRequirementModel] = Field(min_length=1)
    authenticity_policy: ReusableAssetAuthenticityPolicyModel | None = None

    @model_validator(mode="after")
    def _validate_family_policy(self) -> ReusableAssetFamilyTrustPolicyModel:
        duplicates = _reusable_asset_duplicate_evidence_classes(self.evidence_requirements)
        if duplicates:
            raise ValueError(f"asset family {self.asset_family!r} declares duplicate evidence classes: {duplicates}")

        if not _reusable_asset_has_required_integrity(self.evidence_requirements):
            raise ValueError(
                f"asset family {self.asset_family!r} must declare a required integrity evidence "
                "class (integrity_digest or artifact_checksum); integrity is the GOV-913 baseline"
            )

        signature_enforced = _reusable_asset_signature_enforced(self.evidence_requirements)
        if signature_enforced and self.authenticity_policy is None:
            raise ValueError(
                f"asset family {self.asset_family!r} enforces authenticity_signature but declares no "
                "authenticity_policy; a trusted-signer set and threshold are required (identity is not "
                "authenticity)"
            )
        if not signature_enforced and self.authenticity_policy is not None:
            raise ValueError(
                f"asset family {self.asset_family!r} declares an authenticity_policy without a "
                "required/recommended authenticity_signature requirement"
            )

        if self.asset_family == "behavior_vocabulary" and not _reusable_asset_has_required_governance_source(
            self.evidence_requirements
        ):
            raise ValueError(
                "asset family 'behavior_vocabulary' must declare a required governance_source "
                "evidence class; authoritative origin is a first-class evidence class for "
                "reusable governed vocabularies"
            )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        # The published schema is the portable contract external consumers
        # validate against; the security invariants must live in the schema
        # itself, not only in these Python validators (issue #115 review).
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        constraints: list[dict[str, Any]] = []
        # Every family MUST require at least one integrity evidence class.
        constraints.append(
            {
                "properties": {
                    "evidence_requirements": {
                        "contains": {
                            "type": "object",
                            "required": ["evidence_class", "enforcement"],
                            "properties": {
                                "evidence_class": {"enum": ["integrity_digest", "artifact_checksum"]},
                                "enforcement": {"const": "required"},
                            },
                        }
                    }
                },
                "required": ["evidence_requirements"],
            }
        )
        # Each evidence class may appear at most once within a family.
        for evidence_class in REUSABLE_ASSET_EVIDENCE_CLASSES:
            constraints.append(
                {
                    "properties": {
                        "evidence_requirements": {
                            "contains": {
                                "type": "object",
                                "required": ["evidence_class"],
                                "properties": {"evidence_class": {"const": evidence_class}},
                            },
                            "minContains": 0,
                            "maxContains": 1,
                        }
                    }
                }
            )
        # Enforced authenticity_signature requires a threshold-backed policy.
        constraints.append(
            {
                "if": {
                    "properties": {
                        "evidence_requirements": {
                            "contains": {
                                "type": "object",
                                "required": ["evidence_class", "enforcement"],
                                "properties": {
                                    "evidence_class": {"const": "authenticity_signature"},
                                    "enforcement": {"enum": ["required", "recommended"]},
                                },
                            }
                        }
                    },
                    "required": ["evidence_requirements"],
                },
                "then": {"required": ["authenticity_policy"]},
            }
        )
        # behavior_vocabulary MUST carry a required governance_source (authoritative
        # origin is a first-class evidence class for governed reusable semantics).
        constraints.append(
            {
                "if": {
                    "properties": {"asset_family": {"const": "behavior_vocabulary"}},
                    "required": ["asset_family"],
                },
                "then": {
                    "properties": {
                        "evidence_requirements": {
                            "contains": {
                                "type": "object",
                                "required": ["evidence_class", "enforcement"],
                                "properties": {
                                    "evidence_class": {"const": "governance_source"},
                                    "enforcement": {"const": "required"},
                                },
                            }
                        }
                    },
                    "required": ["evidence_requirements"],
                },
            }
        )
        json_schema.setdefault("allOf", []).extend(constraints)
        return json_schema


class ReusableAssetTrustPolicyModel(ContractModel):
    """Ecosystem trust/authenticity/integrity policy over reusable assets (GOV-913).

    A declarative, expectation-based policy: it declares, per asset family, the
    integrity/authenticity/provenance/governance evidence the ecosystem requires,
    referencing the existing RAES mechanisms that carry that evidence. It is not a
    per-asset trust record and it invents no cryptography. See
    ``specs/authority/reusable-asset-trust-integrity.md`` (normative) and ADR-071.
    """

    schema_version: Literal[REUSABLE_ASSET_TRUST_POLICY_SCHEMA_VERSION] = REUSABLE_ASSET_TRUST_POLICY_SCHEMA_VERSION
    policy_id: NonEmptyString
    families: list[ReusableAssetFamilyTrustPolicyModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_trust_policy(self) -> ReusableAssetTrustPolicyModel:
        declared = [family.asset_family for family in self.families]
        duplicates = sorted({value for value in declared if declared.count(value) > 1})
        if duplicates:
            raise ValueError(f"reusable asset trust policy declares duplicate asset families: {duplicates}")

        declared_set = set(declared)
        missing = sorted(_REUSABLE_ASSET_FAMILY_SET - declared_set)
        if missing:
            raise ValueError(
                f"reusable asset trust policy must cover every canonical reusable asset family; missing: {missing}"
            )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        # Encode complete-family-coverage in the portable schema: exactly the
        # canonical families, each present once (issue #115 review). With the
        # asset_family enum bounded to these values, min/max-items pinned to the
        # family count, and a `contains` clause per family, the only conforming
        # shape is a bijection onto the canonical set — matching the validator.
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        families = json_schema.get("properties", {}).get("families")
        if isinstance(families, dict):
            family_count = len(REUSABLE_ASSET_FAMILIES)
            families["minItems"] = family_count
            families["maxItems"] = family_count
            families["allOf"] = [
                {
                    "contains": {
                        "type": "object",
                        "required": ["asset_family"],
                        "properties": {"asset_family": {"const": family}},
                    }
                }
                for family in REUSABLE_ASSET_FAMILIES
            ]
        return json_schema
