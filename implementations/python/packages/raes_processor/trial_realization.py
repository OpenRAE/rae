"""Pure realization of one sealed admitted trial entry through public SDL APIs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace

from raes import canonical_instantiated_sdl_digest, select_scenario_family
from raes.canonical import canonical_sdl_digest
from raes.phase_contracts import (
    AdmittedBindingProvenance,
    AdmittedSelectionProvenance,
    TrialCoordinateProvenance,
    TrialInstantiationProvenance,
)
from raes.scenario import ExpandedScenario, InstantiatedScenario
from raes.selected_scenario import ExpandedScenarioBindingTargetResolver
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedMixedCompositionBindingModel,
    AdmittedTrialEntryModel,
    AdmittedTrialPlanModel,
    BackendManifestV2Model,
    EvaluationPlanModel,
    ExperimentCaptureSpecModel,
    ExperimentReferenceModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    OrchestrationPlanModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ProcessorManifestV2Model,
    ProvisioningPlanModel,
    TrialProcessorPlanReferenceModel,
    processor_backend_manifests_are_mutually_compatible,
)
from raes_contracts.contracts.admitted_trial_plan_ingress import (
    AdmittedTrialPlanIngressError,
    revalidate_admitted_trial_plan,
)
from raes_contracts.contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
)
from raes_contracts.errors import InvalidInputError, NotFoundError
from raes_contracts.experiment_bindings import ApparatusManifest, ApparatusManifestKey, ParticipantManifestKey
from raes_contracts.planning import PlanScope
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

from .capture_admission import compile_scoped_evidence_requirement_demands
from .compiler import compile_scenario_runtime_model
from .models import ExecutionPlan
from .planner import plan as build_execution_plan
from .trial_compiler.apparatus import validate_admitted_apparatus
from .trial_compiler.models import CompilationFailure
from .trial_compiler.sources import validate_authoring_selections

_PLAN_CONTRACT_IDS = {
    "provisioning": "provisioning-plan-v1",
    "orchestration": "orchestration-plan-v1",
    "evaluation": "evaluation-plan-v1",
}


@dataclass(frozen=True)
class TrialRealization:
    """Admitted instantiated scenario plus public processor-plan projections."""

    instantiated: InstantiatedScenario
    snapshot_digest: str
    execution_plan: ExecutionPlan
    provisioning_plan: ProvisioningPlanModel
    orchestration_plan: OrchestrationPlanModel
    evaluation_plan: EvaluationPlanModel
    processor_plan_refs: tuple[TrialProcessorPlanReferenceModel, ...]
    participant_configurations: tuple[ParticipantConfigurationResultModel, ...] = ()


@dataclass(frozen=True)
class TrialRealizationInputs:
    """Exact portable and apparatus inputs required to realize an admitted entry."""

    plan: AdmittedTrialPlanModel
    family: ExpandedScenario
    experiment: ExperimentSpecModel
    task: ExperimentTaskModel
    capture_specs: Mapping[str, ExperimentCaptureSpecModel]
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest]
    realization_envelope: BackendRealizationEnvelopeModel
    backend_key: ApparatusManifestKey
    participant_manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel] = field(
        default_factory=dict
    )


def _revalidate_plan_closed(plan: AdmittedTrialPlanModel) -> AdmittedTrialPlanModel:
    """Reconstruct a caller-held plan once through closed ingress."""

    try:
        return revalidate_admitted_trial_plan(plan)
    except AdmittedTrialPlanIngressError as exc:
        raise InvalidInputError("admitted trial plan failed closed reconstruction") from exc


def _validate_family_matches_plan(
    admitted_plan: AdmittedTrialPlanModel,
    family: ExpandedScenario,
) -> str:
    """Check the family identity against the owned plan and return its digest."""

    if not isinstance(family, ExpandedScenario) or not family.semantic_validated:
        raise ValueError("trial realization requires an admitted expanded scenario family")
    family_reference = admitted_plan.input_refs.scenario_family_ref
    family_digest = canonical_sdl_digest(family).value
    if family.name != family_reference.ref_id or family_digest != family_reference.ref_digest:
        raise InvalidInputError("scenario family identity does not match the admitted plan")
    if admitted_plan.trial_parallelism != family.trial_parallelism:
        raise InvalidInputError("trial parallelism differs from the admitted scenario family")
    return family_digest


def _instantiate_entry_from_validated_plan(
    *,
    admitted_plan: AdmittedTrialPlanModel,
    plan_entry_id: str,
    family: ExpandedScenario,
    family_digest: str,
    resolver: ExpandedScenarioBindingTargetResolver,
) -> InstantiatedScenario:
    """Instantiate one entry from an already validated plan and family."""

    entry = admitted_plan.entries.get(plan_entry_id)
    if entry is None or entry.plan_entry_id != plan_entry_id:
        raise NotFoundError("plan_entry_id does not resolve inside the admitted plan")
    provenance = TrialInstantiationProvenance(
        scenario_family_id=family.name,
        scenario_family_digest=family_digest,
        plan_id=admitted_plan.plan_id,
        plan_digest=admitted_plan.plan_digest,
        plan_entry_id=entry.plan_entry_id,
        entry_digest=entry.entry_digest,
        run_id=entry.run_id,
        coordinate=TrialCoordinateProvenance(**entry.coordinate.model_dump(mode="python")),
        selections=tuple(
            AdmittedSelectionProvenance(
                variation_point_id=selection.variation_point_id,
                record_digest=canonical_json_digest(selection.model_dump(mode="json")),
                record=selection.model_dump(mode="json"),
            )
            for selection in entry.selections
        ),
        bindings=tuple(
            AdmittedBindingProvenance(
                binding_id=binding.descriptor.binding_id,
                record_digest=canonical_json_digest(binding.model_dump(mode="json")),
                record=binding.model_dump(mode="json"),
            )
            for binding in entry.bindings
        ),
    )
    outcomes = {selection.variation_point_id: selection.outcome for selection in entry.selections}
    for selection in entry.selections:
        if selection.treatment is not None:
            resolver.validate_selection(selection.treatment)
    return select_scenario_family(
        family,
        outcomes,
        trial_provenance=provenance,
    )


def _owned_expanded_family(family: ExpandedScenario) -> ExpandedScenario:
    """Capture an independent family snapshot so caller mutation cannot reach it.

    ``ContractModel`` and SDL models are not frozen, so a batch executor must own
    the family it validates and selects from. ``model_copy(deep=True)`` preserves
    the private expansion and semantic-admission state.
    """

    if not isinstance(family, ExpandedScenario):
        raise ValueError("trial realization requires an admitted expanded scenario family")
    return family.model_copy(deep=True)


def admitted_trial_batch_instantiator(
    *,
    plan: AdmittedTrialPlanModel,
    family: ExpandedScenario,
) -> Callable[[str], InstantiatedScenario]:
    """Validate one complete plan once and return a one-entry instantiator.

    The executor reconstructs the plan once, checks family identity once, and
    owns that validated snapshot. Each call instantiates one ``plan_entry_id``
    without repeating whole-plan reconstruction. The executor accepts only an
    entry ID; it exposes no mutable plan, family, or entry alias. For a
    whole-plan traversal, iterate ``canonical_entry_order(plan)``.
    """

    owned_family = _owned_expanded_family(family)
    admitted_plan = _revalidate_plan_closed(plan)
    family_digest = _validate_family_matches_plan(admitted_plan, owned_family)
    resolver = ExpandedScenarioBindingTargetResolver(owned_family)

    def instantiate_one(plan_entry_id: str) -> InstantiatedScenario:
        return _instantiate_entry_from_validated_plan(
            admitted_plan=admitted_plan,
            plan_entry_id=plan_entry_id,
            family=owned_family,
            family_digest=family_digest,
            resolver=resolver,
        )

    return instantiate_one


def instantiate_admitted_trial_entry(
    *,
    plan: AdmittedTrialPlanModel,
    plan_entry_id: str,
    family: ExpandedScenario,
) -> InstantiatedScenario:
    """Instantiate one entry only after reconstructing its complete sealed plan."""

    return admitted_trial_batch_instantiator(plan=plan, family=family)(plan_entry_id)


def _validate_experiment_and_task(
    plan: AdmittedTrialPlanModel,
    experiment: ExperimentSpecModel,
    task: ExperimentTaskModel,
) -> None:
    authoring_ref = plan.input_refs.authoring_input_ref
    if (
        authoring_ref.ref_id != experiment.spec_id
        or authoring_ref.ref_version != experiment.spec_version
        or authoring_ref.ref_digest != canonical_json_digest(experiment.model_dump(mode="json"))
    ):
        raise InvalidInputError("experiment identity does not match the admitted plan")
    task_ref = plan.input_refs.task_ref
    task_digest = canonical_json_digest(task.model_dump(mode="json"))
    if (
        experiment.task_ref != task_ref
        or task_ref.ref_id != task.task_id
        or task_ref.ref_version != task.task_version
        or plan.input_refs.task_digest != task_digest
    ):
        raise InvalidInputError("task identity does not match the admitted plan")


def _validate_capture_specs(
    plan: AdmittedTrialPlanModel,
    experiment: ExperimentSpecModel,
    task: ExperimentTaskModel,
    capture_specs: Mapping[str, ExperimentCaptureSpecModel],
) -> None:
    expected_keys = {(reference.ref_id, reference.ref_version) for reference in experiment.capture_spec_refs}
    supplied_keys = {
        (capture_spec.capture_spec_id, capture_spec.spec_version) for capture_spec in capture_specs.values()
    }
    if (
        expected_keys != supplied_keys
        or len(supplied_keys) != len(capture_specs)
        or any(key != capture_spec.capture_spec_id for key, capture_spec in capture_specs.items())
    ):
        raise InvalidInputError("capture specification identities do not match the admitted plan")
    expected_pins = {
        (
            capture_spec.capture_spec_id,
            capture_spec.spec_version,
            canonical_json_digest(capture_spec.model_dump(mode="json")),
        )
        for capture_spec in capture_specs.values()
    }
    admitted_pins = {
        (reference.ref_id, reference.ref_version, reference.ref_digest)
        for reference in plan.input_refs.capture_spec_refs
    }
    if expected_pins != admitted_pins:
        raise InvalidInputError("capture specification digests do not match the admitted plan")
    requirement_ids = {
        requirement.requirement_id
        for capture_spec in capture_specs.values()
        for requirement in capture_spec.capture_requirements.values()
    }
    task_requirement_ids = {reference.ref_id for reference in task.evaluation_protocol.observation_requirements}
    task_requirement_ids.update(
        reference.ref_id
        for metric in task.evaluation_protocol.metric_definitions.values()
        for reference in metric.evidence_requirements
    )
    if not task_requirement_ids.issubset(requirement_ids):
        raise InvalidInputError("task evidence requirements do not resolve to admitted capture requirements")


def _runtime_backend(
    selected: Mapping[ApparatusManifestKey, ApparatusManifest],
    backend_key: ApparatusManifestKey,
    realization_envelope: BackendRealizationEnvelopeModel,
) -> BackendManifest:
    backend = selected.get(backend_key)
    if not isinstance(backend, BackendManifestV2Model):
        raise InvalidInputError("backend manifest key does not resolve to an admitted backend manifest")
    processors = [manifest for manifest in selected.values() if isinstance(manifest, ProcessorManifestV2Model)]
    if len(processors) != 1:
        raise InvalidInputError("trial realization requires exactly one admitted processor manifest")
    processor = processors[0]
    if not processor_backend_manifests_are_mutually_compatible(processor, backend):
        raise InvalidInputError("processor and backend manifests are not mutually compatible")
    return backend_manifest_from_v2_model_with_envelope(backend, realization_envelope)


def _processor_plan_reference(
    *,
    run_id: str,
    plan_kind: str,
    model: ProvisioningPlanModel | OrchestrationPlanModel | EvaluationPlanModel,
) -> TrialProcessorPlanReferenceModel:
    contract_id = _PLAN_CONTRACT_IDS[plan_kind]
    return TrialProcessorPlanReferenceModel(
        plan_kind=plan_kind,
        artifact_ref=ExperimentReferenceModel(
            ref_kind="other",
            ref_id=f"{run_id}:{plan_kind}",
            ref_version=contract_id,
            ref_digest=canonical_json_digest(model.model_dump(mode="json")),
        ),
    )


def _trial_realization(
    entry: AdmittedTrialEntryModel,
    instantiated: InstantiatedScenario,
    execution_plan: ExecutionPlan,
) -> TrialRealization:
    """Project one valid execution plan into the typed trial realization."""

    if not execution_plan.is_valid:
        raise InvalidInputError("admitted trial processor planning failed")
    provisioning = provisioning_plan_model(execution_plan.provisioning)
    orchestration = orchestration_plan_model(execution_plan.orchestration)
    evaluation = evaluation_plan_model(execution_plan.evaluation)
    references = tuple(
        _processor_plan_reference(run_id=entry.run_id, plan_kind=plan_kind, model=model)
        for plan_kind, model in (
            ("provisioning", provisioning),
            ("orchestration", orchestration),
            ("evaluation", evaluation),
        )
    )
    return TrialRealization(
        instantiated=instantiated,
        snapshot_digest=canonical_instantiated_sdl_digest(instantiated).value,
        execution_plan=execution_plan,
        provisioning_plan=provisioning,
        orchestration_plan=orchestration,
        evaluation_plan=evaluation,
        processor_plan_refs=references,
        # Return independent copies so a caller mutating one result cannot
        # change the owned plan or a later result (issue #2046 review).
        participant_configurations=tuple(
            configuration.model_copy(deep=True) for configuration in entry.participant_configurations
        ),
    )


def admitted_trial_batch_realizer(
    *,
    inputs: TrialRealizationInputs,
    artifact_availability: ArtifactAvailabilityContext | None = None,
    target_name: str | None = None,
) -> Callable[[str], TrialRealization]:
    """Validate one complete plan once and return a one-entry realizer.

    The executor reconstructs the plan once and runs the plan-level experiment,
    task, authoring, capture, and family checks once. It captures an independent
    snapshot of every realization input, so caller mutation after preparation
    cannot change a later result. Each call realizes one ``plan_entry_id`` into
    typed processor plans without repeating whole-plan reconstruction or
    authoring scans. The executor owns its validated plan and accepts only an
    entry ID. For a whole-plan traversal, iterate ``canonical_entry_order(plan)``
    or use ``dispatch_batch_schedule``.
    """

    # Capture an independent snapshot of every input before validation, then
    # consume only owned state throughout the batch (issue #2046 review). The
    # frozen inputs container does not freeze its mutable model children.
    owned = deepcopy(inputs)
    owned_availability = deepcopy(artifact_availability)
    admitted_plan = _revalidate_plan_closed(owned.plan)
    _validate_experiment_and_task(admitted_plan, owned.experiment, owned.task)
    validate_authoring_selections(
        admitted_plan,
        owned.family,
        owned.experiment,
        owned.apparatus_manifests,
        owned.participant_manifests,
    )
    _validate_capture_specs(
        admitted_plan,
        owned.experiment,
        owned.task,
        owned.capture_specs,
    )
    family_digest = _validate_family_matches_plan(admitted_plan, owned.family)
    resolver = ExpandedScenarioBindingTargetResolver(owned.family)

    def realize_one(plan_entry_id: str) -> TrialRealization:
        entry = admitted_plan.entries.get(plan_entry_id)
        if entry is None:
            raise NotFoundError("plan_entry_id does not resolve inside the admitted plan")
        if isinstance(entry.apparatus, AdmittedMixedCompositionBindingModel):
            raise InvalidInputError("mixed-composition runtime coordination is not implemented")
        # The planner retains these dependencies in the returned execution plan.
        # Give each result its own copies; they are small and do not grow with the plan.
        manifests = deepcopy(owned.apparatus_manifests)
        envelope = deepcopy(owned.realization_envelope)
        try:
            selected = validate_admitted_apparatus(
                entry.apparatus,
                manifests,
                envelope,
                intent=owned.experiment.apparatus_intent,
            )
        except CompilationFailure as exc:
            raise InvalidInputError(f"admitted apparatus manifest validation failed: {exc.code}") from exc
        runtime_backend = _runtime_backend(selected, owned.backend_key, envelope)
        instantiated = _instantiate_entry_from_validated_plan(
            admitted_plan=admitted_plan,
            plan_entry_id=plan_entry_id,
            family=owned.family,
            family_digest=family_digest,
            resolver=resolver,
        )
        runtime_model = compile_scenario_runtime_model(instantiated)
        relations = (
            *owned.task.evidence_requirement_relations,
            *owned.experiment.run_plan.evidence_requirement_relations,
        )
        runtime_model = replace(
            runtime_model,
            capture_demands=compile_scoped_evidence_requirement_demands(
                instantiated,
                tuple(owned.capture_specs.values()),
                relations,
                relation_scenario=owned.family,
            ),
        )
        execution_plan = build_execution_plan(
            runtime_model,
            runtime_backend,
            processor_manifest=next(
                manifest for manifest in selected.values() if isinstance(manifest, ProcessorManifestV2Model)
            ),
            # Bind the target plus the admitted entry's authoritative run identity and
            # its unique instantiation coordinate so per-run/per-instantiation generated
            # values reconcile against the correct scope (issue #1276).
            scope=PlanScope(target_name=target_name, run_id=entry.run_id, instantiation_id=plan_entry_id),
            artifact_availability=deepcopy(owned_availability),
        )
        return _trial_realization(entry, instantiated, execution_plan)

    return realize_one


def realize_admitted_trial_entry(
    *,
    inputs: TrialRealizationInputs,
    plan_entry_id: str,
    artifact_availability: ArtifactAvailabilityContext | None = None,
    target_name: str | None = None,
) -> TrialRealization:
    """Realize one exact admitted entry into existing typed processor plans."""

    return admitted_trial_batch_realizer(
        inputs=inputs,
        artifact_availability=artifact_availability,
        target_name=target_name,
    )(plan_entry_id)


__all__ = [
    "TrialRealization",
    "TrialRealizationInputs",
    "admitted_trial_batch_instantiator",
    "admitted_trial_batch_realizer",
    "instantiate_admitted_trial_entry",
    "realize_admitted_trial_entry",
]
