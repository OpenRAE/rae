"""Explicit-loss SDL declaration removal."""

from __future__ import annotations

from copy import deepcopy

from pydantic import ValidationError
from raes_contracts.contracts import (
    ArtifactTransformationKind,
    ArtifactTransformationLossKind,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    ExternalConceptBindingDocumentModel,
    PreservationOutcome,
    TransformationCheckOutcome,
)
from raes_contracts.diagnostics import Severity

from ._declarations import build_declaration_index
from ._errors import SDLParseError, SDLValidationError
from ._transformation_support import (
    EXPLICIT_LOSS_PROFILE,
    REMOVE_PROFILE,
    SDL_CONTRACT_PROFILE,
    check,
    refused_removal,
    removal_loss,
    remove_derivation_digest,
    top_level_declaration,
    transformation_policy_digest,
)
from ._transformation_types import (
    ArtifactTransformationPolicy,
    RemoveSDLDeclarationRequest,
    SDLAuthoringArtifact,
    SDLTransformationResult,
)
from .canonical import SDLCanonicalDigest, canonical_sdl_digest
from .scenario import ExpandedScenario, Scenario
from .validator import SemanticValidator


def _removed_candidate(
    source: SDLAuthoringArtifact,
    *,
    section: str,
    local_key: str,
) -> SDLAuthoringArtifact:
    payload = deepcopy(source.model_dump(mode="python", by_alias=True, exclude_unset=True))
    section_payload = payload.get(section)
    if not isinstance(section_payload, dict) or local_key not in section_payload:
        raise ValueError("selected declaration is absent from the explicit source payload")
    del section_payload[local_key]
    module = payload.get("module")
    if isinstance(module, dict):
        exports = module.get("exports")
        if isinstance(exports, dict) and isinstance(exports.get(section), list):
            exports[section] = [name for name in exports[section] if name != local_key]
    candidate = type(source).model_validate(payload)
    validator = SemanticValidator(candidate)
    validator.validate()
    candidate._set_advisories(validator.warnings)
    candidate._set_source_diagnostics(list(source.source_diagnostics))
    candidate._set_semantic_validated(True)
    return candidate


def _successful_removal_result(
    target: SDLAuthoringArtifact,
    request: RemoveSDLDeclarationRequest,
    policy: ArtifactTransformationPolicy,
    source_digest: SDLCanonicalDigest,
) -> SDLTransformationResult:
    target_digest = canonical_sdl_digest(target)
    policy_digest = transformation_policy_digest(policy)
    report = ArtifactTransformationReportModel(
        operation_profile=REMOVE_PROFILE,
        status=ArtifactTransformationStatus.SUCCESS,
        artifact_kind=ArtifactTransformationKind.SDL_AUTHORING,
        source_profile=SDL_CONTRACT_PROFILE,
        target_profile=SDL_CONTRACT_PROFILE,
        canonicalization_profile=source_digest.profile,
        source_digest=source_digest.value,
        target_digest=target_digest.value,
        policy_digest=policy_digest,
        derivation_digest=remove_derivation_digest(
            source_digest=source_digest.value,
            policy_digest=policy_digest,
            request=request,
        ),
        preconditions=tuple(
            check(name, TransformationCheckOutcome.PASSED)
            for name in ("loss-authorized", "source-admitted", "target-exact")
        ),
        postconditions=(check("target-admitted", TransformationCheckOutcome.PASSED),),
        affected_identities=(request.target_address,),
        preservation=ArtifactTransformationPreservationModel(
            profile=EXPLICIT_LOSS_PROFILE,
            outcome=PreservationOutcome.NOT_APPLICABLE,
            evidence_digests=tuple(sorted({source_digest.value, target_digest.value})),
            limitations=("Removal does not preserve the selected declaration.",),
        ),
        losses=(removal_loss(request.target_address, severity=Severity.WARNING),),
    )
    return SDLTransformationResult(output=target, binding_documents=(), report=report)


def remove_sdl_declaration(
    source: SDLAuthoringArtifact,
    request: RemoveSDLDeclarationRequest,
    *,
    policy: ArtifactTransformationPolicy | None = None,
    binding_documents: tuple[ExternalConceptBindingDocumentModel, ...] = (),
) -> SDLTransformationResult:
    """Remove one exact unreferenced declaration under explicit typed loss policy."""

    if not isinstance(source, (Scenario, ExpandedScenario)) or not source.semantic_validated:
        raise SDLParseError("SDL transformation requires a semantically admitted authoring scenario")
    resolved_policy = ArtifactTransformationPolicy() if policy is None else policy
    source_digest = canonical_sdl_digest(source)
    resolved = top_level_declaration(source, build_declaration_index(source), request.target_address)
    if resolved is None:
        result = refused_removal(
            source_digest=source_digest,
            request=request,
            policy=resolved_policy,
            diagnostic_code="artifact-transformation.target-not-exact",
            message="The request target is not an exact supported declaration address.",
        )
    else:
        _, section, local_key = resolved
        if ArtifactTransformationLossKind.DECLARATION_REMOVED not in resolved_policy.allowed_loss_kinds:
            result = refused_removal(
                source_digest=source_digest,
                request=request,
                policy=resolved_policy,
                diagnostic_code="artifact-transformation.loss-not-authorized",
                message="Declaration removal requires explicit authorization of its exact loss kind.",
                passed_checks=("source-admitted", "target-exact"),
                include_loss=True,
            )
        elif binding_documents:
            result = refused_removal(
                source_digest=source_digest,
                request=request,
                policy=resolved_policy,
                diagnostic_code="artifact-transformation.linked-artifact-unsupported",
                message="Declaration removal cannot silently discard or retarget supplied concept bindings.",
                passed_checks=("loss-authorized", "source-admitted", "target-exact"),
                include_loss=True,
            )
        else:
            try:
                target = _removed_candidate(source, section=section, local_key=local_key)
            except SDLValidationError, ValidationError, TypeError, ValueError:
                result = refused_removal(
                    source_digest=source_digest,
                    request=request,
                    policy=resolved_policy,
                    diagnostic_code="artifact-transformation.target-invalid",
                    message="The complete transformed candidate failed structural or semantic admission.",
                    passed_checks=("loss-authorized", "source-admitted", "target-exact"),
                    include_loss=True,
                )
            else:
                result = _successful_removal_result(target, request, resolved_policy, source_digest)
    return result


__all__ = ["remove_sdl_declaration"]
