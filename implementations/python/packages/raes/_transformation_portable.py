"""Canonical portable-contract transformations and comparisons."""

from __future__ import annotations

from copy import deepcopy

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationKind,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    PreservationOutcome,
    TransformationCheckOutcome,
)
from raes_contracts.contracts.base import ContractModel

from ._transformation_support import (
    CANONICAL_IDENTITY_PROFILE,
    DEFAULT_POLICY_PAYLOAD,
    PORTABLE_CANONICAL_PROFILE,
    PORTABLE_CANONICALIZE_PROFILE,
    check,
)
from ._transformation_types import (
    CanonicalArtifactComparison,
    PortableContractTransformationResult,
    SDLAuthoringArtifact,
)
from .canonical import canonical_materialized_sdl_digest, canonical_sdl_digest
from .materialization import MaterializedScenario
from .scenario import ExpandedScenario, Scenario


def _portable_contract_profile(model: ContractModel) -> str:
    for attribute in ("schema_version", "profile"):
        value = getattr(model, attribute, None)
        if isinstance(value, str) and value:
            return value
    raise TypeError("portable transformation requires an explicit governed schema_version or profile")


def canonicalize_portable_contract(
    source: ContractModel,
) -> PortableContractTransformationResult:
    """Re-admit an isolated portable contract and verify canonical identity."""

    if not isinstance(source, ContractModel):
        raise TypeError("portable contract canonicalization requires a ContractModel")
    source_payload = source.model_dump(mode="json")
    source_digest = canonical_json_digest(source_payload)
    output = type(source).model_validate(deepcopy(source_payload))
    target_digest = canonical_json_digest(output.model_dump(mode="json"))
    if source_digest != target_digest:
        raise ValueError("portable contract readmission did not preserve canonical identity")
    contract_profile = _portable_contract_profile(source)
    policy_digest = canonical_json_digest(DEFAULT_POLICY_PAYLOAD)
    derivation_digest = canonical_json_digest(
        {
            "operation_profile": PORTABLE_CANONICALIZE_PROFILE,
            "policy_digest": policy_digest,
            "source_digest": source_digest,
            "source_profile": contract_profile,
        }
    )
    report = ArtifactTransformationReportModel(
        operation_profile=PORTABLE_CANONICALIZE_PROFILE,
        status=ArtifactTransformationStatus.SUCCESS,
        artifact_kind=ArtifactTransformationKind.PORTABLE_CONTRACT,
        source_profile=contract_profile,
        target_profile=contract_profile,
        canonicalization_profile=PORTABLE_CANONICAL_PROFILE,
        source_digest=source_digest,
        target_digest=target_digest,
        policy_digest=policy_digest,
        derivation_digest=derivation_digest,
        preconditions=(check("source-admitted", TransformationCheckOutcome.PASSED),),
        postconditions=(
            check("canonical-identity", TransformationCheckOutcome.PASSED),
            check("target-admitted", TransformationCheckOutcome.PASSED),
        ),
        preservation=ArtifactTransformationPreservationModel(
            profile=CANONICAL_IDENTITY_PROFILE,
            outcome=PreservationOutcome.VERIFIED,
            evidence_digests=(source_digest,),
            limitations=("Canonical identity does not establish behavioral or backend equivalence.",),
        ),
    )
    return PortableContractTransformationResult(output=output, report=report)


def compare_canonical_artifacts(
    left: SDLAuthoringArtifact | MaterializedScenario | ContractModel,
    right: SDLAuthoringArtifact | MaterializedScenario | ContractModel,
) -> CanonicalArtifactComparison:
    """Compare two artifacts of the same kind under their owning canonicalizer."""

    if isinstance(left, (Scenario, ExpandedScenario)) and isinstance(right, (Scenario, ExpandedScenario)):
        left_identity = canonical_sdl_digest(left)
        right_identity = canonical_sdl_digest(right)
        artifact_kind = ArtifactTransformationKind.SDL_AUTHORING
        canonicalization_profile = left_identity.profile
        left_digest = left_identity.value
        right_digest = right_identity.value
    elif isinstance(left, MaterializedScenario) and isinstance(right, MaterializedScenario):
        left_identity = canonical_materialized_sdl_digest(left)
        right_identity = canonical_materialized_sdl_digest(right)
        artifact_kind = ArtifactTransformationKind.SDL_MATERIALIZATION
        canonicalization_profile = left_identity.profile
        left_digest = left_identity.value
        right_digest = right_identity.value
    elif isinstance(left, ContractModel) and isinstance(right, ContractModel):
        if _portable_contract_profile(left) != _portable_contract_profile(right):
            raise TypeError("portable canonical comparison requires the same exact contract profile")
        artifact_kind = ArtifactTransformationKind.PORTABLE_CONTRACT
        canonicalization_profile = PORTABLE_CANONICAL_PROFILE
        left_digest = canonical_json_digest(left.model_dump(mode="json"))
        right_digest = canonical_json_digest(right.model_dump(mode="json"))
    else:
        raise TypeError("canonical comparison requires two artifacts of the same supported artifact kind")
    return CanonicalArtifactComparison(
        artifact_kind=artifact_kind,
        canonicalization_profile=canonicalization_profile,
        relation_profile=CANONICAL_IDENTITY_PROFILE,
        left_digest=left_digest,
        right_digest=right_digest,
        equivalent=left_digest == right_digest,
    )


__all__ = ["canonicalize_portable_contract", "compare_canonical_artifacts"]
