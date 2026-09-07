"""Pure realization of one sealed admitted trial entry through public SDL APIs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from raes import canonical_instantiated_sdl_digest, select_scenario_family
from raes.canonical import canonical_sdl_digest
from raes.phase_contracts import (
    AdmittedBindingProvenance,
    AdmittedSelectionProvenance,
    TrialCoordinateProvenance,
    TrialInstantiationProvenance,
)
from raes.scenario import ExpandedScenario, InstantiatedScenario
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope
from raes_contracts.admitted_trial_plan_ingress import (
    AdmittedTrialPlanIngressError,
    revalidate_admitted_trial_plan,
)
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    BackendManifestV2Model,
    EvaluationPlanModel,
    ExperimentCaptureSpecModel,
    ExperimentReferenceModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    OrchestrationPlanModel,
    ProcessorManifestV2Model,
    ProvisioningPlanModel,
    TrialProcessorPlanReferenceModel,
)
from raes_contracts.experiment_bindings import ApparatusManifest, ApparatusManifestKey
from raes_contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

from .capture_admission import compile_capture_spec_demands
from .compiler import compile_scenario_runtime_model
from .models import ExecutionPlan
from .planner import plan as build_execution_plan
from .trial_compiler.apparatus import validate_admitted_apparatus
from .trial_compiler.models import CompilationFailure

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


def instantiate_admitted_trial_entry(
    *,
    plan: AdmittedTrialPlanModel,
    plan_entry_id: str,
    family: ExpandedScenario,
) -> InstantiatedScenario:
    """Instantiate one entry only after reconstructing its complete sealed plan."""

    try:
        admitted_plan = revalidate_admitted_trial_plan(plan)
    except AdmittedTrialPlanIngressError as exc:
        raise ValueError("admitted trial plan failed closed reconstruction") from exc
    if not isinstance(family, ExpandedScenario) or not family.semantic_validated:
        raise ValueError("trial realization requires an admitted expanded scenario family")
    family_reference = admitted_plan.input_refs.scenario_family_ref
    family_digest = canonical_sdl_digest(family).value
    if family.name != family_reference.ref_id or family_digest != family_reference.ref_digest:
        raise ValueError("scenario family identity does not match the admitted plan")
    entry = admitted_plan.entries.get(plan_entry_id)
    if entry is None or entry.plan_entry_id != plan_entry_id:
        raise ValueError("plan_entry_id does not resolve inside the admitted plan")
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
    return select_scenario_family(
        family,
        outcomes,
        trial_provenance=provenance,
    )


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
        raise ValueError("experiment identity does not match the admitted plan")
    task_ref = plan.input_refs.task_ref
    task_digest = canonical_json_digest(task.model_dump(mode="json"))
    if (
        experiment.task_ref != task_ref
        or task_ref.ref_id != task.task_id
        or task_ref.ref_version != task.task_version
        or plan.input_refs.task_digest != task_digest
    ):
        raise ValueError("task identity does not match the admitted plan")


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
        raise ValueError("capture specification identities do not match the admitted plan")
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
        raise ValueError("capture specification digests do not match the admitted plan")
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
        raise ValueError("task evidence requirements do not resolve to admitted capture requirements")


def _runtime_backend(
    selected: Mapping[ApparatusManifestKey, ApparatusManifest],
    backend_key: ApparatusManifestKey,
    realization_envelope: BackendRealizationEnvelopeModel,
) -> BackendManifest:
    backend = selected.get(backend_key)
    if not isinstance(backend, BackendManifestV2Model):
        raise ValueError("backend manifest key does not resolve to an admitted backend manifest")
    processors = [manifest for manifest in selected.values() if isinstance(manifest, ProcessorManifestV2Model)]
    if len(processors) != 1:
        raise ValueError("trial realization requires exactly one admitted processor manifest")
    processor = processors[0]
    if (
        backend.identity.name not in processor.compatibility.backends
        or processor.identity.name not in backend.compatibility.processors
    ):
        raise ValueError("processor and backend manifests are not mutually compatible")
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


def realize_admitted_trial_entry(
    *,
    inputs: TrialRealizationInputs,
    plan_entry_id: str,
    artifact_availability: ArtifactAvailabilityContext | None = None,
    target_name: str | None = None,
) -> TrialRealization:
    """Realize one exact admitted entry into existing typed processor plans."""

    admitted_plan = revalidate_admitted_trial_plan(inputs.plan)
    entry = admitted_plan.entries.get(plan_entry_id)
    if entry is None:
        raise ValueError("plan_entry_id does not resolve inside the admitted plan")
    _validate_experiment_and_task(admitted_plan, inputs.experiment, inputs.task)
    _validate_capture_specs(
        admitted_plan,
        inputs.experiment,
        inputs.task,
        inputs.capture_specs,
    )
    try:
        selected = validate_admitted_apparatus(
            entry.apparatus,
            inputs.apparatus_manifests,
            inputs.realization_envelope,
            intent=inputs.experiment.apparatus_intent,
        )
    except CompilationFailure as exc:
        raise ValueError(f"admitted apparatus manifest validation failed: {exc.code}") from exc
    runtime_backend = _runtime_backend(selected, inputs.backend_key, inputs.realization_envelope)
    instantiated = instantiate_admitted_trial_entry(
        plan=admitted_plan,
        plan_entry_id=plan_entry_id,
        family=inputs.family,
    )
    runtime_model = compile_scenario_runtime_model(instantiated)
    runtime_model = replace(
        runtime_model,
        capture_demands=(
            *runtime_model.capture_demands,
            *compile_capture_spec_demands(tuple(inputs.capture_specs.values())),
        ),
    )
    execution_plan = build_execution_plan(
        runtime_model,
        runtime_backend,
        target_name=target_name,
        artifact_availability=artifact_availability,
    )
    if not execution_plan.is_valid:
        raise ValueError("admitted trial processor planning failed")
    provisioning = provisioning_plan_model(execution_plan.provisioning)
    orchestration = orchestration_plan_model(execution_plan.orchestration)
    evaluation = evaluation_plan_model(execution_plan.evaluation)
    references = (
        _processor_plan_reference(
            run_id=entry.run_id,
            plan_kind="provisioning",
            model=provisioning,
        ),
        _processor_plan_reference(
            run_id=entry.run_id,
            plan_kind="orchestration",
            model=orchestration,
        ),
        _processor_plan_reference(
            run_id=entry.run_id,
            plan_kind="evaluation",
            model=evaluation,
        ),
    )
    return TrialRealization(
        instantiated=instantiated,
        snapshot_digest=canonical_instantiated_sdl_digest(instantiated).value,
        execution_plan=execution_plan,
        provisioning_plan=provisioning,
        orchestration_plan=orchestration,
        evaluation_plan=evaluation,
        processor_plan_refs=references,
    )


__all__ = [
    "TrialRealization",
    "TrialRealizationInputs",
    "instantiate_admitted_trial_entry",
    "realize_admitted_trial_entry",
]
