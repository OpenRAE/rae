"""Descriptor admission and resolved selection bindings for trial compilation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from raes import ExpandedScenarioBindingTargetResolver
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedBindingModel,
    AdmittedParticipantManifestReferenceModel,
    ExperimentBindingDescriptorModel,
    ExperimentSelectionMemberOutcomeModel,
    ExperimentSelectionReferenceOutcomeModel,
    LiteralBindingValueModel,
    ParticipantImplementationManifestModel,
    TrialCoordinateModel,
)
from raes_contracts.contracts.experiment_bindings import ParticipantConfigurationResultModel
from raes_contracts.experiment_bindings import (
    ApparatusManifest,
    ApparatusManifestKey,
    ParticipantManifestKey,
    validate_experiment_binding_targets,
)
from raes_contracts.participant_configuration import ConfigurationOverrideModel, realize_participant_configuration

from .models import CompilationFailure, TrialCompilationRequest
from .policies import CoordinateSelections, ResolvedSelection

_BINDING_DESCRIPTORS_ADDRESS = "/binding_descriptors"


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
        value = getattr(member, "reference", None)
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
    *,
    descriptor_ids: set[str] | None = None,
) -> dict[str, ExperimentBindingDescriptorModel]:
    descriptors = request.experiment.binding_descriptors
    if descriptors is None:
        return {}
    if descriptor_ids is not None:
        selected = [descriptor for descriptor in descriptors.descriptors if descriptor.binding_id in descriptor_ids]
        if not selected:
            return {}
        descriptors = descriptors.model_copy(update={"descriptors": selected})
    try:
        admitted = validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=ExpandedScenarioBindingTargetResolver(request.family),
            participant_manifests=participant_manifests,
            apparatus_manifests=apparatus_manifests,
        )
    except ValueError as exc:
        raise CompilationFailure(
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
    if request.experiment.factorial_design is not None:
        bindings = _factorial_entry_bindings(request, row, coordinate, descriptors)
    else:
        bindings = _selection_entry_bindings(request, row, coordinate, descriptors)
        bindings.extend(
            AdmittedBindingModel(descriptor=descriptor, origin="selection")
            for descriptor in sorted(descriptors.values(), key=lambda descriptor: descriptor.binding_id)
            if descriptor.source_condition_id == coordinate.condition_id
            and descriptor.target.plane == "participant-implementation"
        )
    if len({binding.descriptor.binding_id for binding in bindings}) != len(bindings):
        raise CompilationFailure(
            "binding-duplicate",
            _BINDING_DESCRIPTORS_ADDRESS,
            "an admitted binding descriptor is selected more than once",
        )
    if len(bindings) > request.limits.max_bindings_per_entry:
        raise CompilationFailure(
            "binding-limit-exceeded",
            _BINDING_DESCRIPTORS_ADDRESS,
            "entry bindings exceed the compilation limit",
        )
    return bindings


def _factorial_entry_bindings(
    request: TrialCompilationRequest,
    row: CoordinateSelections,
    coordinate: TrialCoordinateModel,
    descriptors: Mapping[str, ExperimentBindingDescriptorModel],
) -> list[AdmittedBindingModel]:
    bindings: list[AdmittedBindingModel] = []
    for descriptor in sorted(descriptors.values(), key=lambda descriptor: descriptor.binding_id):
        if descriptor.source_condition_id != coordinate.condition_id:
            continue
        if descriptor.target.plane == "scenario" and not any(
            _descriptor_matches_selection(request, descriptor, selection) for selection in row.selections
        ):
            raise CompilationFailure(
                "binding-selection-mismatch",
                _BINDING_DESCRIPTORS_ADDRESS,
                "factorial binding differs from the selected scenario outcome",
            )
        bindings.append(AdmittedBindingModel(descriptor=descriptor, origin="selection"))
    return bindings


def _selection_entry_bindings(
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
                raise CompilationFailure(
                    "binding-selection-mismatch",
                    f"{_BINDING_DESCRIPTORS_ADDRESS}/{descriptor_id}",
                    "a binding descriptor does not equal its selected variation outcome",
                )
            bindings.append(AdmittedBindingModel(descriptor=descriptor, origin="selection"))
    return bindings


def entry_participant_configurations(
    request: TrialCompilationRequest,
    bindings: list[AdmittedBindingModel],
    participant_manifest_refs: Sequence[AdmittedParticipantManifestReferenceModel],
) -> list[ParticipantConfigurationResultModel]:
    """Realize each bound participant's complete configuration atomically."""

    selected = {
        (ref.participant_address, ref.implementation_name, ref.implementation_version, ref.manifest_version)
        for ref in participant_manifest_refs
    }
    grouped = _factorial_participant_defaults(request, selected)
    for binding in bindings:
        descriptor = binding.descriptor
        target = descriptor.target
        if target.plane != "participant-implementation":
            continue
        key = (
            target.participant_address,
            target.implementation_name,
            target.implementation_version,
            target.manifest_version,
        )
        grouped.setdefault(key, []).append(
            ConfigurationOverrideModel(target_id=target.target_id, value=descriptor.value)
        )
    if len(grouped) > request.limits.max_bindings_per_entry:
        raise CompilationFailure(
            "participant-configuration-limit-exceeded",
            _BINDING_DESCRIPTORS_ADDRESS,
            "participant configuration count exceeds the compilation limit",
        )
    results = []
    for key, overrides in sorted(grouped.items()):
        manifest = request.participant_manifests[key]
        registry = manifest.configuration_registry
        try:
            results.append(
                realize_participant_configuration(
                    participant_address=key[0],
                    manifest=manifest,
                    manifest_ref=manifest.identity.name,
                    manifest_digest=canonical_json_digest(manifest.model_dump(mode="json")),
                    overrides=overrides,
                    validator=request.participant_configuration_validators.get(
                        (registry.owner.validator_id, registry.owner.validator_version)
                    ),
                )
            )
        except ValueError as exc:
            raise CompilationFailure(
                "participant-configuration-rejected",
                _BINDING_DESCRIPTORS_ADDRESS,
                "participant complete configuration failed owner validation",
            ) from exc
    return results


def _factorial_participant_defaults(
    request: TrialCompilationRequest,
    selected: set[ParticipantManifestKey],
) -> dict[ParticipantManifestKey, list[ConfigurationOverrideModel]]:
    grouped = {}
    if request.experiment.factorial_design is None:
        return grouped
    for descriptor in request.experiment.binding_descriptors.descriptors:
        target = descriptor.target
        if target.plane != "participant-implementation":
            continue
        key = (
            target.participant_address,
            target.implementation_name,
            target.implementation_version,
            target.manifest_version,
        )
        if key in selected:
            grouped.setdefault(key, [])
    return grouped
