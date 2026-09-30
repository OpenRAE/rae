"""Production analysis and replay for bounded participant opacity evidence."""

from __future__ import annotations

from itertools import product
from pathlib import Path

from pydantic import ValidationError
from raes_contracts.behavioral_relation_profiles import (
    ActiveOpacityStrategyModel,
    BehavioralRelationProfileModel,
    CoalitionOpacityObserverModel,
    ParticipantPredicateOpacityParametersModel,
    load_behavioral_relation_profile_revision,
)
from raes_contracts.behavioral_relations import (
    validate_behavioral_claim_binding,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import DiagnosticModel
from raes_contracts.json_ingress import (
    parse_bounded_json_object,
)
from raes_contracts.participant_opacity import (
    OpacityPossiblePointModel,
    ParticipantOpacityAnalysisEvidenceModel,
    ParticipantOpacityAnalysisInputModel,
    ParticipantOpacityCheckerConfigurationModel,
    ParticipantOpacityCounterexampleModel,
    ParticipantOpacityOutcome,
    UnsupportedParticipantOpacityAnalysisModel,
    participant_opacity_counterexample_digest,
)

from ._errors import (
    ParticipantOpacityEvidenceError,
    ParticipantOpacityOperationalError,
)
from ._kernel import evaluate_opacity_kernel, information_cell_key

ANALYSIS_PROFILE = "raes-participant-opacity-bounded-test/v1"
_MAX_INPUT_BYTES = 8 * 1024 * 1024
_INCOMPLETE_CODE = "participant-opacity.incomplete-enumeration"
_VACUOUS_CODE = "participant-opacity.vacuous-secret-domain"
_BOUND_CODE = "participant-opacity.analysis-bound-exceeded"


def _diagnostic(code: str, address: str, message: str) -> DiagnosticModel:
    return DiagnosticModel(
        code=code,
        domain="participant-opacity",
        address=address,
        message=message,
        severity="error",
    )


def _checker_configuration() -> ParticipantOpacityCheckerConfigurationModel:
    return ParticipantOpacityCheckerConfigurationModel(
        profile="raes-participant-opacity-checker/v1",
        tool_id="raes-processor-participant-opacity",
        tool_version="1.0.0",
        algorithm="exhaustive-information-cell-scan/v1",
        information_cell_key=("initial-observation-memory-release-coalition-strategy-order/v1"),
        counterexample_selection="lowest-canonical-ordinal/v1",
        max_points=4096,
    )


def _validate_profile_admission(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    if request.analysis_profile != ANALYSIS_PROFILE:
        raise ParticipantOpacityOperationalError("unknown opacity analysis profile")
    if not isinstance(profile.parameters, ParticipantPredicateOpacityParametersModel):
        raise ParticipantOpacityOperationalError("expected an opacity parameter profile")
    if (
        request.profile_id != profile.profile_id
        or request.profile_revision != profile.profile_revision
        or request.profile_digest != profile.canonical_digest
    ):
        raise ParticipantOpacityOperationalError("opacity profile identity does not match the normalized input")
    try:
        validate_behavioral_claim_binding(request.claim, profile=profile)
    except ValueError as exc:
        raise ParticipantOpacityOperationalError("opacity claim does not resolve against the governed profile") from exc


def _validate_profile_domains(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    _validate_declared_bounds(request, profile)
    _validate_scheduler_environment_domain(request, profile)
    _validate_order_and_cut_domains(request, profile)
    _validate_strategy_domain(request, profile)
    _validate_coalition_domain(request, profile)


def _validate_declared_bounds(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    counts = request.declared_counts
    bounds = profile.parameters.bounds
    if (
        counts.points > bounds.max_points
        or counts.runs > bounds.max_runs
        or counts.cuts > bounds.max_cuts
        or counts.strategies > bounds.max_strategies
        or counts.scheduler_environment_pairs > bounds.max_scheduler_environment_pairs
        or counts.order_variants > bounds.max_order_variants
    ):
        raise ParticipantOpacityOperationalError("normalized input exceeds the governed profile bounds")


def _validate_scheduler_environment_domain(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    parameters = profile.parameters
    scheduler_refs = {point.scheduler_ref for point in request.points}
    environment_refs = {point.environment_ref for point in request.points}
    scheduler_environment_pairs = {(point.scheduler_ref, point.environment_ref) for point in request.points}
    expected_scheduler_environment_pairs = set(product(parameters.scheduler_refs, parameters.environment_refs))
    if scheduler_refs != set(parameters.scheduler_refs):
        raise ParticipantOpacityOperationalError("normalized input scheduler domain does not match the profile")
    if environment_refs != set(parameters.environment_refs):
        raise ParticipantOpacityOperationalError("normalized input environment domain does not match the profile")
    if scheduler_environment_pairs != expected_scheduler_environment_pairs:
        raise ParticipantOpacityOperationalError(
            "normalized input scheduler/environment pair domain does not match the profile Cartesian product"
        )


def _validate_order_and_cut_domains(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    parameters = profile.parameters
    order_refs = {point.order_ref for point in request.points}
    cut_refs = {point.cut_ref for point in request.points}
    if order_refs != set(parameters.order.order_refs):
        raise ParticipantOpacityOperationalError("normalized input order domain does not match the profile")
    if cut_refs != {parameters.horizon.cut_ref}:
        raise ParticipantOpacityOperationalError("normalized input cut domain does not match the profile")


def _validate_strategy_domain(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    parameters = profile.parameters
    strategy_refs = {point.strategy_ref for point in request.points}
    if isinstance(parameters.strategy, ActiveOpacityStrategyModel):
        if strategy_refs != set(parameters.strategy.strategy_refs):
            raise ParticipantOpacityOperationalError("normalized input strategy domain does not match the profile")
    elif len(strategy_refs) != 1:
        raise ParticipantOpacityOperationalError("a passive opacity profile requires one fixed strategy")


def _validate_coalition_domain(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    parameters = profile.parameters
    coalition = isinstance(parameters.observer, CoalitionOpacityObserverModel)
    if any((point.coalition_fusion_key is not None) != coalition for point in request.points):
        raise ParticipantOpacityOperationalError("normalized coalition fusion coordinates do not match the profile")


def _common_evidence(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
    checker: ParticipantOpacityCheckerConfigurationModel,
) -> dict[str, object]:
    normalized = request.canonicalized()
    return {
        "schema_version": "participant-opacity-analysis-evidence/v1",
        "analysis_profile": ANALYSIS_PROFILE,
        "provenance_scope": "normalized-input-only",
        "taxonomy_id": normalized.claim.taxonomy_id,
        "taxonomy_revision": normalized.claim.taxonomy_revision,
        "relation_id": normalized.claim.relation_id,
        "profile_id": profile.profile_id,
        "profile_revision": profile.profile_revision,
        "profile_digest": profile.canonical_digest,
        "normalized_model_ref": normalized.normalized_model_ref,
        "normalized_model_digest": normalized.canonical_digest,
        "checker_configuration": checker,
        "checker_configuration_digest": checker.canonical_digest,
        "claim": normalized.claim,
    }


def _unsupported_evidence(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
    checker: ParticipantOpacityCheckerConfigurationModel,
    *,
    outcome: ParticipantOpacityOutcome,
    diagnostic: DiagnosticModel,
    checked_points: int = 0,
    checked_secret_points: int = 0,
) -> ParticipantOpacityAnalysisEvidenceModel:
    return ParticipantOpacityAnalysisEvidenceModel(
        **_common_evidence(request, profile, checker),
        outcome=outcome,
        checked_points=checked_points,
        checked_secret_points=checked_secret_points,
        diagnostics=(diagnostic,),
        unsupported=UnsupportedParticipantOpacityAnalysisModel(
            profile="raes-participant-opacity-unsupported/v1",
            reason_codes=(diagnostic.code,),
        ),
    )


def _information_cell_key(
    point: OpacityPossiblePointModel,
) -> tuple[str, str, str, str, str | None, str, str]:
    """Derive the complete admitted observer cell; callers provide no cell id."""

    return information_cell_key(point)


def analyze_participant_opacity_input(
    request: ParticipantOpacityAnalysisInputModel,
    *,
    profile: BehavioralRelationProfileModel,
) -> ParticipantOpacityAnalysisEvidenceModel:
    """Exhaustively falsify one admitted complete finite possible-point carrier."""

    _validate_profile_admission(request, profile)
    _validate_profile_domains(request, profile)
    checker = _checker_configuration()
    precondition_evidence = _analysis_precondition_evidence(request, profile, checker)
    if precondition_evidence is not None:
        return precondition_evidence

    reachable = tuple(
        sorted(
            (point for point in request.points if point.reachable),
            key=lambda point: point.ordinal,
        )
    )
    secret_points = tuple(point for point in reachable if point.secret_holds)
    if not secret_points:
        return _unsupported_evidence(
            request,
            profile,
            checker,
            outcome=ParticipantOpacityOutcome.VACUOUS,
            diagnostic=_diagnostic(
                _VACUOUS_CODE,
                "/points",
                "The reachable carrier contains no protected secret point.",
            ),
            checked_points=len(reachable),
        )

    return _analyze_nonvacuous_carrier(
        request,
        profile,
        checker,
        reachable=reachable,
    )


def _analysis_precondition_evidence(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
    checker: ParticipantOpacityCheckerConfigurationModel,
) -> ParticipantOpacityAnalysisEvidenceModel | None:
    if not request.complete_enumeration:
        return _unsupported_evidence(
            request,
            profile,
            checker,
            outcome=ParticipantOpacityOutcome.UNSUPPORTED,
            diagnostic=_diagnostic(
                _INCOMPLETE_CODE,
                "/complete_enumeration",
                "The declared finite carrier is not complete.",
            ),
        )
    if len(request.points) > checker.max_points:
        return _unsupported_evidence(
            request,
            profile,
            checker,
            outcome=ParticipantOpacityOutcome.UNSUPPORTED,
            diagnostic=_diagnostic(
                _BOUND_CODE,
                "/points",
                "The declared finite carrier exceeds the deterministic checker bound.",
            ),
        )
    return None


def _analyze_nonvacuous_carrier(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
    checker: ParticipantOpacityCheckerConfigurationModel,
    *,
    reachable: tuple[OpacityPossiblePointModel, ...],
) -> ParticipantOpacityAnalysisEvidenceModel:
    result = evaluate_opacity_kernel(reachable, cell_key=_information_cell_key)
    normalized_model_digest = request.canonical_digest
    counterexample: ParticipantOpacityCounterexampleModel | None = None
    if result.counterexample_actual_ordinal is not None:
        assert result.counterexample_cell_size is not None
        safe_ref = f"participant-opacity-counterexample:{result.counterexample_actual_ordinal:06d}"
        counterexample = ParticipantOpacityCounterexampleModel(
            safe_ref=safe_ref,
            counterexample_digest=participant_opacity_counterexample_digest(
                safe_ref=safe_ref,
                actual_point_ordinal=result.counterexample_actual_ordinal,
                examined_cell_size=result.counterexample_cell_size,
                normalized_model_digest=normalized_model_digest,
            ),
            actual_point_ordinal=result.counterexample_actual_ordinal,
            examined_cell_size=result.counterexample_cell_size,
        )

    if counterexample is not None:
        return ParticipantOpacityAnalysisEvidenceModel(
            **_common_evidence(request, profile, checker),
            outcome=ParticipantOpacityOutcome.COUNTEREXAMPLE,
            checked_points=result.checked_points,
            checked_secret_points=result.checked_secret_points,
            diagnostics=(),
            counterexample=counterexample,
        )

    return ParticipantOpacityAnalysisEvidenceModel(
        **_common_evidence(request, profile, checker),
        outcome=ParticipantOpacityOutcome.NO_COUNTEREXAMPLE,
        checked_points=result.checked_points,
        checked_secret_points=result.checked_secret_points,
        diagnostics=(),
    )


def analyze_participant_opacity_file(
    path: Path,
) -> ParticipantOpacityAnalysisEvidenceModel:
    """Analyze one bounded strict-JSON normalized finite carrier."""

    try:
        payload = parse_bounded_json_object(
            path.read_bytes(),
            max_bytes=_MAX_INPUT_BYTES,
        )
        request = ParticipantOpacityAnalysisInputModel.model_validate(payload)
        profile = load_behavioral_relation_profile_revision(
            request.profile_id,
            request.profile_revision,
        )
    except (OSError, ValidationError, ValueError):
        raise ParticipantOpacityOperationalError(
            "opacity analysis input failed bounded closed-world admission"
        ) from None
    return analyze_participant_opacity_input(request, profile=profile)


def replay_participant_opacity_evidence(
    request: ParticipantOpacityAnalysisInputModel,
    profile: BehavioralRelationProfileModel,
    evidence: ParticipantOpacityAnalysisEvidenceModel,
) -> ParticipantOpacityAnalysisEvidenceModel:
    """Recompute and compare every profile/model/checker/result evidence join."""

    replayed = analyze_participant_opacity_input(request, profile=profile)
    if canonical_json_digest(replayed.model_dump(mode="json")) != canonical_json_digest(
        evidence.model_dump(mode="json")
    ):
        raise ParticipantOpacityEvidenceError("participant opacity evidence replay did not reproduce")
    return replayed
