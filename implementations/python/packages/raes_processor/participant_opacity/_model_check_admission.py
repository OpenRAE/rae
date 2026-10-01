"""Admission and capability checks for participant-opacity transition models."""

from __future__ import annotations

from importlib.metadata import version
from itertools import product

from raes_contracts.behavioral_relation_profiles import (
    ActiveOpacityStrategyModel,
    BehavioralRelationProfileModel,
    CoalitionOpacityObserverModel,
    ParticipantPredicateOpacityParametersModel,
)
from raes_contracts.behavioral_relations import (
    BehavioralRelationCatalogModel,
    validate_behavioral_claim_binding,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import DiagnosticModel
from raes_contracts.participant_opacity import (
    ParticipantOpacityModelAssumptionsModel,
    ParticipantOpacityModelCheckConfigurationModel,
    ParticipantOpacityModelCheckInputModel,
)

from ._errors import ParticipantOpacityOperationalError

ANALYSIS_PROFILE = "raes-participant-opacity-model-check/v1"
_INCOMPLETE_CODE = "participant-opacity-model-check.incomplete-model"
_BOUND_CODE = "participant-opacity-model-check.bound-exceeded"
_SCHEDULER_CODE = "participant-opacity-model-check.unsupported-scheduler-quantification"
_ORDER_CODE = "participant-opacity-model-check.unsupported-order-treatment"
VACUOUS_CODE = "participant-opacity-model-check.vacuous-secret-domain"


def diagnostic(code: str, address: str, message: str) -> DiagnosticModel:
    return DiagnosticModel(
        code=code,
        domain="participant-opacity-model-check",
        address=address,
        message=message,
        severity="error",
    )


def checker_configuration() -> ParticipantOpacityModelCheckConfigurationModel:
    try:
        return ParticipantOpacityModelCheckConfigurationModel(
            profile="raes-participant-opacity-explicit-state/v1",
            tool_id="raes-processor-participant-opacity-model-check",
            tool_version="1.0.0",
            package="raes",
            package_version=version("raes"),
            algorithm="complete-finite-transition-fixed-point/v1",
            traversal="breadth-first-canonical/v1",
            opacity_kernel="participant-opacity-information-cell-kernel/v1",
            information_cell_key="initial-observation-memory-release-coalition-strategy-order/v1",
            counterexample_selection="lowest-state-ordinal-canonical-shortest-path/v1",
            max_states=4096,
            max_transitions=65536,
        )
    except ValueError as exc:
        raise ParticipantOpacityOperationalError(
            "the installed participant-opacity model checker does not match its governed profile"
        ) from exc


def _catalog_digest(catalog: BehavioralRelationCatalogModel) -> str:
    return canonical_json_digest(catalog.model_dump(mode="json"))


def _expected_assumptions(
    request: ParticipantOpacityModelCheckInputModel,
    profile: BehavioralRelationProfileModel,
) -> ParticipantOpacityModelAssumptionsModel:
    parameters = profile.parameters
    if isinstance(parameters.strategy, ActiveOpacityStrategyModel):
        strategy_refs = parameters.strategy.strategy_refs
    else:
        if len(request.assumptions.strategy_refs) != 1:
            raise ParticipantOpacityOperationalError("a passive model check requires one fixed strategy")
        strategy_refs = request.assumptions.strategy_refs
    return ParticipantOpacityModelAssumptionsModel(
        strategy_kind=parameters.strategy.kind,
        strategy_refs=strategy_refs,
        scheduler_refs=parameters.scheduler_refs,
        environment_refs=parameters.environment_refs,
        order_treatment=parameters.order.treatment,
        order_refs=parameters.order.order_refs,
        cut_ref=parameters.horizon.cut_ref,
        nondeterminism=parameters.nondeterminism,
        time_model=parameters.time.model,
        progress=parameters.time.progress,
        probability=parameters.probability,
    )


def validate_admission(
    request: ParticipantOpacityModelCheckInputModel,
    profile: BehavioralRelationProfileModel,
    catalog: BehavioralRelationCatalogModel,
) -> None:
    if request.analysis_profile != ANALYSIS_PROFILE:
        raise ParticipantOpacityOperationalError("unknown participant-opacity model-check profile")
    if not isinstance(profile.parameters, ParticipantPredicateOpacityParametersModel):
        raise ParticipantOpacityOperationalError("expected an opacity parameter profile")
    if request.catalog_digest != _catalog_digest(catalog):
        raise ParticipantOpacityOperationalError("behavioral catalog digest does not match the transition model")
    if (
        request.profile_id != profile.profile_id
        or request.profile_revision != profile.profile_revision
        or request.profile_digest != profile.canonical_digest
    ):
        raise ParticipantOpacityOperationalError("opacity profile identity does not match the transition model")
    if request.assumptions != _expected_assumptions(request, profile):
        raise ParticipantOpacityOperationalError("transition-model assumptions do not match the opacity profile")
    try:
        validate_behavioral_claim_binding(request.claim, catalog=catalog, profile=profile)
    except ValueError as exc:
        raise ParticipantOpacityOperationalError(
            "opacity model-check claim does not resolve against the exact catalog and profile"
        ) from exc
    _validate_profile_bounds(request, profile)
    _validate_state_domains(request, profile)
    _validate_initial_domain_coverage(request)


def _validate_profile_bounds(
    request: ParticipantOpacityModelCheckInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    counts = request.declared_counts
    bounds = profile.parameters.bounds
    if (
        counts.states > bounds.max_points
        or counts.runs > bounds.max_runs
        or counts.cuts > bounds.max_cuts
        or counts.strategies > bounds.max_strategies
        or counts.scheduler_environment_pairs > bounds.max_scheduler_environment_pairs
        or counts.order_variants > bounds.max_order_variants
    ):
        raise ParticipantOpacityOperationalError("transition model exceeds a governed opacity profile bound")


def _validate_state_domains(
    request: ParticipantOpacityModelCheckInputModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    assumptions = request.assumptions
    if {state.strategy_ref for state in request.states} != set(assumptions.strategy_refs):
        raise ParticipantOpacityOperationalError("transition-model strategy domain does not match the profile")
    if {state.scheduler_ref for state in request.states} != set(assumptions.scheduler_refs):
        raise ParticipantOpacityOperationalError("transition-model scheduler domain does not match the profile")
    if {state.environment_ref for state in request.states} != set(assumptions.environment_refs):
        raise ParticipantOpacityOperationalError("transition-model environment domain does not match the profile")
    expected_pairs = set(product(assumptions.scheduler_refs, assumptions.environment_refs))
    actual_pairs = {(state.scheduler_ref, state.environment_ref) for state in request.states}
    if actual_pairs != expected_pairs:
        raise ParticipantOpacityOperationalError(
            "transition-model scheduler/environment pairs do not match the profile Cartesian product"
        )
    if {state.order_ref for state in request.states} != set(assumptions.order_refs):
        raise ParticipantOpacityOperationalError("transition-model order domain does not match the profile")
    if {state.cut_ref for state in request.states} != {assumptions.cut_ref}:
        raise ParticipantOpacityOperationalError("transition-model evaluation cut does not match the profile")
    coalition = isinstance(profile.parameters.observer, CoalitionOpacityObserverModel)
    if any((state.coalition_fusion_key is not None) != coalition for state in request.states):
        raise ParticipantOpacityOperationalError("transition-model coalition coordinates do not match the profile")


def _validate_initial_domain_coverage(
    request: ParticipantOpacityModelCheckInputModel,
) -> None:
    initial_states = tuple(request.states[ordinal] for ordinal in request.initial_state_ordinals)
    actual = {
        (state.strategy_ref, state.scheduler_ref, state.environment_ref, state.order_ref) for state in initial_states
    }
    assumptions = request.assumptions
    expected = set(
        product(
            assumptions.strategy_refs,
            assumptions.scheduler_refs,
            assumptions.environment_refs,
            assumptions.order_refs,
        )
    )
    if actual != expected:
        raise ParticipantOpacityOperationalError(
            "initial states must cover every declared strategy/scheduler/environment/order domain"
        )


def unsupported_diagnostics(
    request: ParticipantOpacityModelCheckInputModel,
    checker: ParticipantOpacityModelCheckConfigurationModel,
) -> tuple[DiagnosticModel, ...]:
    diagnostics: list[DiagnosticModel] = []
    if not request.complete_model:
        diagnostics.append(
            diagnostic(
                _INCOMPLETE_CODE,
                "/complete_model",
                "The transition artifact is not declared to be the complete finite model.",
            )
        )
    if (
        request.declared_counts.states > checker.max_states
        or request.declared_counts.transitions > checker.max_transitions
    ):
        diagnostics.append(
            diagnostic(
                _BOUND_CODE,
                "/declared_counts",
                "The complete finite model exceeds the deterministic checker resource profile.",
            )
        )
    if len(request.assumptions.scheduler_refs) != 1 or len(request.assumptions.environment_refs) != 1:
        diagnostics.append(
            diagnostic(
                _SCHEDULER_CODE,
                "/assumptions",
                "The v1 checker supports only the profile's unambiguous singleton scheduler/environment posture.",
            )
        )
    if request.assumptions.order_treatment != "total-order":
        diagnostics.append(
            diagnostic(
                _ORDER_CODE,
                "/assumptions/order_treatment",
                "The v1 checker supports exact total-order models only.",
            )
        )
    return tuple(sorted(diagnostics, key=lambda item: (item.address, item.code)))


__all__ = (
    "ANALYSIS_PROFILE",
    "VACUOUS_CODE",
    "checker_configuration",
    "diagnostic",
    "unsupported_diagnostics",
    "validate_admission",
)
