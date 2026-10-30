"""Deterministic finite-state model checking for participant predicate opacity."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from pydantic import ValidationError
from raes_contracts.behavioral_authority_errors import (
    BehavioralAuthorityArtifactError,
    BehavioralAuthorityUnsupportedError,
)
from raes_contracts.behavioral_relation_profiles import (
    BehavioralRelationProfileModel,
    load_behavioral_relation_profile_revision,
)
from raes_contracts.behavioral_relations import (
    BehavioralRelationCatalogModel,
    load_behavioral_relation_catalog_revision,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import DiagnosticModel
from raes_contracts.json_ingress import StrictJsonIngressError, parse_bounded_json_object
from raes_contracts.participant_opacity import (
    ParticipantOpacityModelCheckConfigurationModel,
    ParticipantOpacityModelCheckCounterexampleDigestInput,
    ParticipantOpacityModelCheckCounterexampleModel,
    ParticipantOpacityModelCheckCoverageModel,
    ParticipantOpacityModelCheckEvidenceModel,
    ParticipantOpacityModelCheckInputModel,
    ParticipantOpacityModelCheckOutcome,
    ParticipantOpacityModelStateModel,
    ParticipantOpacityModelTransitionModel,
    ParticipantOpacityStrategyCoverageModel,
    UnsupportedParticipantOpacityModelCheckModel,
    participant_opacity_model_check_counterexample_digest,
)

from ._errors import (
    ParticipantOpacityEvidenceError,
    ParticipantOpacityInputError,
    ParticipantOpacityOperationalError,
)
from ._kernel import evaluate_opacity_kernel
from ._model_check_admission import (
    ANALYSIS_PROFILE,
    VACUOUS_CODE,
    checker_configuration,
    diagnostic,
    unsupported_diagnostics,
    validate_admission,
)

_MAX_INPUT_BYTES = 16 * 1024 * 1024
_INPUT_REFUSED = "participant-opacity model-check input failed bounded closed-world admission"
_AUTHORITY_DAMAGED = "the packaged participant-opacity profile or catalog authority is damaged"


def _empty_coverage(
    request: ParticipantOpacityModelCheckInputModel,
) -> ParticipantOpacityModelCheckCoverageModel:
    return ParticipantOpacityModelCheckCoverageModel(
        declared=request.declared_counts,
        explored_states=0,
        explored_transitions=0,
        reachable_evaluation_points=0,
        reachable_secret_points=0,
        strategy_coverage=(),
        explored_scheduler_environment_pairs=0,
        explored_order_variants=0,
        complete_fixed_point=False,
    )


def _common_evidence(
    request: ParticipantOpacityModelCheckInputModel,
    checker: ParticipantOpacityModelCheckConfigurationModel,
    *,
    derived_carrier_digest: str,
    coverage: ParticipantOpacityModelCheckCoverageModel,
) -> dict[str, object]:
    return {
        "schema_version": "participant-opacity-model-check-evidence/v1",
        "analysis_profile": ANALYSIS_PROFILE,
        "provenance_scope": "normalized-model-only",
        "taxonomy_id": request.claim.taxonomy_id,
        "taxonomy_revision": request.claim.taxonomy_revision,
        "catalog_digest": request.catalog_digest,
        "relation_id": request.claim.relation_id,
        "profile_id": request.profile_id,
        "profile_revision": request.profile_revision,
        "profile_digest": request.profile_digest,
        "source": request.source,
        "model_ref": request.model_ref,
        "model_revision": request.model_revision,
        "model_digest": request.canonical_digest,
        "materializer_id": request.materializer_id,
        "materializer_version": request.materializer_version,
        "materializer_digest": request.materializer_digest,
        "assumptions": request.assumptions,
        "assumptions_digest": request.assumptions.canonical_digest,
        "checker_configuration": checker,
        "checker_configuration_digest": checker.canonical_digest,
        "derived_carrier_digest": derived_carrier_digest,
        "claim": request.claim,
        "coverage": coverage,
    }


def _unsupported_evidence(
    request: ParticipantOpacityModelCheckInputModel,
    checker: ParticipantOpacityModelCheckConfigurationModel,
    diagnostics: tuple[DiagnosticModel, ...],
) -> ParticipantOpacityModelCheckEvidenceModel:
    return ParticipantOpacityModelCheckEvidenceModel(
        **_common_evidence(
            request,
            checker,
            derived_carrier_digest=canonical_json_digest(()),
            coverage=_empty_coverage(request),
        ),
        outcome=ParticipantOpacityModelCheckOutcome.UNSUPPORTED,
        diagnostics=diagnostics,
        unsupported=UnsupportedParticipantOpacityModelCheckModel(
            profile="raes-participant-opacity-model-check-unsupported/v1",
            reason_codes=tuple(sorted({item.code for item in diagnostics})),
        ),
    )


def _reachable_fixed_point(
    request: ParticipantOpacityModelCheckInputModel,
) -> tuple[
    tuple[ParticipantOpacityModelStateModel, ...],
    tuple[ParticipantOpacityModelTransitionModel, ...],
    dict[int, ParticipantOpacityModelTransitionModel | None],
]:
    adjacency: dict[int, tuple[ParticipantOpacityModelTransitionModel, ...]] = {}
    for transition in request.transitions:
        source = transition.source_state_ordinal
        adjacency[source] = (*adjacency.get(source, ()), transition)
    visited = set(request.initial_state_ordinals)
    parents: dict[int, ParticipantOpacityModelTransitionModel | None] = dict.fromkeys(request.initial_state_ordinals)
    queue = deque(request.initial_state_ordinals)
    explored_transitions: list[ParticipantOpacityModelTransitionModel] = []
    while queue:
        source = queue.popleft()
        for transition in adjacency.get(source, ()):
            explored_transitions.append(transition)
            target = transition.target_state_ordinal
            if target in visited:
                continue
            visited.add(target)
            parents[target] = transition
            queue.append(target)
    states = tuple(request.states[ordinal] for ordinal in sorted(visited))
    return states, tuple(explored_transitions), parents


def _coverage(
    request: ParticipantOpacityModelCheckInputModel,
    states: tuple[ParticipantOpacityModelStateModel, ...],
    transitions: tuple[ParticipantOpacityModelTransitionModel, ...],
) -> ParticipantOpacityModelCheckCoverageModel:
    evaluation_states = tuple(state for state in states if state.evaluation_point)
    transition_sources = {
        transition.ordinal: request.states[transition.source_state_ordinal].strategy_ref for transition in transitions
    }
    per_strategy = []
    for strategy_ref in request.assumptions.strategy_refs:
        strategy_states = tuple(state for state in states if state.strategy_ref == strategy_ref)
        strategy_evaluation = tuple(state for state in strategy_states if state.evaluation_point)
        per_strategy.append(
            ParticipantOpacityStrategyCoverageModel(
                strategy_ref=strategy_ref,
                explored_states=len(strategy_states),
                explored_transitions=sum(
                    transition_sources[transition.ordinal] == strategy_ref for transition in transitions
                ),
                reachable_evaluation_points=len(strategy_evaluation),
                reachable_secret_points=sum(state.secret_holds for state in strategy_evaluation),
            )
        )
    return ParticipantOpacityModelCheckCoverageModel(
        declared=request.declared_counts,
        explored_states=len(states),
        explored_transitions=len(transitions),
        reachable_evaluation_points=len(evaluation_states),
        reachable_secret_points=sum(state.secret_holds for state in evaluation_states),
        strategy_coverage=tuple(per_strategy),
        explored_scheduler_environment_pairs=len({(state.scheduler_ref, state.environment_ref) for state in states}),
        explored_order_variants=len({state.order_ref for state in states}),
        complete_fixed_point=True,
    )


def _counterexample_path(
    actual_state_ordinal: int,
    parents: dict[int, ParticipantOpacityModelTransitionModel | None],
) -> tuple[int, ...]:
    path: list[int] = []
    state_ordinal = actual_state_ordinal
    while parents[state_ordinal] is not None:
        transition = parents[state_ordinal]
        assert transition is not None
        path.append(transition.ordinal)
        state_ordinal = transition.source_state_ordinal
    return tuple(reversed(path))


def model_check_participant_opacity_input(
    request: ParticipantOpacityModelCheckInputModel,
    *,
    profile: BehavioralRelationProfileModel,
    catalog: BehavioralRelationCatalogModel,
) -> ParticipantOpacityModelCheckEvidenceModel:
    """Exhaustively model-check one admitted complete finite transition system."""

    validate_admission(request, profile, catalog)
    checker = checker_configuration()
    diagnostics = unsupported_diagnostics(request, checker)
    if diagnostics:
        return _unsupported_evidence(request, checker, diagnostics)
    return _reachable_evidence(request, checker)


def _reachable_evidence(
    request: ParticipantOpacityModelCheckInputModel,
    checker: ParticipantOpacityModelCheckConfigurationModel,
) -> ParticipantOpacityModelCheckEvidenceModel:
    reachable_states, explored_transitions, parents = _reachable_fixed_point(request)
    evaluation_states = tuple(state for state in reachable_states if state.evaluation_point)
    coverage = _coverage(request, reachable_states, explored_transitions)
    derived_carrier_digest = canonical_json_digest(tuple(state.model_dump(mode="json") for state in evaluation_states))
    kernel_result = evaluate_opacity_kernel(evaluation_states)
    common = _common_evidence(
        request,
        checker,
        derived_carrier_digest=derived_carrier_digest,
        coverage=coverage,
    )
    if kernel_result.checked_secret_points == 0:
        vacuous_diagnostic = diagnostic(
            VACUOUS_CODE,
            "/states",
            "The reachable evaluation-point carrier contains no protected secret point.",
        )
        return ParticipantOpacityModelCheckEvidenceModel(
            **common,
            outcome=ParticipantOpacityModelCheckOutcome.VACUOUS,
            diagnostics=(vacuous_diagnostic,),
            unsupported=UnsupportedParticipantOpacityModelCheckModel(
                profile="raes-participant-opacity-model-check-unsupported/v1",
                reason_codes=(vacuous_diagnostic.code,),
            ),
        )

    if kernel_result.counterexample_actual_ordinal is not None:
        assert kernel_result.counterexample_cell_size is not None
        actual_ordinal = kernel_result.counterexample_actual_ordinal
        actual_state = request.states[actual_ordinal]
        path = _counterexample_path(actual_ordinal, parents)
        safe_ref = f"participant-opacity-model-check-counterexample:{actual_ordinal:06d}"
        counterexample = ParticipantOpacityModelCheckCounterexampleModel(
            safe_ref=safe_ref,
            counterexample_digest=participant_opacity_model_check_counterexample_digest(
                ParticipantOpacityModelCheckCounterexampleDigestInput(
                    safe_ref=safe_ref,
                    actual_state_ordinal=actual_ordinal,
                    actual_path_transition_ordinals=path,
                    strategy_ref=actual_state.strategy_ref,
                    examined_cell_size=kernel_result.counterexample_cell_size,
                    model_digest=request.canonical_digest,
                    profile_digest=request.profile_digest,
                    derived_carrier_digest=derived_carrier_digest,
                )
            ),
            actual_state_ordinal=actual_ordinal,
            actual_path_transition_ordinals=path,
            strategy_ref=actual_state.strategy_ref,
            examined_cell_size=kernel_result.counterexample_cell_size,
        )
        return ParticipantOpacityModelCheckEvidenceModel(
            **common,
            outcome=ParticipantOpacityModelCheckOutcome.COUNTEREXAMPLE,
            diagnostics=(),
            counterexample=counterexample,
        )

    return ParticipantOpacityModelCheckEvidenceModel(
        **common,
        outcome=ParticipantOpacityModelCheckOutcome.HOLDS,
        diagnostics=(),
    )


def model_check_participant_opacity_file(
    path: Path,
) -> ParticipantOpacityModelCheckEvidenceModel:
    """Model-check one bounded strict-JSON complete finite transition model."""

    try:
        content = path.read_bytes()
    except OSError:
        # A file that cannot be read is a host failure; a later attempt can succeed.
        raise ParticipantOpacityOperationalError(_INPUT_REFUSED) from None
    try:
        payload = parse_bounded_json_object(content, max_bytes=_MAX_INPUT_BYTES)
        request = ParticipantOpacityModelCheckInputModel.model_validate(payload)
    except StrictJsonIngressError, ValidationError:
        # The caller can correct a document that is not strict JSON or fails its governed contract.
        raise ParticipantOpacityInputError(_INPUT_REFUSED) from None
    try:
        profile = load_behavioral_relation_profile_revision(
            request.profile_id,
            request.profile_revision,
        )
        catalog = load_behavioral_relation_catalog_revision(request.taxonomy_revision)
    except BehavioralAuthorityUnsupportedError as exc:
        raise ParticipantOpacityInputError(_INPUT_REFUSED) from exc
    except BehavioralAuthorityArtifactError as exc:
        raise ParticipantOpacityOperationalError(_AUTHORITY_DAMAGED) from exc
    return model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )


def replay_participant_opacity_model_check_evidence(
    request: ParticipantOpacityModelCheckInputModel,
    profile: BehavioralRelationProfileModel,
    catalog: BehavioralRelationCatalogModel,
    evidence: ParticipantOpacityModelCheckEvidenceModel,
) -> ParticipantOpacityModelCheckEvidenceModel:
    """Recompute every catalog/profile/model/checker/coverage/result join."""

    replayed = model_check_participant_opacity_input(
        request,
        profile=profile,
        catalog=catalog,
    )
    if canonical_json_digest(replayed.model_dump(mode="json")) != canonical_json_digest(
        evidence.model_dump(mode="json")
    ):
        raise ParticipantOpacityEvidenceError("participant opacity model-check evidence did not reproduce")
    return replayed


__all__ = (
    "ANALYSIS_PROFILE",
    "model_check_participant_opacity_file",
    "model_check_participant_opacity_input",
    "replay_participant_opacity_model_check_evidence",
)
