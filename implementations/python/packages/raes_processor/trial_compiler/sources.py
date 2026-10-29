"""Compare typed plan contents with separately supplied pinned authoring intent."""

from collections.abc import Mapping

from pydantic import ValidationError
from raes.scenario import ExpandedScenario
from raes.selected_scenario import ExpandedScenarioBindingTargetResolver
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import (
    AdmittedSelectionRecordModel,
    AdmittedTrialEntryModel,
    AdmittedTrialPlanModel,
    ExperimentBindingDescriptorSetModel,
    ExperimentSpecModel,
    ParticipantImplementationManifestModel,
    TrialCompilationLimitsModel,
    TrialCoordinateModel,
)
from raes_contracts.errors import InvalidInputError
from raes_contracts.experiment_bindings import (
    ApparatusManifest,
    ApparatusManifestKey,
    ParticipantManifestKey,
    validate_experiment_binding_targets,
)

from .apparatus import validate_participant_manifest_references
from .inputs import coordinate_replicate_id
from .models import CompilationFailure
from .policies import compile_coordinate_selections
from .profiles import coordinate_projection, derive_identity
from .replacement_inputs import replacement_coordinate


def validate_authoring_selections(
    plan: AdmittedTrialPlanModel,
    family: ExpandedScenario,
    experiment: ExperimentSpecModel,
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
    participant_manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel],
) -> None:
    """Check exact coordinates, bindings and selection sets without renormalizing configuration.

    A difference from the admitted plan raises ``InvalidInputError`` (ADR-116).
    """
    design = experiment.factorial_design
    typed = design is not None and design.profile == "factorial-treatments-v1"
    if not typed and plan.profiles.treatment_profile is None:
        return
    if not typed or plan.profiles.treatment_profile != "factorial-treatments-v1":
        raise InvalidInputError("authoring selection profile differs from the admitted plan")
    # Reconstruct direct caller-held models before trusting their source joins.
    try:
        experiment = ExperimentSpecModel.model_validate(experiment.model_dump(mode="python"))
    except ValidationError as exc:
        # The contract owner refuses with ValueError (E3); refuse the authoring input here (E9).
        raise InvalidInputError("authoring experiment failed closed reconstruction") from exc
    coordinates = _authoring_coordinates(plan, experiment)
    _validate_coordinate_set(plan, coordinates)
    rows = compile_coordinate_selections(
        family=family,
        spec=experiment,
        coordinates=coordinates,
        limits=TrialCompilationLimitsModel(),
    )
    records = {
        canonical_json_bytes(coordinate.model_dump(mode="json")): row.records()
        for coordinate, row in zip(coordinates, rows, strict=True)
    }
    descriptors = experiment.binding_descriptors
    if descriptors is not None and participant_manifests:
        descriptors = _resolve_descriptors(plan, family, descriptors, apparatus_manifests, participant_manifests)
    for entry in plan.entries.values():
        expected = records[canonical_json_bytes(entry.coordinate.model_dump(mode="json"))]
        _validate_entry_sources(entry, expected, descriptors)


def _validate_coordinate_set(plan: AdmittedTrialPlanModel, coordinates: list[TrialCoordinateModel]) -> None:
    expected = {canonical_json_bytes(coordinate.model_dump(mode="json")) for coordinate in coordinates}
    actual = {canonical_json_bytes(entry.coordinate.model_dump(mode="json")) for entry in plan.entries.values()}
    if actual != expected or len(plan.entries) != len(coordinates):
        raise InvalidInputError("authoring selection coordinates differ from the admitted plan")


def _resolve_descriptors(
    plan: AdmittedTrialPlanModel,
    family: ExpandedScenario,
    descriptors: ExperimentBindingDescriptorSetModel,
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
    participant_manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel],
) -> ExperimentBindingDescriptorSetModel:
    try:
        for entry in plan.entries.values():
            validate_participant_manifest_references(entry.apparatus.participant_manifest_refs, participant_manifests)
    except CompilationFailure as exc:
        raise InvalidInputError("participant manifest authority differs from the admitted plan") from exc
    return validate_experiment_binding_targets(
        descriptors,
        scenario_resolver=ExpandedScenarioBindingTargetResolver(family),
        participant_manifests=participant_manifests,
        apparatus_manifests=apparatus_manifests,
    )


def _authoring_coordinates(
    plan: AdmittedTrialPlanModel,
    experiment: ExperimentSpecModel,
) -> list[TrialCoordinateModel]:
    allocation = experiment.run_plan.allocation
    coordinates = [
        TrialCoordinateModel(condition_id=condition, replicate_id=coordinate_replicate_id(ordinal))
        for condition in sorted(allocation.compared_conditions)
        for ordinal in range(1, allocation.target_runs_per_condition + 1)
    ]
    origin = plan.replacement_origin
    if origin is not None:
        policy = experiment.run_plan.replacement_policy
        indices = [
            index
            for index, coordinate in enumerate(coordinates)
            if derive_identity(
                "trial-entry", {"plan_id": origin.root_plan_id, "coordinate": coordinate_projection(coordinate)}
            )
            == origin.root_entry_id
        ]
        if policy is None or policy != plan.replacement_policy or len(indices) != 1:
            raise InvalidInputError("authoring selection replacement slot differs from the admitted plan")
        coordinates = [replacement_coordinate(coordinates, indices[0], policy.max_replacements, origin.ordinal)]
    return coordinates


def _validate_entry_sources(
    entry: AdmittedTrialEntryModel,
    expected: list[AdmittedSelectionRecordModel],
    descriptors: ExperimentBindingDescriptorSetModel | None,
) -> None:
    if canonical_json_bytes(
        [selection.model_dump(mode="json") for selection in entry.selections]
    ) != canonical_json_bytes([selection.model_dump(mode="json") for selection in expected]):
        raise InvalidInputError("authoring selection records differ from the admitted entry")
    expected_bindings = (
        []
        if descriptors is None
        else [
            {"descriptor": descriptor.model_dump(mode="json"), "origin": "selection"}
            for descriptor in descriptors.descriptors
            if descriptor.source_condition_id == entry.coordinate.condition_id
        ]
    )
    if canonical_json_bytes(sorted(expected_bindings, key=canonical_json_bytes)) != canonical_json_bytes(
        sorted((binding.model_dump(mode="json") for binding in entry.bindings), key=canonical_json_bytes)
    ):
        raise InvalidInputError("authoring selection bindings differ from the admitted entry")
