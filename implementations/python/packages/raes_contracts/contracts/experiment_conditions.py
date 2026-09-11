"""Experiment condition-assignment / run matching helpers for study analysis."""

from __future__ import annotations

import json
from collections.abc import Callable, Collection

from .base import _canonical_digest
from .experiment_apparatus import ExperimentApparatusComponentModel
from .experiment_artifacts import (
    _format_reference,
    _identity_matches_reference,
    _reference_satisfies_requirement,
)
from .experiment_references import ExperimentParameterModel, ExperimentReferenceModel
from .experiment_run import ExperimentRunModel
from .experiment_study import ExperimentConditionAssignmentModel
from .participant_manifests import ParticipantImplementationSelectionModel


def _component_identity_matches_reference(
    component: ExperimentApparatusComponentModel,
    reference: ExperimentReferenceModel,
) -> bool:
    return component.component_kind == reference.ref_kind and _identity_matches_reference(component.identity, reference)


def _participant_selection_matches_reference(
    selection: ParticipantImplementationSelectionModel,
    reference: ExperimentReferenceModel,
) -> bool:
    return reference.ref_kind == "participant-implementation" and _identity_matches_reference(
        selection.implementation_identity,
        reference,
    )


def _reference_in_collection(
    references: list[ExperimentReferenceModel],
    requirement: ExperimentReferenceModel,
) -> bool:
    return any(_reference_satisfies_requirement(reference, requirement) for reference in references)


def _condition_reference_matches_processor_or_backend(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    return any(
        _component_identity_matches_reference(component, requirement)
        for component in run.apparatus_context.components.values()
    )


def _condition_reference_matches_participant_implementation(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    provenance = run.participant_implementation_provenance
    if provenance is None:
        return False
    return any(
        _participant_selection_matches_reference(selection, requirement)
        for selection in provenance.participant_implementations
    )


def _condition_reference_matches_task(run: ExperimentRunModel, requirement: ExperimentReferenceModel) -> bool:
    return _reference_satisfies_requirement(run.task_ref, requirement)


def _condition_reference_matches_scenario_snapshot(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    return _reference_satisfies_requirement(run.scenario_snapshot_ref, requirement)


def _condition_reference_matches_apparatus_context(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    apparatus_context = run.apparatus_context
    apparatus_context_ref = ExperimentReferenceModel(
        ref_kind="apparatus-context",
        ref_id=apparatus_context.apparatus_context_id,
        ref_version=apparatus_context.context_version,
    )
    return _reference_satisfies_requirement(apparatus_context_ref, requirement)


def _condition_reference_matches_manifest(run: ExperimentRunModel, requirement: ExperimentReferenceModel) -> bool:
    return any(
        _reference_satisfies_requirement(selected_manifest, requirement)
        for selected_manifest in run.apparatus_context.selected_manifests
    )


def _condition_reference_matches_profile_or_capability(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    apparatus_context = run.apparatus_context
    component_refs = [
        reference for component in apparatus_context.components.values() for reference in component.compatibility_refs
    ]
    return _reference_in_collection(
        apparatus_context.compatibility_declarations, requirement
    ) or _reference_in_collection(
        component_refs,
        requirement,
    )


def _condition_reference_matches_measurement_channel(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    return _reference_in_collection(run.apparatus_context.measurement_channels, requirement)


def _condition_reference_matches_default_refs(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
) -> bool:
    return (
        _reference_in_collection(run.used_refs, requirement)
        or _reference_in_collection(run.generated_refs, requirement)
        or _reference_in_collection(run.derived_from_refs, requirement)
    )


_CONDITION_REFERENCE_HANDLERS_BY_REF_KIND: dict[
    str,
    Callable[[ExperimentRunModel, ExperimentReferenceModel], bool],
] = {
    "processor": _condition_reference_matches_processor_or_backend,
    "backend": _condition_reference_matches_processor_or_backend,
    "participant-implementation": _condition_reference_matches_participant_implementation,
    "task": _condition_reference_matches_task,
    "scenario-snapshot": _condition_reference_matches_scenario_snapshot,
    "apparatus-context": _condition_reference_matches_apparatus_context,
    "manifest": _condition_reference_matches_manifest,
    "profile": _condition_reference_matches_profile_or_capability,
    "capability": _condition_reference_matches_profile_or_capability,
    "measurement-channel": _condition_reference_matches_measurement_channel,
}


def _run_satisfies_condition_reference(
    run: ExperimentRunModel,
    requirement: ExperimentReferenceModel,
    validated_evidence_refs: Collection[ExperimentReferenceModel],
) -> bool:
    if requirement.ref_kind == "evidence":
        return _reference_in_collection(list(validated_evidence_refs), requirement)
    handler = _CONDITION_REFERENCE_HANDLERS_BY_REF_KIND.get(
        requirement.ref_kind, _condition_reference_matches_default_refs
    )
    return handler(run, requirement)


def _parameter_satisfies_requirement(
    parameter: ExperimentParameterModel,
    requirement: ExperimentParameterModel,
) -> bool:
    return (
        parameter.name == requirement.name
        and parameter.value_kind == requirement.value_kind
        and parameter.value == requirement.value
    )


def _condition_assignment_run_criteria_signature(
    assignment: ExperimentConditionAssignmentModel,
) -> tuple[
    tuple[tuple[str, str, str | None, str | None, str | None], ...],
    tuple[tuple[str, str, str, str], ...],
    str,
    str | None,
]:
    reference_signature = tuple(
        sorted(
            (
                reference.ref_kind,
                reference.ref_id,
                reference.ref_version,
                _canonical_digest(reference.ref_digest),
                reference.ref_path,
            )
            for reference in assignment.required_refs
        )
    )
    parameter_signature = tuple(
        sorted(
            (
                parameter.name,
                parameter.value_kind,
                type(parameter.value).__name__,
                json.dumps(parameter.value, sort_keys=True, separators=(",", ":")),
            )
            for parameter in assignment.required_parameters
        )
    )
    return (
        reference_signature,
        parameter_signature,
        assignment.difficulty_condition,
        assignment.difficulty_policy_id,
    )


def _run_satisfies_condition_assignment(
    run: ExperimentRunModel,
    assignment: ExperimentConditionAssignmentModel,
    validated_evidence_refs: Collection[ExperimentReferenceModel] = (),
) -> list[str]:
    missing: list[str] = []
    missing.extend(
        _format_reference(reference)
        for reference in assignment.required_refs
        if not _run_satisfies_condition_reference(run, reference, validated_evidence_refs)
    )
    run_parameters = [*run.parameter_set, *run.apparatus_context.configuration_parameters]
    missing.extend(
        f"parameter:{parameter.name}:{parameter.value_kind}"
        for parameter in assignment.required_parameters
        if not any(_parameter_satisfies_requirement(candidate, parameter) for candidate in run_parameters)
    )
    run_condition = run.difficulty_provenance.policy.condition if run.difficulty_provenance is not None else "fixed"
    run_policy_id = run.difficulty_provenance.policy.policy_id if run.difficulty_provenance is not None else None
    if run_condition != assignment.difficulty_condition:
        missing.append(f"difficulty-condition:{assignment.difficulty_condition}")
    if assignment.difficulty_policy_id is not None and run_policy_id != assignment.difficulty_policy_id:
        missing.append(f"difficulty-policy:{assignment.difficulty_policy_id}")
    return missing
