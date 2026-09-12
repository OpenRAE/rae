"""Atomic deterministic compiler from admitted SCE-002 inputs to a sealed plan."""

from __future__ import annotations

from collections.abc import Mapping

from raes import (
    ExpandedScenarioBindingTargetResolver,
    InstantiatedScenario,
    select_scenario_family,
    validate_experiment_selection_against_family,
)
from raes.realization_envelope import member
from raes_backend_protocols.capabilities import ObservationCapabilities
from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import (
    AdmittedBindingModel,
    AdmittedExecutionControlModel,
    AdmittedInstantiationProvenanceModel,
    AdmittedSelectionRecordModel,
    AdmittedTrialEntryModel,
    AdmittedTrialPlanAdmissionModel,
    AdmittedTrialPlanModel,
    BackendManifestV2Model,
    ExperimentBindingDescriptorModel,
    ExperimentSelectionMemberOutcomeModel,
    ExperimentSelectionReferenceOutcomeModel,
    LiteralBindingValueModel,
    ParticipantImplementationManifestModel,
    TrialCleanupPlanModel,
    TrialCoordinateModel,
    seal_admitted_trial_entry,
    seal_admitted_trial_plan,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.experiment_bindings import (
    ApparatusManifest,
    ApparatusManifestKey,
    ParticipantManifestKey,
    validate_experiment_binding_targets,
)

from ..capture_admission import (
    CaptureDemand,
    capture_admission_diagnostics,
    compile_capture_spec_demands,
    compile_scenario_capture_demands,
)
from .apparatus import (
    validate_selected_apparatus,
    validate_selected_participant_manifests,
)
from .inputs import coordinates, plan_intent, validate_input_identities, visit_indices
from .models import CompilationFailure, TrialCompilationRequest, TrialCompilationResult
from .policies import CoordinateSelections, ResolvedSelection, compile_coordinate_selections
from .profiles import admitted_profiles, coordinate_projection, derive_identity

_DOMAIN = "trial-compiler"
_BINDING_DESCRIPTORS_ADDRESS = "/binding_descriptors"
_ENTRIES_ADDRESS = "/entries/"


class _CaptureAdmissionFailure(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__("required capture is not supported by the admitted apparatus")
        self.diagnostics = diagnostics


def _fail(code: str, address: str, message: str) -> CompilationFailure:
    return CompilationFailure(code, address, message)


def _diagnostic(failure: CompilationFailure) -> Diagnostic:
    return Diagnostic(
        code=f"{_DOMAIN}.{failure.code}",
        domain=_DOMAIN,
        address=failure.address,
        message=failure.safe_message,
        severity=Severity.ERROR,
    )


def _outcome_binding_value(
    request: TrialCompilationRequest,
    selection: ResolvedSelection,
) -> object | None:
    outcome = selection.outcome
    if isinstance(outcome, LiteralBindingValueModel):
        value = outcome.value
    elif isinstance(outcome, ExperimentSelectionReferenceOutcomeModel):
        value = outcome.reference_id
    elif isinstance(outcome, ExperimentSelectionMemberOutcomeModel):
        point = request.family.variation_points[selection.point_id]
        alternatives = getattr(point, "alternatives", {})
        member = alternatives.get(outcome.member_id)
        value = member.reference if member is not None else None
    else:
        value = None
    return value


def _descriptor_matches_selection(
    request: TrialCompilationRequest,
    descriptor: ExperimentBindingDescriptorModel,
    selection: ResolvedSelection,
) -> bool:
    if getattr(descriptor.target, "variation_point_id", None) != selection.point_id:
        return False
    selected_value = _outcome_binding_value(request, selection)
    return isinstance(descriptor.value, LiteralBindingValueModel) and (
        type(descriptor.value.value) is type(selected_value) and descriptor.value.value == selected_value
    )


def _admitted_descriptors(
    request: TrialCompilationRequest,
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
    participant_manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel],
) -> dict[str, ExperimentBindingDescriptorModel]:
    descriptors = request.experiment.binding_descriptors
    if descriptors is None:
        return {}
    try:
        admitted = validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=ExpandedScenarioBindingTargetResolver(request.family),
            participant_manifests=participant_manifests,
            apparatus_manifests=apparatus_manifests,
        )
    except ValueError as exc:
        raise _fail(
            "binding-target-rejected",
            _BINDING_DESCRIPTORS_ADDRESS,
            "a binding descriptor target failed authoritative admission",
        ) from exc
    return {descriptor.binding_id: descriptor for descriptor in admitted.descriptors}


def _entry_bindings(
    request: TrialCompilationRequest,
    row: CoordinateSelections,
    coordinate: TrialCoordinateModel,
    descriptors: Mapping[str, ExperimentBindingDescriptorModel],
) -> list[AdmittedBindingModel]:
    bindings: list[AdmittedBindingModel] = []
    for selection in row.selections:
        policy = request.experiment.run_plan.selection_policies[selection.policy_id]
        for descriptor_id in sorted(getattr(policy, "binding_descriptor_refs", ())):
            descriptor = descriptors.get(descriptor_id)
            if descriptor is None or descriptor.source_condition_id != coordinate.condition_id:
                continue
            if not _descriptor_matches_selection(request, descriptor, selection):
                raise _fail(
                    "binding-selection-mismatch",
                    f"{_BINDING_DESCRIPTORS_ADDRESS}/{descriptor_id}",
                    "a binding descriptor does not equal its selected variation outcome",
                )
            bindings.append(AdmittedBindingModel(descriptor=descriptor, origin="selection"))
    if len({binding.descriptor.binding_id for binding in bindings}) != len(bindings):
        raise _fail(
            "binding-duplicate",
            _BINDING_DESCRIPTORS_ADDRESS,
            "an admitted binding descriptor is selected more than once",
        )
    if len(bindings) > request.limits.max_bindings_per_entry:
        raise _fail(
            "binding-limit-exceeded",
            _BINDING_DESCRIPTORS_ADDRESS,
            "entry bindings exceed the compilation limit",
        )
    return bindings


def _selection_records(row: CoordinateSelections) -> list[AdmittedSelectionRecordModel]:
    return [
        AdmittedSelectionRecordModel(
            variation_point_id=selection.point_id,
            origin_policy_id=selection.policy_id,
            origin_policy_kind=selection.policy_kind,
            outcome=selection.outcome,
        )
        for selection in row.selections
    ]


def _validate_selected_scenario(
    request: TrialCompilationRequest,
    row: CoordinateSelections,
    coordinate: TrialCoordinateModel,
) -> InstantiatedScenario:
    outcomes = {selection.point_id: selection.outcome for selection in row.selections}
    try:
        selected = select_scenario_family(request.family, outcomes)
    except (TypeError, ValueError) as exc:
        raise _fail(
            "selected-scenario-rejected",
            _ENTRIES_ADDRESS + (coordinate.replicate_id or "coordinate"),
            "the complete selection failed SDL-owned whole-scenario admission",
        ) from exc
    envelope_result = member(selected, request.realization_envelope.expression)
    if not envelope_result.holds:
        raise _fail(
            "realization-envelope-membership-rejected",
            _ENTRIES_ADDRESS + (coordinate.replicate_id or "coordinate"),
            "the selected scenario is outside the admitted realization envelope",
        )
    return selected


def _require_capture_admission(
    demands: tuple[CaptureDemand, ...],
    observations: tuple[ObservationCapabilities | None, ...],
) -> None:
    diagnostics = [
        diagnostic for observation in observations for diagnostic in capture_admission_diagnostics(demands, observation)
    ]
    if diagnostics:
        raise _CaptureAdmissionFailure(tuple(diagnostics))


def _compile_entry(
    request: TrialCompilationRequest,
    plan_id: str,
    row: CoordinateSelections,
    coordinate: TrialCoordinateModel,
    descriptors: Mapping[str, ExperimentBindingDescriptorModel],
    observations: tuple[ObservationCapabilities | None, ...],
) -> tuple[str, AdmittedTrialEntryModel, str, TrialCleanupPlanModel]:
    selected = _validate_selected_scenario(request, row, coordinate)
    _require_capture_admission(
        (
            *compile_scenario_capture_demands(selected),
            *compile_capture_spec_demands(tuple(request.capture_specs.values())),
        ),
        observations,
    )
    identity_projection = {
        "plan_id": plan_id,
        "coordinate": coordinate_projection(coordinate),
    }
    entry_id = derive_identity("trial-entry", identity_projection)
    run_id = derive_identity("archival-run", identity_projection)
    cleanup_id = derive_identity(
        "trial-cleanup",
        {
            "plan_entry_id": entry_id,
            "run_id": run_id,
            "template": request.execution_authority.cleanup.model_dump(mode="json"),
        },
    )
    cleanup = request.execution_authority.cleanup.bind(
        plan_id=cleanup_id,
        plan_entry_id=entry_id,
        run_id=run_id,
    )
    bindings = _entry_bindings(request, row, coordinate, descriptors)
    if len(row.draws) > request.limits.max_draws_per_entry:
        raise _fail(
            "draw-limit-exceeded",
            "/run_plan/stochastic_controls",
            "entry random draws exceed the compilation limit",
        )
    entry = seal_admitted_trial_entry(
        plan_entry_id=entry_id,
        coordinate=coordinate,
        run_id=run_id,
        selections=_selection_records(row),
        bindings=bindings,
        stochastic_draws=list(row.draws),
        apparatus=request.apparatus,
        execution_controls=AdmittedExecutionControlModel(
            attempt_timeout_seconds=request.execution_authority.attempt_timeout_seconds,
            on_timeout=request.execution_authority.on_timeout,
            on_cancellation=request.execution_authority.on_cancellation,
            cleanup_plan_ref=cleanup_id,
        ),
        instantiation_provenance=AdmittedInstantiationProvenanceModel(
            plan_id=plan_id,
            plan_entry_id=entry_id,
            run_id=run_id,
            scenario_family_id=request.family.name,
        ),
    )
    return entry_id, entry, cleanup_id, cleanup


def _failure_key(failure: CompilationFailure) -> tuple[str, str, str]:
    return failure.address, failure.code, failure.safe_message


def _compile_entries(
    request: TrialCompilationRequest,
    plan_id: str,
    coordinates: list[TrialCoordinateModel],
    rows: list[CoordinateSelections],
    descriptors: Mapping[str, ExperimentBindingDescriptorModel],
    visit_indices: tuple[int, ...],
    observations: tuple[ObservationCapabilities | None, ...],
) -> tuple[dict[str, AdmittedTrialEntryModel], dict[str, TrialCleanupPlanModel], set[str]]:
    entries: dict[str, AdmittedTrialEntryModel] = {}
    cleanup_plans: dict[str, TrialCleanupPlanModel] = {}
    used_control_ids: set[str] = set()
    canonical_failure: CompilationFailure | None = None
    capture_failures: dict[tuple[str, str, str], Diagnostic] = {}
    for coordinate_index in visit_indices:
        coordinate = coordinates[coordinate_index]
        row = rows[coordinate_index]
        try:
            entry_id, entry, cleanup_id, cleanup = _compile_entry(
                request,
                plan_id,
                row,
                coordinate,
                descriptors,
                observations,
            )
        except _CaptureAdmissionFailure as failure:
            capture_failures.update(
                {
                    (diagnostic.address, diagnostic.code, diagnostic.message): diagnostic
                    for diagnostic in failure.diagnostics
                }
            )
            continue
        except CompilationFailure as failure:
            candidate_failure = failure
        except (TypeError, ValueError) as exc:
            candidate_failure = _fail(
                "entry-invalid",
                _ENTRIES_ADDRESS + (coordinate.replicate_id or "coordinate"),
                "a trial entry failed closed construction",
            )
            candidate_failure.__cause__ = exc
        else:
            used_control_ids.update(draw.control_id for draw in row.draws)
            entries[entry_id] = entry
            cleanup_plans[cleanup_id] = cleanup
            continue
        if canonical_failure is None or _failure_key(candidate_failure) < _failure_key(canonical_failure):
            canonical_failure = candidate_failure
    if capture_failures:
        raise _CaptureAdmissionFailure(tuple(capture_failures[key] for key in sorted(capture_failures)))
    if canonical_failure is not None:
        raise canonical_failure
    return entries, cleanup_plans, used_control_ids


def _compile(
    request: TrialCompilationRequest,
    coordinate_partitions: tuple[tuple[int, ...], ...] | None,
) -> AdmittedTrialPlanModel:
    validate_input_identities(request)
    apparatus_manifests = validate_selected_apparatus(request)
    participant_manifests = validate_selected_participant_manifests(request)
    runtime_observations = tuple(
        backend_manifest_from_v2_model_with_envelope(backend, request.realization_envelope).observation
        for backend in sorted(
            (manifest for manifest in apparatus_manifests.values() if isinstance(manifest, BackendManifestV2Model)),
            key=lambda manifest: (manifest.identity.name, manifest.identity.version),
        )
    )
    try:
        validate_experiment_selection_against_family(request.experiment, family=request.family)
    except ValueError as exc:
        raise _fail(
            "selection-intent-rejected",
            "/run_plan/selection_policies",
            "selection policy intent failed scenario-family admission",
        ) from exc
    planned_coordinates = coordinates(request)
    rows = compile_coordinate_selections(
        family=request.family,
        spec=request.experiment,
        coordinates=planned_coordinates,
        limits=request.limits,
    )
    descriptors = _admitted_descriptors(
        request,
        apparatus_manifests,
        participant_manifests,
    )
    plan_id = derive_identity("trial-plan", plan_intent(request, planned_coordinates))
    traversal = visit_indices(len(planned_coordinates), coordinate_partitions)
    entries, cleanup_plans, used_control_ids = _compile_entries(
        request,
        plan_id,
        planned_coordinates,
        rows,
        descriptors,
        traversal,
        runtime_observations,
    )
    controls = {
        control.control_id: control
        for control in request.experiment.run_plan.stochastic_controls
        if control.control_id in used_control_ids
    }
    plan = seal_admitted_trial_plan(
        plan_id=plan_id,
        profiles=admitted_profiles(),
        input_refs=request.input_refs,
        stochastic_controls=controls,
        cleanup_plans=cleanup_plans,
        entries=entries,
        admission=AdmittedTrialPlanAdmissionModel(
            admitted_at_stage="admitted-sealed",
            entry_count=len(entries),
        ),
    )
    if len(canonical_json_bytes(plan.model_dump(mode="json"))) > request.limits.max_plan_bytes:
        raise _fail(
            "plan-byte-limit-exceeded",
            "",
            "canonical admitted plan bytes exceed the compilation limit",
        )
    return plan


def compile_admitted_trial_plan(
    request: TrialCompilationRequest,
    *,
    coordinate_partitions: tuple[tuple[int, ...], ...] | None = None,
) -> TrialCompilationResult:
    """Compile one request atomically, returning a sealed plan or safe diagnostics."""

    try:
        plan = _compile(request, coordinate_partitions)
    except _CaptureAdmissionFailure as failure:
        result = TrialCompilationResult(plan=None, diagnostics=failure.diagnostics)
    except CompilationFailure as failure:
        result = TrialCompilationResult(plan=None, diagnostics=(_diagnostic(failure),))
    except (TypeError, ValueError) as exc:
        failure = _fail(
            "input-invalid",
            "",
            "trial compilation input failed closed validation",
        )
        failure.__cause__ = exc
        result = TrialCompilationResult(plan=None, diagnostics=(_diagnostic(failure),))
    else:
        result = TrialCompilationResult(plan=plan, diagnostics=())
    return result


__all__ = ["compile_admitted_trial_plan"]
