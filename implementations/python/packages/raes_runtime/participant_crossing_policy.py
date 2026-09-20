"""RUN-319 caller, capability, and deny-first policy gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from raes_backend_protocols.capability_admission import resolve_participant_feature_support
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingBackendPosture,
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDecisionGatesModel,
    ParticipantCrossingDirection,
    ParticipantCrossingGateDisposition,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingOperation,
)
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .participant_crossing_mediation import (
    ParticipantCrossingIntent,
    ParticipantCrossingPolicyResolution,
    ParticipantCrossingSemanticGates,
)


@dataclass(frozen=True)
class _BackendSupport:
    gate: ParticipantCrossingGateDisposition
    posture: ParticipantCrossingBackendPosture
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    effective_levels: tuple[tuple[str, str], ...] = ()


def _resolve_backend_support(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    resolution: ParticipantCrossingPolicyResolution,
) -> _BackendSupport:
    if getattr(control_plane, "_mixed_runtime", None) is not None:
        from .mixed_runtime_dispatch import mixed_policy_allocation

        allocation = mixed_policy_allocation(control_plane, intent)
        if allocation is None:
            return _BackendSupport(
                gate=ParticipantCrossingGateDisposition.UNSUPPORTED,
                posture=ParticipantCrossingBackendPosture.UNSUPPORTED,
                limitations=("limitation:mixed-provider-unresolved",),
            )
        requirements = {requirement.feature: requirement for requirement in allocation.feature_requirements}
        levels = []
        limitations = []
        evidence_refs = []
        for feature in _required_features(intent):
            requirement = requirements.get(feature)
            if requirement is None:
                return _BackendSupport(
                    gate=ParticipantCrossingGateDisposition.UNSUPPORTED,
                    posture=ParticipantCrossingBackendPosture.UNSUPPORTED,
                    limitations=(f"limitation:{feature}:unsupported",),
                    effective_levels=((feature, ParticipantFeatureSupportLevel.UNSUPPORTED.value),),
                )
            level = requirement.allowed_downgrade_level or requirement.required_level
            levels.append((feature, level.value))
            if requirement.allowed_downgrade_level is not None:
                limitations.append(f"limitation:{feature}:admitted-downgrade")
                evidence_refs.append(requirement.downgrade_provenance_ref)
        weakest = min((ParticipantFeatureSupportLevel(level) for _, level in levels), key=_support_rank)
        posture = {
            ParticipantFeatureSupportLevel.EXACT: ParticipantCrossingBackendPosture.EXACT,
            ParticipantFeatureSupportLevel.BOUNDED: ParticipantCrossingBackendPosture.BOUNDED,
            ParticipantFeatureSupportLevel.DISCLOSED_WEAK: ParticipantCrossingBackendPosture.DISCLOSED_WEAK,
            ParticipantFeatureSupportLevel.UNSUPPORTED: ParticipantCrossingBackendPosture.UNSUPPORTED,
        }[weakest]
        return _BackendSupport(
            gate=(
                ParticipantCrossingGateDisposition.PERMIT
                if weakest is not ParticipantFeatureSupportLevel.UNSUPPORTED
                else ParticipantCrossingGateDisposition.UNSUPPORTED
            ),
            posture=posture,
            evidence_refs=tuple(ref for ref in evidence_refs if ref is not None),
            limitations=tuple(limitations),
            effective_levels=tuple(levels),
        )
    declarations = []
    for feature in _required_features(intent):
        try:
            declaration = resolve_participant_feature_support(
                control_plane._target.manifest,
                feature,
                required_level=resolution.required_support_level,
                allowed_downgrade_level=resolution.allowed_downgrades.get(feature),
                downgrade_policy_ref=resolution.downgrade_policy_ref,
                downgrade_provenance_ref=resolution.downgrade_provenance_ref,
            )
        except ValueError:
            return _BackendSupport(
                gate=ParticipantCrossingGateDisposition.UNSUPPORTED,
                posture=ParticipantCrossingBackendPosture.UNSUPPORTED,
                limitations=(f"limitation:{feature}:unsupported",),
                effective_levels=((feature, ParticipantFeatureSupportLevel.UNSUPPORTED.value),),
            )
        if declaration is not None:
            declarations.append(declaration)
    if not declarations:
        return _BackendSupport(
            gate=ParticipantCrossingGateDisposition.UNSUPPORTED,
            posture=ParticipantCrossingBackendPosture.UNSUPPORTED,
            limitations=("limitation:participant-policy-support-unresolved",),
        )
    weakest = min(
        (declaration.support_level for declaration in declarations),
        key=_support_rank,
    )
    posture = {
        ParticipantFeatureSupportLevel.EXACT: ParticipantCrossingBackendPosture.EXACT,
        ParticipantFeatureSupportLevel.BOUNDED: ParticipantCrossingBackendPosture.BOUNDED,
        ParticipantFeatureSupportLevel.DISCLOSED_WEAK: ParticipantCrossingBackendPosture.DISCLOSED_WEAK,
        ParticipantFeatureSupportLevel.UNSUPPORTED: ParticipantCrossingBackendPosture.UNSUPPORTED,
    }[weakest]
    return _BackendSupport(
        gate=(
            ParticipantCrossingGateDisposition.PERMIT
            if weakest is not ParticipantFeatureSupportLevel.UNSUPPORTED
            else ParticipantCrossingGateDisposition.UNSUPPORTED
        ),
        posture=posture,
        evidence_refs=tuple(dict.fromkeys(ref for item in declarations for ref in item.evidence_refs)),
        limitations=tuple(
            dict.fromkeys(
                ref
                for item in declarations
                for ref in (*item.constraint_refs, *item.limitation_refs, *item.disclosure_refs)
            )
        ),
        effective_levels=tuple((item.feature, item.support_level.value) for item in declarations),
    )


def _support_rank(level: ParticipantFeatureSupportLevel) -> int:
    return {
        ParticipantFeatureSupportLevel.UNSUPPORTED: 0,
        ParticipantFeatureSupportLevel.DISCLOSED_WEAK: 1,
        ParticipantFeatureSupportLevel.BOUNDED: 2,
        ParticipantFeatureSupportLevel.EXACT: 3,
    }[level]


def _required_features(intent: ParticipantCrossingIntent) -> tuple[str, ...]:
    features: list[str] = []
    if intent.direction is ParticipantCrossingDirection.INGRESS:
        features.append("participant_ingress_admission")
    else:
        features.append("participant_egress_projection")
    if intent.interaction_kind in {
        ParticipantCrossingInteractionKind.INTERVENTION,
        ParticipantCrossingInteractionKind.HANDOFF,
    }:
        features.append("participant_intervention")
    if intent.interaction_kind is ParticipantCrossingInteractionKind.PARTICIPANT_INJECT_DELIVERY:
        features.append("participant_directed_inject_delivery")
    if intent.requested_operation is ParticipantCrossingOperation.DECLASSIFICATION:
        features.append("participant_declassification")
    if intent.requested_operation in {
        ParticipantCrossingOperation.PROJECTION,
        ParticipantCrossingOperation.MASKING,
        ParticipantCrossingOperation.REDACTION,
        ParticipantCrossingOperation.TRANSFORMATION,
    }:
        features.append("participant_transformation")
    return tuple(dict.fromkeys(features))


def _require_crossing_identity(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: object,
) -> ControlPlaneIdentity:
    if not isinstance(identity, ControlPlaneIdentity):
        _record_identity_denial(control_plane, intent, "authentication-required")
        raise PermissionError("participant crossing requires an authenticated identity")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        _record_identity_denial(
            control_plane,
            intent,
            "target-forbidden",
            identity=identity.identity,
        )
        raise PermissionError("participant crossing identity is not authorized for this target")
    _require_crossing_role(control_plane, intent, identity)
    _require_crossing_subject_binding(control_plane, intent, identity)
    return identity


def _require_crossing_role(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
) -> None:
    allowed_roles = {
        ControlPlaneRole.BACKEND,
        ControlPlaneRole.OPERATOR,
    }
    if intent.direction is ParticipantCrossingDirection.EGRESS:
        allowed_roles.add(ControlPlaneRole.AUDITOR)
    if identity.roles.isdisjoint(allowed_roles):
        _record_identity_denial(
            control_plane,
            intent,
            "caller-forbidden",
            identity=identity.identity,
        )
        raise PermissionError("participant crossing identity is not authorized for this operation")


def _require_crossing_subject_binding(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    identity: ControlPlaneIdentity,
) -> None:
    if intent.direction is ParticipantCrossingDirection.INGRESS:
        bound = any(
            binding.participant_address == intent.participant_address
            and binding.controller_ref == intent.controller_ref
            for binding in identity.participant_control_subjects
        )
        if not bound:
            _record_identity_denial(
                control_plane,
                intent,
                "subject-forbidden",
                identity=identity.identity,
            )
            raise PermissionError("participant crossing identity is not authorized for this subject")
    else:
        bound = any(
            binding.participant_address == intent.participant_address
            and binding.audience_scope_ref == intent.audience_scope_ref
            for binding in identity.participant_audience_subjects
        )
        if not bound:
            _record_identity_denial(
                control_plane,
                intent,
                "audience-forbidden",
                identity=identity.identity,
            )
            raise PermissionError("participant crossing identity is not authorized for this audience")


def _record_identity_denial(
    control_plane: object,
    intent: ParticipantCrossingIntent,
    reason: str,
    *,
    identity: str = "anonymous",
) -> None:
    control_plane.record_audit(
        action="record_participant_crossing",
        identity=identity,
        allowed=False,
        target=intent.participant_address,
        reason=reason,
    )


def _decision_gates(
    semantic: ParticipantCrossingSemanticGates,
    backend_support: ParticipantCrossingGateDisposition,
) -> ParticipantCrossingDecisionGatesModel:
    return ParticipantCrossingDecisionGatesModel(
        caller_authorization=ParticipantCrossingGateDisposition.PERMIT,
        target_authorization=ParticipantCrossingGateDisposition.PERMIT,
        participant_authority=semantic.participant_authority,
        action_admission=semantic.action_admission,
        visibility=semantic.visibility,
        marking_authorization=semantic.marking_authorization,
        declassification=semantic.declassification,
        backend_support=backend_support,
        transformation_validity=semantic.transformation_validity,
    )


def _applicable_semantic_gates(
    intent: ParticipantCrossingIntent,
    resolution: ParticipantCrossingPolicyResolution,
) -> ParticipantCrossingSemanticGates:
    values = asdict(resolution.gates)

    def require(name: str) -> None:
        if values[name] is ParticipantCrossingGateDisposition.NOT_APPLICABLE:
            values[name] = ParticipantCrossingGateDisposition.UNKNOWN

    require("participant_authority")
    require("marking_authorization")
    if intent.direction is ParticipantCrossingDirection.INGRESS:
        require("action_admission")
    else:
        require("visibility")
    if intent.requested_operation is ParticipantCrossingOperation.DECLASSIFICATION:
        require("declassification")
    if intent.requested_operation in {
        ParticipantCrossingOperation.PROJECTION,
        ParticipantCrossingOperation.MASKING,
        ParticipantCrossingOperation.REDACTION,
        ParticipantCrossingOperation.TRANSFORMATION,
        ParticipantCrossingOperation.DECLASSIFICATION,
    }:
        require("transformation_validity")
    if resolution.required_operation is not None and resolution.transformation is None:
        values["transformation_validity"] = ParticipantCrossingGateDisposition.UNKNOWN
    return ParticipantCrossingSemanticGates(**values)


def _decision_disposition(
    gates: ParticipantCrossingDecisionGatesModel,
    resolution: ParticipantCrossingPolicyResolution,
) -> ParticipantCrossingDecisionDisposition:
    values = set(gates.dispositions())
    if ParticipantCrossingGateDisposition.DENY in values:
        disposition = ParticipantCrossingDecisionDisposition.DENY
    elif values & {
        ParticipantCrossingGateDisposition.UNKNOWN,
        ParticipantCrossingGateDisposition.UNSUPPORTED,
    }:
        disposition = ParticipantCrossingDecisionDisposition.UNSUPPORTED
    elif resolution.required_operation is not None:
        disposition = ParticipantCrossingDecisionDisposition.TRANSFORM
    else:
        disposition = ParticipantCrossingDecisionDisposition.PERMIT
    return disposition


__all__ = (
    "_BackendSupport",
    "_applicable_semantic_gates",
    "_decision_disposition",
    "_decision_gates",
    "_require_crossing_identity",
    "_resolve_backend_support",
)
