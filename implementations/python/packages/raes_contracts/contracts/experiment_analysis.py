"""Experiment archival-datetime validators and study-vs-runs analysis validators."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .experiment_apparatus import (
    ExperimentStochasticControlModel,
    ExperimentTaskModel,
)
from .experiment_artifacts import (
    _experiment_reference_key,
    _format_reference,
)
from .experiment_conditions import _run_satisfies_condition_assignment
from .experiment_references import ExperimentReferenceModel
from .experiment_run import (
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
)
from .experiment_spec import ExperimentStudyModel
from .experiment_study import (
    ExperimentRunAllocationPlanModel,
    ExperimentStudyMembershipModel,
)
from .experiment_study_run_validation import validate_study_run_task_membership


def _run_model_key(run: ExperimentRunModel) -> tuple[str, str | None]:
    return (run.run_id, run.run_version)


def _task_ref_matches_task(reference: ExperimentReferenceModel, task: ExperimentTaskModel) -> bool:
    if reference.ref_digest is not None or reference.ref_path is not None:
        return False
    return (
        reference.ref_kind == "task"
        and reference.ref_id == task.task_id
        and (reference.ref_version is None or reference.ref_version == task.task_version)
    )


def _run_ref_matches_run(reference: ExperimentReferenceModel, run: ExperimentRunModel) -> bool:
    if reference.ref_digest is not None or reference.ref_path is not None:
        return False
    return (
        reference.ref_kind == "run"
        and reference.ref_id == run.run_id
        and (reference.ref_version is None or reference.ref_version == run.run_version)
    )


def _run_is_eligible_for_study_analysis(run: ExperimentRunModel) -> bool:
    return run.run_status not in {"invalidated", "superseded"} and run.outcome_status != "not-evaluated"


def _validate_study_analysis_run_eligibility(
    study: ExperimentStudyModel,
    runs: list[ExperimentRunModel],
    evaluation_run_members: list[ExperimentStudyMembershipModel],
) -> None:
    if study.analysis_plan is None:
        return

    if not evaluation_run_members:
        raise ValueError("study analysis_plan requires at least one included evaluation-run membership")

    ambiguous_run_refs: list[str] = []
    ineligible_run_refs: list[str] = []
    for member in evaluation_run_members:
        reference_label = _format_reference(member.target_ref)
        matching_runs = [run for run in runs if _run_ref_matches_run(member.target_ref, run)]
        if len(matching_runs) > 1:
            ambiguous_run_refs.append(reference_label)
            continue
        for run in matching_runs:
            if not _run_is_eligible_for_study_analysis(run):
                ineligible_run_refs.append(f"{run.run_id}:{run.run_status}:{run.outcome_status}")

    if ambiguous_run_refs:
        joined = ", ".join(sorted(ambiguous_run_refs))
        raise ValueError(
            f"study evaluation-run memberships used for analysis must resolve to one supplied run artifact: {joined}"
        )
    if ineligible_run_refs:
        joined = ", ".join(sorted(ineligible_run_refs))
        raise ValueError(
            "study evaluation-run members used for analysis must not be invalidated, superseded, or not-evaluated: "
            f"{joined}"
        )


@dataclass
class _RunAllocationCoverageState:
    """Mutable accumulator for `_validate_study_run_allocation_coverage` classification."""

    grouped_run_keys: dict[str, set[tuple[str, str | None]]]
    validated_evidence_by_run: Mapping[tuple[str, str | None], tuple[ExperimentReferenceModel, ...]] = field(
        default_factory=dict
    )
    condition_by_run_key: dict[tuple[str, str | None], str] = field(default_factory=dict)
    ungrouped_run_refs: list[str] = field(default_factory=list)
    unknown_groupings: list[str] = field(default_factory=list)
    ambiguous_run_refs: list[str] = field(default_factory=list)
    duplicate_run_assignments: list[str] = field(default_factory=list)
    ineligible_run_refs: list[str] = field(default_factory=list)
    unsatisfied_condition_runs: list[str] = field(default_factory=list)
    ambiguous_condition_runs: list[str] = field(default_factory=list)


def _classify_evaluation_run_allocation_candidate(
    run: ExperimentRunModel,
    grouping: str,
    allocation: ExperimentRunAllocationPlanModel,
    state: _RunAllocationCoverageState,
) -> None:
    run_key = _run_model_key(run)
    prior_condition = state.condition_by_run_key.get(run_key)
    if prior_condition is not None:
        state.duplicate_run_assignments.append(f"{run.run_id}:{prior_condition},{grouping}")
        return
    if not _run_is_eligible_for_study_analysis(run):
        state.ineligible_run_refs.append(f"{run.run_id}:{run.run_status}:{run.outcome_status}")
        return
    _classify_eligible_run_allocation_candidate(run, run_key, grouping, allocation, state)


def _classify_eligible_run_allocation_candidate(
    run: ExperimentRunModel,
    run_key: tuple[str, str | None],
    grouping: str,
    allocation: ExperimentRunAllocationPlanModel,
    state: _RunAllocationCoverageState,
) -> None:
    assignment = allocation.condition_assignments[grouping]
    validated_evidence = state.validated_evidence_by_run.get(run_key, ())
    missing_condition_inputs = _run_satisfies_condition_assignment(run, assignment, validated_evidence)
    if missing_condition_inputs:
        joined_missing_inputs = "|".join(sorted(missing_condition_inputs))
        state.unsatisfied_condition_runs.append(f"{run.run_id}:{grouping}:{joined_missing_inputs}")
        return
    satisfied_other_conditions = sorted(
        condition_id
        for condition_id, candidate_assignment in allocation.condition_assignments.items()
        if condition_id != grouping
        and not _run_satisfies_condition_assignment(run, candidate_assignment, validated_evidence)
    )
    if satisfied_other_conditions:
        joined_other_conditions = "|".join(satisfied_other_conditions)
        state.ambiguous_condition_runs.append(f"{run.run_id}:{grouping}:{joined_other_conditions}")
        return
    state.condition_by_run_key[run_key] = grouping
    state.grouped_run_keys[grouping].add(run_key)


def _classify_evaluation_run_allocation_member(
    member: ExperimentStudyMembershipModel,
    runs: list[ExperimentRunModel],
    allocation: ExperimentRunAllocationPlanModel,
    condition_set: set[str],
    state: _RunAllocationCoverageState,
) -> None:
    reference_label = _format_reference(member.target_ref)
    if member.grouping is None:
        state.ungrouped_run_refs.append(reference_label)
        return
    if member.grouping not in condition_set:
        state.unknown_groupings.append(f"{reference_label}:{member.grouping}")
        return
    matching_runs = [run for run in runs if _run_ref_matches_run(member.target_ref, run)]
    if len(matching_runs) > 1:
        state.ambiguous_run_refs.append(reference_label)
        return
    for run in matching_runs:
        _classify_evaluation_run_allocation_candidate(run, member.grouping, allocation, state)


def _raise_for_run_allocation_coverage_violations(
    state: _RunAllocationCoverageState,
    allocation: ExperimentRunAllocationPlanModel,
) -> None:
    if state.ungrouped_run_refs:
        joined = ", ".join(sorted(state.ungrouped_run_refs))
        raise ValueError(f"study run_allocation requires evaluation-run membership groupings: {joined}")
    if state.unknown_groupings:
        joined = ", ".join(sorted(state.unknown_groupings))
        raise ValueError(f"study evaluation-run groupings must be declared in compared_conditions: {joined}")
    if state.ambiguous_run_refs:
        joined = ", ".join(sorted(state.ambiguous_run_refs))
        raise ValueError(
            f"study evaluation-run membership references must resolve to one supplied run artifact: {joined}"
        )
    if state.duplicate_run_assignments:
        joined = ", ".join(sorted(state.duplicate_run_assignments))
        raise ValueError(f"study evaluation-run members must not assign the same run to multiple conditions: {joined}")
    if state.ineligible_run_refs:
        joined = ", ".join(sorted(state.ineligible_run_refs))
        raise ValueError(
            "study evaluation-run members used for analysis must not be invalidated, superseded, or not-evaluated: "
            f"{joined}"
        )
    if state.unsatisfied_condition_runs:
        joined = ", ".join(sorted(state.unsatisfied_condition_runs))
        raise ValueError(f"study evaluation-run members must satisfy their condition assignments: {joined}")
    if state.ambiguous_condition_runs:
        joined = ", ".join(sorted(state.ambiguous_condition_runs))
        raise ValueError(f"study evaluation-run members must satisfy exactly one condition assignment: {joined}")

    under_target_conditions = sorted(
        f"{condition}:{len(run_keys)}/{allocation.target_runs_per_condition}"
        for condition, run_keys in state.grouped_run_keys.items()
        if len(run_keys) < allocation.target_runs_per_condition
    )
    if under_target_conditions:
        joined = ", ".join(under_target_conditions)
        raise ValueError(
            f"study run_allocation target_runs_per_condition must be satisfied by included evaluation runs: {joined}"
        )


def _validate_study_run_allocation_coverage(
    study: ExperimentStudyModel,
    runs: list[ExperimentRunModel],
    evaluation_run_members: list[ExperimentStudyMembershipModel],
    validated_evidence_by_run: Mapping[tuple[str, str | None], tuple[ExperimentReferenceModel, ...]],
) -> None:
    allocation = study.run_allocation
    if allocation is None:
        return

    if not evaluation_run_members:
        raise ValueError("study run_allocation requires at least one included evaluation-run membership")

    condition_set = set(allocation.compared_conditions)
    state = _RunAllocationCoverageState(
        grouped_run_keys={condition: set() for condition in allocation.compared_conditions},
        validated_evidence_by_run=validated_evidence_by_run,
    )
    for member in evaluation_run_members:
        _classify_evaluation_run_allocation_member(member, runs, allocation, condition_set, state)

    _raise_for_run_allocation_coverage_violations(state, allocation)


def _executable_binding_identity(control: ExperimentStochasticControlModel) -> tuple[Any, ...] | None:
    binding = control.executable_binding
    if binding is None:
        return None
    return (_experiment_reference_key(binding.profile_ref), binding.namespace)


@dataclass
class _StochasticControlIdentityState:
    """Mutable accumulator for `_collect_evaluation_run_stochastic_control_identities` classification."""

    identity_by_control_id: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    unbound_control_ids: set[str] = field(default_factory=set)
    conflicting_control_ids: set[str] = field(default_factory=set)


def _record_stochastic_control_identity(
    control: ExperimentStochasticControlModel,
    state: _StochasticControlIdentityState,
) -> None:
    identity = _executable_binding_identity(control)
    if identity is None:
        state.unbound_control_ids.add(control.control_id)
        return
    prior_identity = state.identity_by_control_id.get(control.control_id)
    if prior_identity is not None and prior_identity != identity:
        state.conflicting_control_ids.add(control.control_id)
    state.identity_by_control_id[control.control_id] = identity


def _collect_evaluation_run_stochastic_control_identities(
    runs: list[ExperimentRunModel],
    evaluation_run_members: list[ExperimentStudyMembershipModel],
) -> _StochasticControlIdentityState:
    state = _StochasticControlIdentityState()
    for member in evaluation_run_members:
        for run in runs:
            if not _run_ref_matches_run(member.target_ref, run):
                continue
            for control in run.stochastic_controls:
                _record_stochastic_control_identity(control, state)
    return state


def _validate_study_run_allocation_stochastic_control_consistency(
    study: ExperimentStudyModel,
    runs: list[ExperimentRunModel],
    evaluation_run_members: list[ExperimentStudyMembershipModel],
) -> None:
    """EXP-718: runs an allocation asserts comparable must share consistent executable stream identity.

    When ``run_allocation`` compares evaluation runs across conditions, a
    stochastic control declared on more than one of those runs (matched by
    ``control_id``) is a common-random-number/controlled-variation claim: its
    executable ``profile_ref`` and ``namespace`` must agree across every run
    that declares it. A control that is descriptive-only (no
    ``executable_binding``) on *every* run that declares it makes no such
    claim and is not checked. A control that carries an ``executable_binding``
    on some but not all of the runs that declare it is an asymmetric claim --
    one run asserts a reproducible executable stream identity for it and
    another makes no claim at all -- and is rejected on the same footing as a
    mismatched ``profile_ref``/``namespace``, since it is exactly as
    unreproducible as a genuine mismatch would be.
    """

    if study.run_allocation is None:
        return
    state = _collect_evaluation_run_stochastic_control_identities(runs, evaluation_run_members)
    asymmetric_control_ids = state.conflicting_control_ids | (
        state.unbound_control_ids & state.identity_by_control_id.keys()
    )
    if asymmetric_control_ids:
        joined = ", ".join(sorted(asymmetric_control_ids))
        raise ValueError(
            "study run_allocation compared evaluation runs must use a consistent executable stochastic "
            "profile_ref and namespace for shared stochastic_controls control_id values, and either all "
            f"or none of the runs that share a control_id may carry an executable_binding: {joined}"
        )


def _resolve_and_validate_study_tasks(
    study: ExperimentStudyModel,
    tasks: list[ExperimentTaskModel],
) -> list[ExperimentTaskModel]:
    task_refs = [
        member.target_ref for member in study.membership.values() if member.role in {"primary-task", "comparison-task"}
    ]
    matched_tasks = [task for task in tasks if any(_task_ref_matches_task(reference, task) for reference in task_refs)]
    missing_task_refs = sorted(
        _format_reference(reference)
        for reference in task_refs
        if not any(_task_ref_matches_task(reference, task) for task in tasks)
    )
    if missing_task_refs:
        joined = ", ".join(missing_task_refs)
        raise ValueError(f"study task membership references must resolve to supplied task artifacts: {joined}")
    return matched_tasks


def _resolve_and_validate_study_runs(
    study: ExperimentStudyModel,
    runs: list[ExperimentRunModel],
) -> tuple[list[ExperimentRunModel], list[ExperimentStudyMembershipModel], list[ExperimentRunModel]]:
    run_refs = [
        member.target_ref
        for member in study.membership.values()
        if member.role in {"calibration-run", "evaluation-run"}
    ]
    evaluation_run_members = [member for member in study.membership.values() if member.role == "evaluation-run"]
    evaluation_run_refs = [member.target_ref for member in evaluation_run_members]
    matched_runs = [run for run in runs if any(_run_ref_matches_run(reference, run) for reference in run_refs)]
    matched_evaluation_runs = [
        run for run in runs if any(_run_ref_matches_run(reference, run) for reference in evaluation_run_refs)
    ]
    missing_run_refs = sorted(
        _format_reference(reference)
        for reference in run_refs
        if not any(_run_ref_matches_run(reference, run) for run in runs)
    )
    if run_refs and missing_run_refs:
        joined = ", ".join(missing_run_refs)
        raise ValueError(f"study run membership references must resolve to supplied run artifacts: {joined}")
    return matched_runs, evaluation_run_members, matched_evaluation_runs


def _validate_study_analysis_plan_metrics(
    study: ExperimentStudyModel,
    matched_tasks: list[ExperimentTaskModel],
    matched_evaluation_runs: list[ExperimentRunModel],
) -> None:
    if study.analysis_plan is None:
        return
    declared_metric_ids = {
        metric_id for task in matched_tasks for metric_id in task.evaluation_protocol.metric_definitions
    }
    if not declared_metric_ids:
        raise ValueError("study analysis_plan metrics require supplied task protocol artifacts")
    ungrounded_metrics = sorted(
        metric_id for metric_id in study.analysis_plan.metrics if metric_id not in declared_metric_ids
    )
    if ungrounded_metrics:
        joined = ", ".join(ungrounded_metrics)
        raise ValueError(f"study analysis_plan metrics must be declared by included task protocols: {joined}")
    missing_run_metrics = sorted(
        f"{run.run_id}:{metric_id}"
        for run in matched_evaluation_runs
        for metric_id in study.analysis_plan.metrics
        if metric_id not in {result.metric_id for result in run.result_summaries.values()}
    )
    if missing_run_metrics:
        joined = ", ".join(missing_run_metrics)
        raise ValueError(
            "study analysis_plan metrics must have result_summaries, including explicit missing/withheld "
            f"statuses, in included evaluation runs: {joined}"
        )


def _validate_experiment_study_against_tasks_and_runs(
    study: ExperimentStudyModel,
    tasks: list[ExperimentTaskModel],
    runs: list[ExperimentRunModel] | None = None,
    *,
    evidence_by_run: Mapping[str, ExperimentRunEvidenceInputs] | None,
    structural_only: bool,
) -> None:
    """Validate study-level analysis semantics against concrete task/run artifacts."""

    runs = runs or []
    matched_tasks = _resolve_and_validate_study_tasks(study, tasks)
    matched_runs, evaluation_run_members, matched_evaluation_runs = _resolve_and_validate_study_runs(study, runs)
    validated_evidence = validate_study_run_task_membership(
        matched_tasks,
        matched_runs,
        evidence_by_run,
        structural_only=structural_only,
    )

    _validate_study_analysis_run_eligibility(study, runs, evaluation_run_members)
    _validate_study_run_allocation_coverage(study, runs, evaluation_run_members, validated_evidence)
    _validate_study_run_allocation_stochastic_control_consistency(study, runs, evaluation_run_members)
    _validate_study_analysis_plan_metrics(study, matched_tasks, matched_evaluation_runs)


def validate_experiment_study_structure_against_tasks_and_runs(
    study: ExperimentStudyModel,
    tasks: list[ExperimentTaskModel],
    runs: list[ExperimentRunModel] | None = None,
) -> None:
    """Validate only structural study/task/run joins for schema composition."""

    _validate_experiment_study_against_tasks_and_runs(
        study,
        tasks,
        runs,
        evidence_by_run=None,
        structural_only=True,
    )


def validate_experiment_study_against_tasks_and_runs(
    study: ExperimentStudyModel,
    tasks: list[ExperimentTaskModel],
    runs: list[ExperimentRunModel] | None = None,
    *,
    evidence_by_run: Mapping[str, ExperimentRunEvidenceInputs] | None = None,
) -> None:
    """Validate study semantics and content-backed evidence for every claimed run."""

    _validate_experiment_study_against_tasks_and_runs(
        study,
        tasks,
        runs,
        evidence_by_run=evidence_by_run,
        structural_only=False,
    )
