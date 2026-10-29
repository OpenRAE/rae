"""Read-only record production across every durable trial start."""

from __future__ import annotations

import json
from copy import deepcopy

from raes_contracts.contracts import (
    ExperimentResultSummaryModel,
    validate_admitted_trial_run,
)

from .control_plane_store_snapshots import _snapshot_from_payload
from .experiment_records import ExperimentRecordBundle, ExperimentRecordSource, ExperimentRunMetadata
from .runtime_decisions import RunPhaseDecision
from .runtime_record_assembly import assemble_run, eligible_run_ids, summarize_records
from .runtime_record_lineage import accounting_validation_record, canonical_archival_runs
from .runtime_record_versions import require_compatible_record_versions, retained_record_versions
from .runtime_trial_decisions import (
    TrialAttemptDecision,
    TrialObservationDecision,
    TrialReplacementDecision,
)


def experiment_records(experiment, *, identity, metadata=None, study=None, evidence_reader=None, archive=None):
    experiment._authorize(identity)
    with experiment._advance_lease():
        records = experiment.engine._store.load_runtime_decisions()
        sources = []
        for slot in experiment._slots(records):
            attempts = tuple(
                sorted(
                    (
                        item
                        for item in records
                        if isinstance(item, TrialAttemptDecision)
                        and item.experiment_id == experiment.experiment_id
                        and item.plan_entry_id == slot.entry.plan_entry_id
                    ),
                    key=lambda item: item.attempt,
                )
            )
            if attempts:
                sources.append(_source(experiment, slot, attempts))
        selected = {} if metadata is None else dict(metadata)
        if set(selected) - {source.run_id for source in sources}:
            raise ValueError("record metadata does not resolve to started runs")
        runs, validation_records, validation, failures = [], [], {}, {}
        canonical = canonical_archival_runs(records, experiment.experiment_id)
        history = retained_record_versions(records, experiment.experiment_id)
        owned_versions = dict(history)
        for source in sources:
            supplied = selected.get(source.run_id, ExperimentRunMetadata())
            if not isinstance(supplied, ExperimentRunMetadata):
                raise ValueError("record metadata requires its typed input model")
            try:
                supplied = ExperimentRunMetadata.model_validate(supplied.model_dump(mode="json", warnings=False))
            except ValueError:
                raise ValueError("record metadata failed validation") from None
            summaries = dict(supplied.result_summaries)
            declared = {
                item.metric_id for item in experiment.inputs.task.evaluation_protocol.metric_definitions.values()
            }
            if any(item.metric_id not in declared for item in summaries.values()):
                raise ValueError("record result metric is not declared by the admitted task")
            for metric in experiment.inputs.task.evaluation_protocol.metric_definitions.values():
                if not any(item.metric_id == metric.metric_id for item in summaries.values()):
                    summaries["missing:" + metric.metric_id] = ExperimentResultSummaryModel(
                        metric_id=metric.metric_id, value_status="missing", notes="No measured result was supplied."
                    )
            supplied = supplied.model_copy(update={"result_summaries": summaries})
            from .runtime_record_validation import validate_observed_apparatus

            validate_observed_apparatus(experiment, supplied)
            try:
                run = assemble_run(source, supplied)
            except ValueError:
                raise ValueError("record assembly rejected supplied facts") from None
            receipts = [
                attempt.cleanup_receipt
                for attempt in run.execution_accounting.attempts
                if attempt.cleanup_receipt is not None
            ]
            validate_admitted_trial_run(source.plan, run, receipts)
            run, checked = accounting_validation_record(run, canonical.get(run.run_id))
            require_compatible_record_versions(records, experiment.experiment_id, (run,), known_versions=owned_versions)
            try:
                from .runtime_record_validation import validate_run_evidence

                validate_run_evidence(experiment, source, checked, evidence_reader)
            except ValueError, OSError, RuntimeError, TypeError, AttributeError:
                # Validator inputs and provider exception messages can contain secrets.
                validation[run.run_id] = "failed"
                failures[run.run_id] = ("task-evidence-validation-failed",)
            else:
                validation[run.run_id] = "passed"
            runs.append(run)
            validation_records.append(checked)
        planned = sum(
            len(slot.plan.entries) if slot.plan is not experiment.plan else 0 for slot in experiment._slots(records)
        ) + len(experiment.plan.entries)
        # Each child plan contains one allocated replacement entry.
        replaced_ids = {
            item.parent_run.run_id
            for item in records
            if isinstance(item, TrialReplacementDecision) and item.experiment_id == experiment.experiment_id
        }
        eligible = eligible_run_ids(validation_records, validation, replaced_ids, experiment.plan.replacement_policy)
        bundle = ExperimentRecordBundle(
            runs=tuple(runs),
            sources=tuple(sources),
            accounting=summarize_records(planned, runs, sources, validation, eligible),
            validation_by_run=validation,
            validation_failures=failures,
            retained_history=tuple(artifact for key, artifact in history.items() if key[0] == "run"),
            eligible_run_ids=eligible,
            validation_records=tuple(validation_records),
        )
        if study is not None:
            from .runtime_study_records import assemble_study

            bundle = assemble_study(experiment, bundle, study, evidence_reader)
        if archive is not None:
            _publish(experiment, bundle, archive)
        return bundle


def _source(experiment, slot, attempts):
    run = experiment._run(slot.entry, slot.plan)
    decisions = run._store.load_runtime_decisions()
    ids = {item.execution_attempt_id for item in attempts}
    observations = tuple(
        sorted(
            (
                item
                for item in decisions
                if isinstance(item, TrialObservationDecision) and item.execution_attempt_id in ids
            ),
            key=lambda item: (item.execution_attempt_id, item.observation.kind),
        )
    )
    refs = {}
    for attempt in attempts:
        execution_ids = {attempt.execution_attempt_id + suffix for suffix in ("", ":apply", ":destroy")}
        refs[attempt.execution_attempt_id] = tuple(
            sorted(
                {
                    operation_id
                    for item in decisions
                    if isinstance(item, RunPhaseDecision) and item.execution_id in execution_ids
                    for operation_id in item.operation_ids
                }
            )
        )
    operations = run._store.load_records()
    snapshots = {
        item.execution_attempt_id: _snapshot_from_payload(json.loads(item.snapshot_json))
        for item in observations
        if item.observation.kind == "execution" and item.snapshot_json is not None
    }
    return ExperimentRecordSource(
        run_id=slot.entry.run_id,
        plan=slot.plan.model_copy(deep=True),
        realization=deepcopy(slot.realization),
        attempts=attempts,
        observations=observations,
        execution_snapshots=snapshots,
        operation_refs=refs,
        phase_states={
            item.execution_id + ":" + str(item.phase): item.state
            for item in decisions
            if isinstance(item, RunPhaseDecision) and item.state != "started"
        },
        operation_states={key: value.status.state.value for key, value in operations.items()},
        operation_receipts=tuple(value.receipt for value in operations.values()),
    )


def _publish(experiment, bundle, archive):
    from .runtime_record_publication import publish_records

    return publish_records(experiment, bundle, archive)
