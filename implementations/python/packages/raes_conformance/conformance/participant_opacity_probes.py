"""Runner-owned backend realization probes for participant predicate opacity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, cast

from raes_backend_protocols.capabilities import ParticipantFeatureSupport, resolve_participant_feature_support
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.behavioral_relation_profiles import load_behavioral_relation_profile
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BehavioralClaimBindingModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.participant_policy_execution import _instrumented_target
from raes_conformance.conformance.report import ConformanceCaseResult

_LOGGER = get_logger(__name__)
_FEATURE = "participant_predicate_opacity"
_RELATION = "participant-predicate-opacity"


class ParticipantOpacityRealizationOwner(StrEnum):
    """Who actually realizes the measured relation for a case."""

    DECLARATION_ONLY = "declaration-only"
    RUNTIME_MEDIATED = "runtime-mediated"
    BACKEND_NATIVE = "backend-native"


@dataclass(frozen=True)
class ParticipantOpacityProbeObservation:
    """Closed, non-secret observation transcript compared by the runner."""

    decision: str
    failure: str
    action_availability: str
    delivery: str
    omission: str
    retry: str
    logical_timing: str
    logical_order: str
    policy_release_effect: str
    external_effect: str
    payload_released: bool


@dataclass(frozen=True)
class ParticipantOpacityProbeCase:
    """Typed backend-specific inputs; no pass boolean or prebuilt report."""

    name: str
    profile_id: str
    profile_revision: str
    profile_digest: str
    actual_point_ref: str
    alternative_point_ref: str
    expected_observation: ParticipantOpacityProbeObservation
    realization_owner: ParticipantOpacityRealizationOwner
    execution_basis: str
    manifest_digest: str
    configuration_digest: str
    tool_digest: str
    environment_digest: str
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    explicit_non_claims: tuple[str, ...]


class ParticipantOpacityProbeHarness(Protocol):
    """Backend setup and observation adapter used by the generic runner."""

    probe_set_digest: str

    def cases(self, target: RuntimeTarget) -> tuple[ParticipantOpacityProbeCase, ...]: ...

    def observe(
        self,
        target: RuntimeTarget,
        case: ParticipantOpacityProbeCase,
        point_ref: str,
    ) -> ParticipantOpacityProbeObservation: ...


@dataclass(frozen=True)
class _ProbeExecution:
    observations: tuple[ParticipantOpacityProbeObservation, ...]
    diagnostics: tuple[Diagnostic, ...]
    backend_calls: int


def _claim(
    *,
    case: ParticipantOpacityProbeCase,
    target: RuntimeTarget,
    axis: str,
    status: str,
    evidence_scope: str,
    evidence_refs: tuple[str, ...],
) -> BehavioralClaimBindingModel:
    profile = load_behavioral_relation_profile(case.profile_id)
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
            quantifier_scope="single-artifact" if evidence_scope == "structural" else "finite-cases",
            evidence_scope=evidence_scope,
            assurance_axis=axis,
            evidence_boundary=(
                "The exact named backend manifest declaration."
                if evidence_scope == "structural"
                else "The exact two finite profile points and complete observation transcript in this case."
            ),
            assurance_status=status,
            evidence_refs=list(evidence_refs),
            limitations=list(case.limitations),
            explicit_non_claims=list(case.explicit_non_claims),
        )
    )


def _declaration_claim(
    case: ParticipantOpacityProbeCase,
    target: RuntimeTarget,
    evidence_refs: tuple[str, ...],
) -> BehavioralClaimBindingModel:
    return _claim(
        case=case,
        target=target,
        axis="backend-declaration",
        status="declared",
        evidence_scope="structural",
        evidence_refs=evidence_refs,
    )


def _unsupported_case(target: RuntimeTarget) -> ConformanceCaseResult:
    profile = load_behavioral_relation_profile("participant-opacity-runtime-reference-v1")
    declaration = next(
        entry
        for entry in target.manifest.participant_runtime.feature_support  # type: ignore[union-attr]
        if entry.feature == _FEATURE
    )
    seed = ParticipantOpacityProbeCase(
        name="participant-opacity-backend-not-executed",
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        actual_point_ref="possible-point:runtime-reference-protected",
        alternative_point_ref="possible-point:runtime-reference-complement",
        expected_observation=ParticipantOpacityProbeObservation("", "", "", "", "", "", "", "", "", "", False),
        realization_owner=ParticipantOpacityRealizationOwner.DECLARATION_ONLY,
        execution_basis="fixture-only",
        manifest_digest="",
        configuration_digest="",
        tool_digest="",
        environment_digest="",
        evidence_refs=declaration.evidence_refs,
        limitations=(*declaration.limitation_refs, "No backend probe was executed."),
        explicit_non_claims=("No backend realization or conformance is established.",),
    )
    return ConformanceCaseResult(
        name=seed.name,
        contract_name="backend-manifest-v2",
        valid=True,
        passed=False,
        outcome="unsupported",
        capability_feature=_FEATURE,
        declared_support_level=declaration.support_level.value,
        effective_support_level=None,
        evidence_refs=declaration.evidence_refs,
        limitations=seed.limitations,
        explicit_non_claims=seed.explicit_non_claims,
        claim_bindings=(_declaration_claim(seed, target, declaration.evidence_refs),),
        realization_owner=seed.realization_owner.value,
        profile_digest=profile.canonical_digest,
        manifest_digest=canonical_json_digest(backend_manifest_payload(target.manifest)),
    )


def _validate_probe_case(
    target: RuntimeTarget,
    case: ParticipantOpacityProbeCase,
    declaration: ParticipantFeatureSupport,
) -> None:
    """Bind a probe case to the governed profile and exact target manifest."""

    profile = load_behavioral_relation_profile(case.profile_id)
    if case.profile_revision != profile.profile_revision or case.profile_digest != profile.canonical_digest:
        raise InvalidInputError("probe profile coordinates do not match the governed profile")
    declared_profile = f"profile:{case.profile_id}@{case.profile_revision}"
    if declared_profile not in declaration.constraint_refs:
        raise InvalidInputError("probe profile is outside the manifest's declared support constraints")
    actual_manifest_digest = canonical_json_digest(backend_manifest_payload(target.manifest))
    if case.manifest_digest != actual_manifest_digest:
        raise InvalidInputError("probe manifest digest does not match the target declaration")
    if case.execution_basis not in {"fixture-only", "hermetic-live", "native-live"}:
        raise InvalidInputError("probe execution basis is unsupported")


def _execute_probe(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness,
    case: ParticipantOpacityProbeCase,
) -> _ProbeExecution:
    """Collect the closed transcript and retain only sanitized failures."""

    instrumented, counter = _instrumented_target(target)
    observations: list[ParticipantOpacityProbeObservation] = []
    diagnostics: list[Diagnostic] = []
    try:
        for point_ref in (case.actual_point_ref, case.alternative_point_ref):
            observations.append(harness.observe(instrumented, case, point_ref))
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Isolation of the harness and the backend runtime: a refusal category needs no record.
            _LOGGER.exception("participant opacity probe observation failed", exc_info=foreign_failure_record(exc))
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-probe-rejected",
                case.name,
                sanitized_failure_message(exc),
            )
        )
    backend_calls = counter.calls if counter is not None else 0
    return _ProbeExecution(tuple(observations), tuple(diagnostics), backend_calls)


def _probe_diagnostics(
    case: ParticipantOpacityProbeCase,
    execution: _ProbeExecution,
    observations_match: bool,
) -> tuple[Diagnostic, ...]:
    """Evaluate mediation, ownership, and transcript consistency."""

    diagnostics = list(execution.diagnostics)
    if execution.backend_calls == 0:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-backend-unobserved",
                case.name,
                "No participant-runtime call was observed; mediation cannot establish backend-native ownership.",
            )
        )
    if case.realization_owner is not ParticipantOpacityRealizationOwner.BACKEND_NATIVE:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-realization-not-backend-native",
                case.name,
                "Runtime mediation or a declaration alone cannot establish backend-native realization.",
            )
        )
    if execution.observations and not observations_match:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-opacity-observation-mismatch",
                case.name,
                "The measured complete observation transcript differs across the governed opacity points.",
            )
        )
    return tuple(diagnostics)


def _case_claims(
    case: ParticipantOpacityProbeCase,
    target: RuntimeTarget,
    declaration: ParticipantFeatureSupport,
    passed: bool,
) -> tuple[BehavioralClaimBindingModel, ...]:
    """Build the declaration-to-realization claim chain for one probe."""

    claims = [_declaration_claim(case, target, declaration.evidence_refs)]
    if passed:
        claims.extend(
            (
                _claim(
                    case=case,
                    target=target,
                    axis="backend-realization",
                    status="realized",
                    evidence_scope="finite",
                    evidence_refs=case.evidence_refs,
                ),
                _claim(
                    case=case,
                    target=target,
                    axis="backend-conformance",
                    status="conformant",
                    evidence_scope="finite",
                    evidence_refs=case.evidence_refs,
                ),
            )
        )
    return tuple(claims)


def _run_case(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness,
    case: ParticipantOpacityProbeCase,
) -> ConformanceCaseResult:
    declaration = resolve_participant_feature_support(
        target.manifest,
        _FEATURE,
        required_level=ParticipantFeatureSupportLevel.BOUNDED,
    )
    assert declaration is not None
    _validate_probe_case(target, case, declaration)
    execution = _execute_probe(target, harness, case)
    observations_match = len(execution.observations) == 2 and all(
        observation == case.expected_observation for observation in execution.observations
    )
    diagnostics = _probe_diagnostics(case, execution, observations_match)
    passed = not diagnostics and observations_match
    return ConformanceCaseResult(
        name=case.name,
        contract_name="backend-manifest-v2",
        valid=True,
        passed=passed,
        outcome="passed" if passed else "failed",
        probe_kind="participant-opacity-complete-transcript",
        probe_digest=canonical_json_digest(
            {
                "case": case.name,
                "observation_count": len(execution.observations),
                "observations_match": observations_match,
                "backend_calls": execution.backend_calls,
            }
        ),
        probe_set_digest=harness.probe_set_digest,
        configuration_digest=case.configuration_digest,
        evidence_refs=case.evidence_refs,
        capability_feature=_FEATURE,
        declared_support_level=declaration.support_level.value,
        effective_support_level=declaration.support_level.value if passed else None,
        finite_scope="The exact two named possible points and closed observation transcript.",
        limitations=case.limitations,
        explicit_non_claims=case.explicit_non_claims,
        diagnostics=diagnostics,
        claim_bindings=_case_claims(case, target, declaration, passed),
        realization_owner=case.realization_owner.value,
        profile_digest=case.profile_digest,
        manifest_digest=case.manifest_digest,
        tool_digest=case.tool_digest,
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
) -> tuple[ConformanceCaseResult, ...]:
    """Convert adapter failures into bounded, non-passing report cases."""

    try:
        probe_cases = harness.cases(target)
        if probe_cases:
            results = tuple(_run_case(target, harness, case) for case in probe_cases)
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
        if not isinstance(exc, RaesError):
            # Isolation of the harness and its cases: a refusal category needs no record.
            _LOGGER.exception("participant opacity harness failed", exc_info=foreign_failure_record(exc))
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
            results = (_unsupported_case(target),) if harness is None else _run_harness_cases(target, harness)
    return results


__all__ = [
    "ParticipantOpacityProbeCase",
    "ParticipantOpacityProbeHarness",
    "ParticipantOpacityProbeObservation",
    "ParticipantOpacityRealizationOwner",
    "participant_opacity_cases",
]
