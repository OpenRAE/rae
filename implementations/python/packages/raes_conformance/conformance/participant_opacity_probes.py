"""Runner-owned realization probes for participant predicate opacity.

**The runner owns execution, the transcript, and the verdict.** A harness
supplies the exact profile coordinates, one exact-cut crossing policy resolver
per possible point, the typed carriers, the transcript the backend reports, and
a backend state commitment. The runner executes both points on the target under
evaluation, derives the closed transcript from committed runtime facts and the
backend readback, and compares it across points, against the runner-owned
profile normal form, and against the reported transcript. A reported or
finite-model transcript that execution does not corroborate is synthetic
evidence, never realization evidence.

Realization ownership is derived from the committed runtime bindings. Under the
published runtime profile RUN-319 produces the normal form before any protected
backend effect, so a passing case is runtime-mediated and carries only the
backend-declaration claim.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import cast

from raes_backend_protocols.capabilities import ParticipantFeatureSupport, resolve_participant_feature_support
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.behavioral_relation_profiles import load_behavioral_relation_profile
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BehavioralClaimBindingModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.participant_opacity_execution import (
    _PointMeasurement,
    configuration_digest,
    measure_point,
    tool_digest,
)
from raes_conformance.conformance.participant_opacity_projection import (
    NORMAL_FORMS,
    MeasuredObservation,
    derive_realization_owner,
    disagreeing_fields,
    missing_fields,
    project_observation,
    visible_projection,
)
from raes_conformance.conformance.participant_opacity_types import (
    ParticipantOpacityBackendReadback,
    ParticipantOpacityEvidenceOrigin,
    ParticipantOpacityProbeCase,
    ParticipantOpacityProbeHarness,
    ParticipantOpacityProbeObservation,
    ParticipantOpacityProbePoint,
    ParticipantOpacityReadbackRequest,
    ParticipantOpacityRealizationOwner,
)
from raes_conformance.conformance.report import ConformanceCaseResult
from raes_conformance.realization import ExecutionBasis

_FEATURE = "participant_predicate_opacity"
_RELATION = "participant-predicate-opacity"
_REFERENCE_PROFILE = "participant-opacity-runtime-reference-v1"
_PROBE_KIND = "participant-opacity-observed-transcript"
_FINITE_SCOPE = (
    "The exact two named possible points and the closed observation transcript measured from action "
    "ingress, exact replay, and the participant status-view delivery opportunity in the runtime's "
    "single-writer logical order."
)
_STANDING_LIMITATIONS = (
    "Supervisor-control, decision-surface selection, and autonomous-scheduler surfaces were not exercised.",
    "Runtime mediation shields backend mechanisms; no backend-native realization is derived for this profile.",
)
_FINAL_SINK_DISABLED = "Final-sink flow-control enforcement was disabled for this case."


def _declaration_claim(
    target: RuntimeTarget,
    profile_id: str,
    evidence_refs: tuple[str, ...],
    limitations: tuple[str, ...],
    explicit_non_claims: tuple[str, ...],
) -> BehavioralClaimBindingModel:
    profile = load_behavioral_relation_profile(profile_id)
    return validate_behavioral_claim_binding(
        BehavioralClaimBindingModel(
            taxonomy_id=profile.taxonomy_id,
            taxonomy_revision=profile.taxonomy_revision,
            relation_id=_RELATION,
            subject=f"Participant predicate opacity for backend target {target.name}",
            left_carrier_ref=profile.left_carrier_ref,
            observation_projection_ref=profile.observation_projection_ref,
            observation_projection_revision=profile.observation_projection_revision,
            relation_parameter_profile_ref=profile.profile_id,
            relation_parameter_profile_revision=profile.profile_revision,
            quantifier_scope="single-artifact",
            evidence_scope="structural",
            assurance_axis="backend-declaration",
            evidence_boundary="The exact named backend manifest declaration.",
            assurance_status="declared",
            evidence_refs=list(evidence_refs),
            limitations=list(limitations),
            explicit_non_claims=list(explicit_non_claims),
        )
    )


def _declaration(target: RuntimeTarget) -> ParticipantFeatureSupport:
    return next(
        entry
        for entry in target.manifest.participant_runtime.feature_support  # type: ignore[union-attr]
        if entry.feature == _FEATURE
    )


def _unsupported_case(target: RuntimeTarget) -> ConformanceCaseResult:
    profile = load_behavioral_relation_profile(_REFERENCE_PROFILE)
    declaration = _declaration(target)
    limitations = (*declaration.limitation_refs, "No backend probe was executed.")
    non_claims = ("No backend realization or conformance is established.",)
    return ConformanceCaseResult(
        name="participant-opacity-backend-not-executed",
        contract_name="backend-manifest-v2",
        valid=True,
        passed=False,
        outcome="unsupported",
        capability_feature=_FEATURE,
        declared_support_level=declaration.support_level.value,
        effective_support_level=None,
        evidence_refs=declaration.evidence_refs,
        limitations=limitations,
        explicit_non_claims=non_claims,
        claim_bindings=(
            _declaration_claim(target, profile.profile_id, declaration.evidence_refs, limitations, non_claims),
        ),
        realization_owner=ParticipantOpacityRealizationOwner.DECLARATION_ONLY.value,
        evidence_origin=ParticipantOpacityEvidenceOrigin.DECLARATION.value,
        profile_digest=profile.canonical_digest,
        manifest_digest=canonical_json_digest(backend_manifest_payload(target.manifest)),
    )


def _validate_probe_case(
    case: ParticipantOpacityProbeCase,
    declaration: ParticipantFeatureSupport,
) -> None:
    """Bind a probe case to the governed profile, declaration, and runner-owned normal form."""

    profile = load_behavioral_relation_profile(case.profile_id)
    if case.profile_revision != profile.profile_revision or case.profile_digest != profile.canonical_digest:
        raise ValueError("probe profile coordinates do not match the governed profile")
    if f"profile:{case.profile_id}@{case.profile_revision}" not in declaration.constraint_refs:
        raise ValueError("probe profile is outside the manifest's declared support constraints")
    if (case.profile_id, case.profile_revision) not in NORMAL_FORMS:
        raise ValueError("probe profile has no runner-owned observation normal form")


def _failed_measurement(point: ParticipantOpacityProbePoint, exc: Exception) -> _PointMeasurement:
    return _PointMeasurement(
        point_ref=point.point_ref,
        ingress=None,
        replay=None,
        egress=None,
        readback_before=None,
        readback_after=None,
        history_valid=False,
        opacity_supports=(),
        failures=(f"execution: {sanitized_failure_message(exc)}",),
    )


def _reported(
    harness: ParticipantOpacityProbeHarness,
    target: RuntimeTarget,
    case: ParticipantOpacityProbeCase,
    point: ParticipantOpacityProbePoint,
) -> tuple[ParticipantOpacityProbeObservation | None, str | None]:
    try:
        reported = harness.reported_observation(target, case, point.point_ref)
        if not isinstance(reported, ParticipantOpacityProbeObservation):
            raise TypeError("reported transcript must be a ParticipantOpacityProbeObservation")
    except Exception as exc:
        return None, f"reported transcript: {sanitized_failure_message(exc)}"
    return reported, None


def _execute(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness,
    case: ParticipantOpacityProbeCase,
) -> tuple[list[_PointMeasurement], list[ParticipantOpacityProbeObservation | None], list[str]]:
    """Measure each point in its own control plane, then collect what the backend reports."""

    measurements: list[_PointMeasurement] = []
    reported: list[ParticipantOpacityProbeObservation | None] = []
    failures: list[str] = []
    for point in case.points:
        try:
            measurement = measure_point(target, harness, case, point)
        except Exception as exc:
            measurement = _failed_measurement(point, exc)
        measurements.append(measurement)
        failures.extend(measurement.failures)
        transcript, failure = _reported(harness, target, case, point)
        reported.append(transcript)
        if failure is not None:
            failures.append(failure)
    return measurements, reported, failures


def _comparison_diagnostics(
    case: ParticipantOpacityProbeCase,
    measurements: list[_PointMeasurement],
    observations: list[MeasuredObservation],
    reported: list[ParticipantOpacityProbeObservation | None],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    disagreement = sorted(
        {
            name
            for observation, transcript in zip(observations, reported, strict=True)
            if transcript is not None
            for name in disagreeing_fields(observation, transcript)
        }
    )
    if disagreement:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-transcript-disagreement",
                case.name,
                "The reported transcript disagrees with instrumented execution for: " + ", ".join(disagreement) + ".",
            )
        )
    if missing_fields(observations):
        # Missing evidence is reported once by the caller; comparing absent
        # fields would only restate it.
        return diagnostics
    if observations[0] != observations[1] or visible_projection(measurements[0]) != visible_projection(measurements[1]):
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-observation-mismatch",
                case.name,
                "The measured participant observation differs across the governed opacity points.",
            )
        )
    normal_form = asdict(NORMAL_FORMS[(case.profile_id, case.profile_revision)])
    if any(observation != normal_form for observation in observations):
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-normal-form-mismatch",
                case.name,
                "The measured transcript differs from the profile's runner-owned normal form.",
            )
        )
    return diagnostics


def _case_diagnostics(
    case: ParticipantOpacityProbeCase,
    measurements: list[_PointMeasurement],
    observations: list[MeasuredObservation],
    reported: list[ParticipantOpacityProbeObservation | None],
    failures: list[str],
    owner: ParticipantOpacityRealizationOwner,
) -> tuple[Diagnostic, ...]:
    diagnostics = [_diagnostic("conformance.participant-opacity-probe-rejected", case.name, item) for item in failures]
    missing = missing_fields(observations)
    if missing:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-observation-missing",
                case.name,
                "Execution produced no measured basis for: " + ", ".join(missing) + ".",
            )
        )
    diagnostics.extend(_comparison_diagnostics(case, measurements, observations, reported))
    if owner is ParticipantOpacityRealizationOwner.DECLARATION_ONLY:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-realization-unestablished",
                case.name,
                "No committed runtime-enforcement binding for the case profile and points established realization.",
            )
        )
    return tuple(diagnostics)


def _run_case(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness,
    case: ParticipantOpacityProbeCase,
    execution_basis: ExecutionBasis,
) -> ConformanceCaseResult:
    declaration = resolve_participant_feature_support(
        target.manifest,
        _FEATURE,
        required_level=ParticipantFeatureSupportLevel.BOUNDED,
    )
    assert declaration is not None
    _validate_probe_case(case, declaration)
    measurements, reported, failures = _execute(target, harness, case)
    observations = [project_observation(measurement) for measurement in measurements]
    owner = derive_realization_owner(case, measurements)
    diagnostics = _case_diagnostics(case, measurements, observations, reported, failures, owner)
    passed = not diagnostics
    complete = not any(item.failures for item in measurements) and not missing_fields(observations)
    limitations = (
        *case.limitations,
        *_STANDING_LIMITATIONS,
        *(() if case.enforce_final_sink_flow_control else (_FINAL_SINK_DISABLED,)),
    )
    manifest_digest = canonical_json_digest(backend_manifest_payload(target.manifest))
    return ConformanceCaseResult(
        name=case.name,
        contract_name="backend-manifest-v2",
        valid=True,
        passed=passed,
        outcome="passed" if passed else "failed",
        execution_basis=execution_basis.value,
        probe_kind=_PROBE_KIND,
        probe_digest=canonical_json_digest(
            {
                "case": case.name,
                "measured": observations,
                "reported": [None if item is None else asdict(item) for item in reported],
                "backend_calls": [
                    [len(facts.backend_calls) if facts is not None else None for facts in operations]
                    for operations in ((m.ingress, m.replay, m.egress) for m in measurements)
                ],
                "realization_owner": owner.value,
            }
        ),
        probe_set_digest=harness.probe_set_digest,
        configuration_digest=configuration_digest(target, case, manifest_digest, measurements),
        evidence_refs=case.evidence_refs,
        capability_feature=_FEATURE,
        declared_support_level=declaration.support_level.value,
        effective_support_level=declaration.support_level.value if passed else None,
        finite_scope=_FINITE_SCOPE,
        limitations=limitations,
        explicit_non_claims=case.explicit_non_claims,
        diagnostics=diagnostics,
        claim_bindings=(
            _declaration_claim(
                target, case.profile_id, declaration.evidence_refs, limitations, case.explicit_non_claims
            ),
        ),
        realization_owner=owner.value,
        evidence_origin=(
            ParticipantOpacityEvidenceOrigin.OBSERVED_EXECUTION
            if complete
            else ParticipantOpacityEvidenceOrigin.SYNTHETIC_MODEL
        ).value,
        profile_digest=case.profile_digest,
        manifest_digest=manifest_digest,
        tool_digest=tool_digest(),
        environment_digest=case.environment_digest,
    )


def _harness_failure_case(
    target: RuntimeTarget,
    code: str,
    message: str,
    *,
    outcome: str,
) -> ConformanceCaseResult:
    """Retain the positive declaration while refusing absent probe evidence."""

    case = _unsupported_case(target)
    return cast(
        ConformanceCaseResult,
        replace(
            case,
            diagnostics=(_diagnostic(code, _FEATURE, message),),
            outcome=outcome,
        ),
    )


def _run_harness_cases(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness,
    execution_basis: ExecutionBasis,
) -> tuple[ConformanceCaseResult, ...]:
    """Convert adapter failures into bounded, non-passing report cases."""

    try:
        probe_cases = harness.cases(target)
        if probe_cases:
            results = tuple(_run_case(target, harness, case, execution_basis) for case in probe_cases)
        else:
            results = (
                _harness_failure_case(
                    target,
                    "conformance.participant-opacity-harness-empty",
                    "The opacity harness supplied no cases for a positive declaration.",
                    outcome="unsupported",
                ),
            )
    except Exception as exc:
        results = (
            _harness_failure_case(
                target,
                "conformance.participant-opacity-harness-rejected",
                sanitized_failure_message(exc),
                outcome="failed",
            ),
        )
    return results


def participant_opacity_cases(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness | None,
    execution_basis: ExecutionBasis = ExecutionBasis.HERMETIC_LIVE,
) -> tuple[ConformanceCaseResult, ...]:
    """Run backend opacity probes or retain an explicit unsupported result."""

    capability = target.manifest.participant_runtime
    results: tuple[ConformanceCaseResult, ...] = ()
    if capability is not None:
        declaration = next((entry for entry in capability.feature_support if entry.feature == _FEATURE), None)
        supported = (
            declaration is not None and declaration.support_level is not ParticipantFeatureSupportLevel.UNSUPPORTED
        )
        if supported:
            results = (
                (_unsupported_case(target),)
                if harness is None
                else _run_harness_cases(target, harness, execution_basis)
            )
    return results


__all__ = [
    "ParticipantOpacityBackendReadback",
    "ParticipantOpacityEvidenceOrigin",
    "ParticipantOpacityProbeCase",
    "ParticipantOpacityProbeHarness",
    "ParticipantOpacityProbeObservation",
    "ParticipantOpacityProbePoint",
    "ParticipantOpacityReadbackRequest",
    "ParticipantOpacityRealizationOwner",
    "participant_opacity_cases",
]
