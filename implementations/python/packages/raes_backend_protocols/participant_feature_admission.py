"""Evidence-backed admission for participant semantic feature support."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from raes_contracts.errors import ConflictError
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .capabilities import (
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
    ParticipantFeatureSupport,
)

if TYPE_CHECKING:
    from .backend_manifest import BackendManifest


_PARTICIPANT_FEATURE_SUPPORT_RANK = {
    ParticipantFeatureSupportLevel.UNSUPPORTED: 0,
    ParticipantFeatureSupportLevel.DISCLOSED_WEAK: 1,
    ParticipantFeatureSupportLevel.BOUNDED: 2,
    ParticipantFeatureSupportLevel.EXACT: 3,
}


def _participant_feature_required_contracts(feature: str) -> frozenset[str]:
    for scope in (
        PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
        PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
    ):
        contracts = PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[scope].get(feature)
        if contracts is not None:
            return contracts
    return frozenset()


def _validate_downgrade_authorization(
    feature: str,
    allowed_downgrade_level: ParticipantFeatureSupportLevel | None,
    downgrade_policy_ref: str | None,
    downgrade_provenance_ref: str | None,
) -> None:
    if allowed_downgrade_level is not None and (not downgrade_policy_ref or not downgrade_provenance_ref):
        raise ConflictError(
            f"participant feature '{feature}' requires explicit downgrade authorization "
            "with policy and provenance references"
        )


def _participant_feature_declaration(
    manifest: BackendManifest,
    feature: str,
) -> ParticipantFeatureSupport | None:
    capability = manifest.participant_runtime
    if capability is None:
        raise ConflictError(f"participant feature '{feature}' requires participant runtime capabilities")

    supported_features = capability.supported_behavior_features | capability.supported_interaction_features
    declaration = next((entry for entry in capability.feature_support if entry.feature == feature), None)
    if declaration is None:
        if feature in supported_features and feature not in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES:
            return None
        raise ConflictError(f"participant feature '{feature}' has no explicit support declaration")
    if declaration.support_level == ParticipantFeatureSupportLevel.UNSUPPORTED:
        raise ConflictError(f"participant feature '{feature}' is explicitly unsupported")
    return declaration


def _validate_participant_feature_evidence(
    manifest: BackendManifest,
    feature: str,
    declaration: ParticipantFeatureSupport,
) -> None:
    missing_contracts = sorted(_participant_feature_required_contracts(feature) - manifest.supported_contract_versions)
    if missing_contracts:
        raise ConflictError(
            f"participant feature '{feature}' is missing required contracts: {', '.join(missing_contracts)}"
        )
    if not declaration.evidence_refs and feature in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES:
        raise ConflictError(f"participant feature '{feature}' has no conformance evidence")


def _validate_participant_feature_strength(
    feature: str,
    declaration: ParticipantFeatureSupport,
    required_level: ParticipantFeatureSupportLevel,
    allowed_downgrade_level: ParticipantFeatureSupportLevel | None,
) -> None:
    declared_rank = _PARTICIPANT_FEATURE_SUPPORT_RANK[declaration.support_level]
    required_rank = _PARTICIPANT_FEATURE_SUPPORT_RANK[required_level]
    if declared_rank >= required_rank:
        return
    if allowed_downgrade_level is None:
        raise ConflictError(
            f"participant feature '{feature}' requires {required_level.value} support; "
            f"backend declares {declaration.support_level.value}"
        )
    if declaration.support_level != allowed_downgrade_level:
        raise ConflictError(
            f"participant feature '{feature}' authorized downgrade is "
            f"{allowed_downgrade_level.value}; backend declares {declaration.support_level.value}"
        )


def resolve_participant_feature_support(
    manifest: BackendManifest,
    feature: str,
    *,
    required_level: ParticipantFeatureSupportLevel = ParticipantFeatureSupportLevel.EXACT,
    allowed_downgrade_level: ParticipantFeatureSupportLevel | None = None,
    downgrade_policy_ref: str | None = None,
    downgrade_provenance_ref: str | None = None,
) -> ParticipantFeatureSupport | None:
    """Resolve one required participant feature without inventing support.

    Raise ``ConflictError`` when the backend declaration cannot satisfy the requirement.
    """

    _validate_downgrade_authorization(
        feature,
        allowed_downgrade_level,
        downgrade_policy_ref,
        downgrade_provenance_ref,
    )
    declaration = _participant_feature_declaration(manifest, feature)
    if declaration is None:
        return None
    _validate_participant_feature_evidence(manifest, feature, declaration)
    _validate_participant_feature_strength(
        feature,
        declaration,
        required_level,
        allowed_downgrade_level,
    )
    return declaration


def participant_feature_support_gaps(
    manifest: BackendManifest,
    features: Iterable[str],
    *,
    required_level: ParticipantFeatureSupportLevel = ParticipantFeatureSupportLevel.EXACT,
) -> tuple[str, ...]:
    """Return fail-closed gaps for required participant semantic features."""

    gaps: list[str] = []
    for feature in sorted(set(features)):
        try:
            resolve_participant_feature_support(
                manifest,
                feature,
                required_level=required_level,
            )
        except ConflictError as exc:
            gaps.append(str(exc))
    return tuple(gaps)


__all__ = ["participant_feature_support_gaps", "resolve_participant_feature_support"]
