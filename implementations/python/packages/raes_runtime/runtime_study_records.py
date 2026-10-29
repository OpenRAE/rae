"""Study assembly preserves authored policy and all started-run membership."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentStudyModel,
    TrialReplacementStudyInputs,
    validate_admitted_trial_study,
    validate_replacement_trial_study,
)

from .experiment_records import ExperimentRecordBundle
from .runtime_record_decisions import ExperimentStudyDefinitionDecision
from .runtime_record_validation import with_record_evidence
from .runtime_trial_decisions import TrialArchiveCandidateDecision, TrialArchiveDecision, TrialReplacementDecision

if TYPE_CHECKING:
    from .experiment_records import ExperimentEvidenceReader, ExperimentRecordSource
    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment import RuntimeExperiment


def assemble_study(
    experiment: RuntimeExperiment,
    bundle: ExperimentRecordBundle,
    definition: ExperimentStudyModel,
    evidence_reader: ExperimentEvidenceReader | None,
) -> ExperimentRecordBundle:
    definition = _authored_definition(experiment, definition)
    study = _study_snapshot(bundle, definition)
    validation_records = {run.run_id: run for run in bundle.validation_records}
    experiment.engine._store.claim_runtime_decision(
        ExperimentStudyDefinitionDecision(experiment_id=experiment.experiment_id, study=definition)
    )
    failures = dict(bundle.validation_failures)
    status = "passed"
    selected = [
        (source, validation_records[run.run_id])
        for source, run in zip(bundle.sources, bundle.runs, strict=True)
        if run.run_id in bundle.eligible_run_ids
    ]
    try:
        if bundle.runs and not selected:
            raise ValueError("study has no validated evaluation runs")
        with_record_evidence(
            experiment,
            selected,
            evidence_reader,
            lambda evidence: _validate_study(experiment, bundle, study, definition, selected, evidence),
        )
    except ValueError, OSError, RuntimeError, TypeError, AttributeError:
        status = "failed"
        failures["study"] = ("study-validation-failed",)
    return cast(
        ExperimentRecordBundle, replace(bundle, study=study, study_validation=status, validation_failures=failures)
    )


def _authored_definition(experiment: RuntimeExperiment, definition: ExperimentStudyModel) -> ExperimentStudyModel:
    try:
        definition = ExperimentStudyModel.model_validate(definition.model_dump(mode="json", warnings=False))
    except ValueError:
        raise ValueError("authored study definition failed validation") from None
    if definition.definition_ref is not None:
        raise ValueError("authored study definition must not be a generated snapshot")
    reference = experiment.plan.input_refs.study_ref
    if reference is not None and (
        reference.ref_id != definition.study_id
        or (reference.ref_version is not None and reference.ref_version != definition.study_version)
    ):
        raise ValueError("authored study definition does not match the admitted plan")
    return definition


def _study_snapshot(bundle: ExperimentRecordBundle, definition: ExperimentStudyModel) -> ExperimentStudyModel:
    payload = definition.model_dump(mode="json")
    membership = dict(payload["membership"])
    validation_records = {run.run_id: run for run in bundle.validation_records}
    for source, run in zip(bundle.sources, bundle.runs, strict=True):
        _add_run_membership(membership, bundle, source, run, validation_records)
    payload["definition_ref"] = {
        "ref_kind": "study",
        "ref_id": definition.study_id,
        "ref_version": definition.study_version,
        "ref_digest": canonical_json_digest(definition.model_dump(mode="json")),
    }
    payload["membership"] = membership
    payload["study_version"] = definition.study_version + "-" + canonical_json_digest(payload).split(":", 1)[1]
    return ExperimentStudyModel.model_validate(payload)


def _add_run_membership(
    membership: dict[str, Any],
    bundle: ExperimentRecordBundle,
    source: ExperimentRecordSource,
    run: ExperimentRunModel,
    validation_records: Mapping[str, ExperimentRunModel],
) -> None:
    entry = source.plan.entries[run.execution_accounting.plan_entry_id]
    eligible = run.run_id in bundle.eligible_run_ids
    checked = validation_records[run.run_id] if eligible else run
    key = "runtime:" + run.run_id
    if key in membership:
        raise ValueError("authored study membership collides with produced run membership")
    membership[key] = {
        "target_ref": {"ref_kind": "run", "ref_id": checked.run_id, "ref_version": checked.run_version},
        "role": "evaluation-run" if eligible else "other",
        "grouping": entry.coordinate.condition_id,
        "inclusion_rationale": "Validated evaluation run."
        if eligible
        else "Retained execution; scientific eligibility not established.",
    }
    if checked.run_version != run.run_version:
        accounting_key = key + ":accounting"
        if accounting_key in membership:
            raise ValueError("authored study membership collides with produced accounting membership")
        membership[accounting_key] = {
            "target_ref": {"ref_kind": "run", "ref_id": run.run_id, "ref_version": run.run_version},
            "role": "other",
            "grouping": entry.coordinate.condition_id,
            "inclusion_rationale": "Additional accounting linked to the exact evaluation artifact.",
        }


def _validate_study(
    experiment: RuntimeExperiment,
    bundle: ExperimentRecordBundle,
    study: ExperimentStudyModel,
    definition: ExperimentStudyModel,
    selected: list[tuple[ExperimentRecordSource, ExperimentRunModel]],
    evidence: Mapping[str, ExperimentRunEvidenceInputs | None],
) -> None:
    selected_runs = [run for _, run in selected]
    records = experiment.engine._store.load_runtime_decisions()
    changes = [
        item
        for item in records
        if isinstance(item, TrialReplacementDecision) and item.experiment_id == experiment.experiment_id
    ]
    kwargs = {
        "study_definition": definition,
        "relation_scenarios": {experiment.inputs.family.name: experiment.inputs.family},
        "relation_capture_specs": experiment.inputs.capture_specs,
    }
    if experiment.plan.replacement_policy is not None and experiment.plan.replacement_policy.max_replacements:
        validate_replacement_trial_study(
            experiment.plan,
            study,
            [experiment.inputs.task],
            _replacement_runs(records, experiment.experiment_id, changes, selected_runs),
            inputs=TrialReplacementStudyInputs(
                replacement_plans=[item.plan for item in changes],
                cleanup_receipts=[
                    attempt.cleanup_receipt
                    for run in bundle.runs
                    for attempt in run.execution_accounting.attempts
                    if attempt.cleanup_receipt is not None
                ],
                evidence_by_run=evidence,
                **kwargs,
            ),
        )
    else:
        validate_admitted_trial_study(
            experiment.plan, study, [experiment.inputs.task], selected_runs, evidence_by_run=evidence, **kwargs
        )


def _replacement_runs(
    records: tuple[RuntimeDecision, ...],
    experiment_id: str,
    changes: list[TrialReplacementDecision],
    selected_runs: list[ExperimentRunModel],
) -> list[ExperimentRunModel]:
    history = [run for change in changes for run in (change.parent_run, change.superseded_run)]
    history.extend(
        item.run
        for item in records
        if isinstance(item, (TrialArchiveCandidateDecision, TrialArchiveDecision))
        and item.experiment_id == experiment_id
    )
    unique = {(run.run_id, run.run_version): run for run in history}
    for run in selected_runs:
        key = (run.run_id, run.run_version)
        if key in unique and unique[key] != run:
            raise ValueError("study run version conflicts with retained replacement history")
        unique[key] = run
    return list(unique.values())
