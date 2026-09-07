"""Admitted trial plan reconciliation against archival experiment records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .._canonical import canonical_json_digest
from .admitted_trial_plan import AdmittedTrialEntryModel, AdmittedTrialPlanModel
from .experiment_analysis import validate_experiment_study_against_tasks_and_runs
from .experiment_apparatus import ExperimentTaskModel
from .experiment_run import ExperimentRunEvidenceInputs, ExperimentRunModel
from .experiment_spec import ExperimentStudyModel
from .trial_cleanup import TrialCleanupReceiptModel, validate_trial_cleanup_receipt
from .trial_provenance import TrialRunProvenanceModel


@dataclass(frozen=True)
class AdmittedTrialPlanReconciliation:
    """Plan-wide accounting of admitted entries, attempts, and archival outcomes."""

    entry_count: int
    attempted_entry_ids: tuple[str, ...]
    unattempted_entry_ids: tuple[str, ...]
    archived_entry_ids: tuple[str, ...]


def _validate_trial_terminal_outcome(
    run: ExperimentRunModel,
    terminal_receipt: TrialCleanupReceiptModel,
) -> None:
    if run.run_status in {"invalidated", "superseded"}:
        return
    expected_statuses = {
        "succeeded": {"completed", "sealed"},
        "failed": {"failed"},
        "cancelled": {"aborted"},
        "timed-out": {"failed", "aborted"},
        "aborted": {"aborted"},
    }[terminal_receipt.trial_outcome]
    if run.run_status not in expected_statuses:
        raise ValueError("archival run status does not match the terminal execution attempt")
    if terminal_receipt.trial_outcome == "succeeded" and run.outcome_status == "failed":
        raise ValueError("successful terminal attempt cannot produce a failed archival outcome")


def _validate_run_plan_linkage(
    plan: AdmittedTrialPlanModel,
    run: ExperimentRunModel,
) -> tuple[AdmittedTrialEntryModel, TrialRunProvenanceModel]:
    linkage = run.trial_provenance
    if linkage is None:
        raise ValueError("plan-aware archival run requires trial_provenance")
    if linkage.plan_id != plan.plan_id or linkage.plan_digest != plan.plan_digest:
        raise ValueError("archival run trial provenance does not match the admitted plan")
    entry = plan.entries.get(linkage.plan_entry_id)
    if entry is None:
        raise ValueError("archival run references an unknown admitted plan entry")
    if (
        linkage.entry_digest != entry.entry_digest
        or linkage.admitted_run_id != entry.run_id
        or linkage.coordinate != entry.coordinate
        or run.run_id != entry.run_id
    ):
        raise ValueError("archival run identity or coordinate does not match the admitted entry")
    if run.scenario_snapshot_ref.ref_digest != linkage.instantiated_scenario_digest:
        raise ValueError("archival run scenario snapshot does not match trial provenance")
    return entry, linkage


def _validate_run_stochastic_provenance(
    plan: AdmittedTrialPlanModel,
    entry: AdmittedTrialEntryModel,
    run: ExperimentRunModel,
) -> None:
    run_controls = {control.control_id: control for control in run.stochastic_controls}
    required_control_ids = {draw.control_id for draw in entry.stochastic_draws}
    for control_id in sorted(required_control_ids):
        if run_controls.get(control_id) != plan.stochastic_controls.get(control_id):
            raise ValueError("archival run stochastic control does not match the admitted entry")
    admitted_draws = {canonical_json_digest(draw.model_dump(mode="json")) for draw in entry.stochastic_draws}
    run_draws = {canonical_json_digest(draw.model_dump(mode="json")) for draw in run.stochastic_draws}
    if not admitted_draws.issubset(run_draws):
        raise ValueError("archival run stochastic draws do not preserve the admitted entry")


def _validate_run_attempt_evidence(
    plan: AdmittedTrialPlanModel,
    entry: AdmittedTrialEntryModel,
    linkage: TrialRunProvenanceModel,
    cleanup_receipts: list[TrialCleanupReceiptModel],
) -> TrialCleanupReceiptModel:
    receipts_by_id = {receipt.receipt_id: receipt for receipt in cleanup_receipts}
    if len(receipts_by_id) != len(cleanup_receipts):
        raise ValueError("cleanup receipt identities must be unique")
    attempt_refs = {attempt.execution_attempt_id: attempt for attempt in linkage.execution_attempts}
    for attempt_id, attempt in attempt_refs.items():
        receipt = receipts_by_id.get(attempt.cleanup_receipt_ref)
        if receipt is None or receipt.execution_attempt_id != attempt_id:
            raise ValueError("execution attempt reference does not resolve to matching cleanup evidence")
        cleanup_plan = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
        validate_trial_cleanup_receipt(cleanup_plan, receipt)
    terminal_attempt = attempt_refs[linkage.terminal_attempt_id]
    return receipts_by_id[terminal_attempt.cleanup_receipt_ref]


def validate_admitted_trial_run(
    plan: AdmittedTrialPlanModel,
    run: ExperimentRunModel,
    cleanup_receipts: list[TrialCleanupReceiptModel],
) -> None:
    """Join one archival run to its exact admitted entry and attempt evidence."""

    entry, linkage = _validate_run_plan_linkage(plan, run)
    _validate_run_stochastic_provenance(plan, entry, run)
    terminal_receipt = _validate_run_attempt_evidence(plan, entry, linkage, cleanup_receipts)
    _validate_trial_terminal_outcome(run, terminal_receipt)


def _index_cleanup_receipts(
    plan: AdmittedTrialPlanModel,
    cleanup_receipts: list[TrialCleanupReceiptModel],
) -> dict[str, list[TrialCleanupReceiptModel]]:
    receipts_by_entry: dict[str, list[TrialCleanupReceiptModel]] = {}
    seen_attempt_ids: set[str] = set()
    seen_receipt_ids: set[str] = set()
    for receipt in cleanup_receipts:
        if receipt.receipt_id in seen_receipt_ids or receipt.execution_attempt_id in seen_attempt_ids:
            raise ValueError("attempt and cleanup receipt identities must be globally unique")
        seen_receipt_ids.add(receipt.receipt_id)
        seen_attempt_ids.add(receipt.execution_attempt_id)
        entry = plan.entries.get(receipt.plan_entry_id)
        if entry is None or receipt.run_id != entry.run_id:
            raise ValueError("cleanup receipt does not resolve to an admitted plan entry")
        cleanup_plan = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
        validate_trial_cleanup_receipt(cleanup_plan, receipt)
        receipts_by_entry.setdefault(entry.plan_entry_id, []).append(receipt)
        if len(receipts_by_entry[entry.plan_entry_id]) > cleanup_plan.retry_policy.max_attempts:
            raise ValueError("execution attempts exceed the admitted retry policy")
    return receipts_by_entry


def _index_archival_runs(
    plan: AdmittedTrialPlanModel,
    runs: list[ExperimentRunModel],
    receipts_by_entry: dict[str, list[TrialCleanupReceiptModel]],
) -> dict[str, ExperimentRunModel]:
    runs_by_entry: dict[str, ExperimentRunModel] = {}
    for run in runs:
        if run.trial_provenance is None:
            raise ValueError("plan reconciliation requires trial provenance on every archival run")
        entry_id = run.trial_provenance.plan_entry_id
        if entry_id in runs_by_entry:
            raise ValueError("an admitted entry has more than one archival run")
        entry_receipts = receipts_by_entry.get(entry_id, [])
        validate_admitted_trial_run(plan, run, entry_receipts)
        referenced_receipts = {attempt.cleanup_receipt_ref for attempt in run.trial_provenance.execution_attempts}
        if referenced_receipts != {receipt.receipt_id for receipt in entry_receipts}:
            raise ValueError("archival run must account for every execution attempt on its admitted entry")
        runs_by_entry[entry_id] = run
    return runs_by_entry


def reconcile_admitted_trial_plan(
    plan: AdmittedTrialPlanModel,
    runs: list[ExperimentRunModel],
    cleanup_receipts: list[TrialCleanupReceiptModel],
) -> AdmittedTrialPlanReconciliation:
    """Account for every entry with zero or more attempts and at most one run."""

    receipts_by_entry = _index_cleanup_receipts(plan, cleanup_receipts)
    runs_by_entry = _index_archival_runs(plan, runs, receipts_by_entry)

    attempted = tuple(sorted(receipts_by_entry))
    archived = tuple(sorted(runs_by_entry))
    return AdmittedTrialPlanReconciliation(
        entry_count=len(plan.entries),
        attempted_entry_ids=attempted,
        unattempted_entry_ids=tuple(sorted(set(plan.entries) - set(receipts_by_entry))),
        archived_entry_ids=archived,
    )


def _validate_study_identity(
    plan: AdmittedTrialPlanModel,
    study: ExperimentStudyModel,
) -> None:
    study_ref = plan.input_refs.study_ref
    if study_ref is not None and (
        study_ref.ref_id != study.study_id
        or (study_ref.ref_version is not None and study_ref.ref_version != study.study_version)
    ):
        raise ValueError("study identity does not match the admitted plan")


def _validate_study_run_membership(
    study: ExperimentStudyModel,
    runs: list[ExperimentRunModel],
) -> None:
    run_member_ids = {
        member.target_ref.ref_id
        for member in study.membership.values()
        if member.role in {"calibration-run", "evaluation-run"}
    }
    linked_runs = [run for run in runs if run.trial_provenance is not None]
    missing_members = sorted(run.run_id for run in linked_runs if run.run_id not in run_member_ids)
    if missing_members:
        raise ValueError("admitted archival runs must resolve to study run membership")


def _validate_study_allocation(
    plan: AdmittedTrialPlanModel,
    study: ExperimentStudyModel,
) -> None:
    allocation = study.run_allocation
    if allocation is None:
        return
    planned_counts: dict[str, int] = {}
    for entry in plan.entries.values():
        condition_id = entry.coordinate.condition_id
        if condition_id is None:
            continue
        if condition_id not in allocation.condition_assignments:
            raise ValueError("admitted trial condition does not resolve to the study allocation")
        planned_counts[condition_id] = planned_counts.get(condition_id, 0) + 1
    over_allocated = sorted(
        condition_id for condition_id, count in planned_counts.items() if count > allocation.target_runs_per_condition
    )
    if over_allocated:
        raise ValueError("admitted trial coordinates exceed the study allocation")


def validate_admitted_trial_study(
    plan: AdmittedTrialPlanModel,
    study: ExperimentStudyModel,
    tasks: list[ExperimentTaskModel],
    runs: list[ExperimentRunModel],
    *,
    evidence_by_run: Mapping[str, ExperimentRunEvidenceInputs] | None = None,
) -> None:
    """Join admitted coordinates and archival runs to the existing study authority."""

    validate_experiment_study_against_tasks_and_runs(
        study,
        tasks,
        runs,
        evidence_by_run=evidence_by_run,
    )
    _validate_study_identity(plan, study)
    _validate_study_run_membership(study, runs)
    _validate_study_allocation(plan, study)
