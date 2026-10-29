"""Pure assembly of run records from retained starts and observed facts."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel, ExperimentRunTraceabilityModel
from raes_contracts.contracts.experiment_analysis_eligibility import experiment_run_is_analysis_eligible
from raes_contracts.contracts.experiment_execution_accounting import (
    ExperimentAttemptAccountingModel,
    ExperimentExecutionAccountingModel,
)

from .experiment_records import RUNTIME_RECORD_CLOCK, ExperimentAccounting, ExperimentRunMetadata

if TYPE_CHECKING:
    from .experiment_records import ExperimentRecordSource


def assemble_run(source: ExperimentRecordSource, metadata: ExperimentRunMetadata) -> ExperimentRunModel:
    plan = source.plan
    entry = plan.entries[source.attempts[0].plan_entry_id]
    attempts = [_assemble_attempt(source, attempt) for attempt in source.attempts]
    accounting = ExperimentExecutionAccountingModel(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        plan_entry_id=entry.plan_entry_id,
        entry_digest=entry.entry_digest,
        attempts=attempts,
        participant_configurations=list(entry.participant_configurations),
    )
    latest = attempts[-1]
    status = {
        "succeeded": "completed",
        "failed": "failed",
        "cancelled": "aborted",
        "timed-out": "failed",
        "aborted": "aborted",
        "running": "in-progress",
        "unknown": "indeterminate",
    }[latest.execution_status]
    evidence = {}
    for attempt in attempts:
        for observation in source.observations:
            if observation.execution_attempt_id != attempt.execution_attempt_id:
                continue
            for item in observation.observation.evidence:
                prior = evidence.setdefault((item.evidence_record_id, item.record_version), item)
                if prior != item:
                    raise ValueError("evidence identity conflicts across execution attempts")
    traceability = None
    if evidence and plan.input_refs.capture_spec_refs:
        traceability = ExperimentRunTraceabilityModel(
            capture_spec_refs=[
                {"ref_kind": "capture-spec", "ref_id": ref.ref_id, "ref_version": ref.ref_version}
                for ref in plan.input_refs.capture_spec_refs
            ],
            evidence_record_refs=[
                {"ref_kind": "evidence-record", "ref_id": item.evidence_record_id, "ref_version": item.record_version}
                for item in evidence.values()
            ],
        )
    if metadata.traceability is not None:
        if any((ref.ref_id, ref.ref_version) not in evidence for ref in metadata.traceability.evidence_record_refs):
            raise ValueError("scientific traceability must identify retained observed evidence")
        traceability = metadata.traceability
    payload = metadata.model_dump(mode="json", exclude={"run_version", "realized_bindings"})
    full = bool(
        latest.ended_at
        and all(item.cleanup_receipt for item in attempts)
        and (metadata.participant_implementation_provenance is not None or not entry.participant_configurations)
        and metadata.apparatus_context
        and traceability
        and metadata.evidence_artifacts
        and metadata.result_summaries
    )
    payload.update(
        schema_version="experiment-run/v1",
        record_state="archival" if full else "partial",
        execution_accounting=accounting.model_dump(mode="json"),
        run_id=entry.run_id,
        run_version=metadata.run_version,
        task_ref=plan.input_refs.task_ref.model_dump(mode="json"),
        scenario_snapshot_ref={
            "ref_kind": "scenario-snapshot",
            "ref_id": plan.input_refs.scenario_family_ref.ref_id,
            "ref_version": "raes-sdl-instantiated-snapshot/v2",
            "ref_digest": source.realization.snapshot_digest,
        },
        stochastic_controls=[item.model_dump(mode="json") for item in plan.stochastic_controls.values()],
        stochastic_draws=[item.model_dump(mode="json") for item in entry.stochastic_draws],
        started_at=attempts[0].started_at,
        ended_at=latest.ended_at,
        clock_context=RUNTIME_RECORD_CLOCK.model_dump(mode="json"),
        run_status=status,
        outcome_status=metadata.outcome_status,
        traceability=None if traceability is None else traceability.model_dump(mode="json"),
        realized_selections=[item.treatment.model_dump(mode="json") for item in entry.selections if item.treatment],
        realized_bindings=_realized_bindings(entry, latest),
    )
    extras = {item.descriptor.binding_id: item for item in metadata.realized_bindings}
    automatic = {item["descriptor"]["binding_id"]: item for item in payload["realized_bindings"]}
    if set(extras) & set(automatic):
        raise ValueError("owner-supplied bindings must not override runtime configuration observations")
    payload["realized_bindings"].extend(item.model_dump(mode="json") for item in extras.values())
    if metadata.invalidation is not None:
        payload["run_status"] = "invalidated"
    if full:
        payload["trial_provenance"] = _trial_provenance(source, entry, attempts)
    else:
        # A partial snapshot's revision depends on its facts, never export time.
        payload["run_version"] = "partial-" + canonical_json_digest(payload).split(":", 1)[1]
    return ExperimentRunModel.model_validate(payload)


def _assemble_attempt(source, attempt):
    observed = {
        item.observation.kind: item
        for item in source.observations
        if item.execution_attempt_id == attempt.execution_attempt_id
    }
    execution, capture, cleanup = (observed.get(kind) for kind in ("execution", "capture", "cleanup"))
    evidence = {}
    for item in observed.values():
        for record in item.observation.evidence:
            prior = evidence.setdefault((record.evidence_record_id, record.record_version), record)
            if prior != record:
                raise ValueError("retained evidence identity has conflicting content")
    return ExperimentAttemptAccountingModel(
        execution_attempt_id=attempt.execution_attempt_id,
        attempt=attempt.attempt,
        started_at=attempt.started_at,
        ended_at=(
            None
            if execution is None
            else max((item.observed_at for item in observed.values() if item.observed_at is not None), default=None)
        ),
        execution_status="unknown" if execution is None else execution.observation.state,
        configuration_status="observed"
        if "configuration" in observed
        else ("failed" if source.phase_states.get(attempt.execution_attempt_id + ":0") == "failed" else "unobserved"),
        capture_status=(
            "failed"
            if source.phase_states.get(attempt.execution_attempt_id + ":1") in {"failed", "cancelled"}
            else "unobserved"
            if capture is None
            else "complete"
            if capture.observation.complete
            else "partial"
        ),
        cleanup_status=(
            cleanup.observation.receipt.cleanup_status
            if cleanup is not None
            else "failed"
            if any(
                value in {"failed", "cancelled"} and key.startswith(attempt.execution_attempt_id + ":destroy:")
                for key, value in source.phase_states.items()
            )
            else "unobserved"
        ),
        cleanup_receipt=None if cleanup is None else cleanup.observation.receipt,
        operation_refs=sorted(source.operation_refs.get(attempt.execution_attempt_id, ())),
        evidence_record_refs=[
            {"ref_kind": "evidence-record", "ref_id": item.evidence_record_id, "ref_version": item.record_version}
            for item in evidence.values()
        ],
        evidence_records=list(evidence.values()) if len(evidence) <= 1024 else [],
    )


def _realized_bindings(entry, latest):
    configurations = {item.participant_address: item for item in entry.participant_configurations}
    bindings = []
    for binding in entry.bindings:
        target = binding.descriptor.target
        digest = None
        if target.plane == "participant-implementation":
            if latest.configuration_status != "observed":
                continue
            digest = configurations[target.participant_address].configuration_digest
        elif target.plane != "scenario":
            # Admission is not evidence that an apparatus setting was applied.
            continue
        bindings.append(
            {
                "descriptor": binding.descriptor.model_dump(mode="json"),
                "origin": binding.origin,
                "configuration_digest": digest,
            }
        )
    return bindings


def _trial_provenance(source, entry, attempts):
    return {
        "plan_id": source.plan.plan_id,
        "plan_digest": source.plan.plan_digest,
        "plan_entry_id": entry.plan_entry_id,
        "entry_digest": entry.entry_digest,
        "admitted_run_id": entry.run_id,
        "coordinate": entry.coordinate.model_dump(mode="json"),
        "instantiated_scenario_digest": source.realization.snapshot_digest,
        "processor_plan_refs": [item.model_dump(mode="json") for item in source.realization.processor_plan_refs],
        "execution_attempts": [
            {
                "execution_attempt_id": item.execution_attempt_id,
                "cleanup_receipt_ref": item.cleanup_receipt.receipt_id,
                "operation_refs": item.operation_refs,
            }
            for item in attempts
        ],
        "terminal_attempt_id": attempts[-1].execution_attempt_id,
    }


def eligible_run_ids(runs, validation, replaced_ids, replacement_policy):
    return frozenset(
        run.run_id
        for run in runs
        if validation[run.run_id] == "passed"
        and run.run_id not in replaced_ids
        and experiment_run_is_analysis_eligible(run, replacement_policy)
    )


def summarize_records(planned, runs, sources, validation, eligible_ids):
    all_attempts = [attempt for run in runs for attempt in run.execution_accounting.attempts]
    latest = [run.execution_accounting.attempts[-1] for run in runs]
    unresolved = sum(item.execution_status in {"unknown", "running"} for item in latest)
    metrics = {}
    for run in runs:
        by_metric = {}
        for result in run.result_summaries.values():
            by_metric.setdefault(result.metric_id, []).append(result)
        for metric_id, values in by_metric.items():
            population = metrics.setdefault(metric_id, Counter())
            population["started_runs"] += 1
            population["eligible_runs"] += int(run.run_id in eligible_ids)
            population["reported_results"] += sum(value.value_status == "reported" for value in values)
            population["reported_runs"] += int(any(value.value_status == "reported" for value in values))
            population["missing_runs"] += int(all(value.value_status == "missing" for value in values))
            population["withheld_runs"] += int(any(value.value_status == "withheld" for value in values))
    return ExperimentAccounting(
        planned_runs=planned,
        started_runs=len(runs),
        unstarted_runs=planned - len(runs),
        resolved_runs=len(runs) - unresolved,
        unresolved_runs=unresolved,
        attempts=len(all_attempts),
        retry_attempts=len(all_attempts) - len(runs),
        replacement_runs=sum(source.plan.replacement_origin is not None for source in sources),
        run_outcomes=dict(Counter(run.run_status for run in runs)),
        scientific_outcomes=dict(Counter(run.outcome_status for run in runs)),
        execution_outcomes=dict(Counter(item.execution_status for item in all_attempts)),
        capture_outcomes=dict(Counter(item.capture_status for item in all_attempts)),
        cleanup_outcomes=dict(Counter(item.cleanup_status for item in all_attempts)),
        validation_outcomes=dict(Counter(validation.values())),
        metric_populations=metrics,
    )
