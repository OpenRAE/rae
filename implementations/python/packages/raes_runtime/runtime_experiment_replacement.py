"""Author-directed fresh trials through the incumbent compiler and archive owner."""

from dataclasses import dataclass
from typing import Protocol

from raes_contracts.contracts import ExperimentRunModel, validate_admitted_trial_run
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan
from raes_processor.trial_compiler.replacement import TrialReplacementResult, compile_replacement_trial

from .runtime_trial_decisions import TrialArchiveDecision, TrialReplacementDecision


class TrialArchiveOwner(Protocol):
    """Installed archival producer; immutable write and exact readback are required."""

    def build_run(self, request, realization, results) -> ExperimentRunModel: ...
    def write_run(self, run: ExperimentRunModel) -> None: ...
    def read_run(self, run_id: str, run_version: str) -> ExperimentRunModel: ...


@dataclass(frozen=True)
class ExperimentReplacementBinding:
    compilation_request: TrialCompilationRequest
    archive: TrialArchiveOwner

    def require_root(self, plan):
        result = compile_admitted_trial_plan(self.compilation_request)
        if result.plan is None or result.plan.model_dump(mode="json") != plan.model_dump(mode="json"):
            raise ValueError("replacement requires the exact original compilation request")
        if not all(callable(getattr(self.archive, name, None)) for name in ("build_run", "write_run", "read_run")):
            raise ValueError("replacement requires an installed immutable archive owner")


def _write_archive(owner, run):
    owner.write_run(run)
    observed = owner.read_run(run.run_id, run.run_version)
    if ExperimentRunModel.model_validate(observed.model_dump(mode="json")) != run:
        raise ValueError("archive readback differs from the committed trial run")


def archive_and_replace(experiment, slot, unit, records, *, allow_replacement=True):
    binding = experiment.replacement
    if binding is None:
        return False
    engine, archive = experiment.engine, binding.archive
    prior = next(
        (
            record
            for record in records
            if isinstance(record, TrialArchiveDecision)
            and record.experiment_id == experiment.experiment_id
            and record.run.run_id == unit.request.run_id
        ),
        None,
    )
    attempts = sorted(
        (item for item in experiment._units.values() if item.request.run_id == unit.request.run_id),
        key=lambda item: item.attempt.attempt,
    )
    if prior is None:
        results = tuple(item.result() for item in attempts)
        receipts = tuple(result.cleanup_receipt for result in results)
        run = engine._execution_adapter.call(
            "control",
            archive.build_run,
            unit.request,
            unit.realization,
            results,
            timeout_ms=engine._supervision.observation_ms,
        )
        run = ExperimentRunModel.model_validate(run.model_dump(mode="json"))
        validate_admitted_trial_run(slot.plan, run, list(receipts))
        expected_attempts = [
            (
                result.cleanup_receipt.execution_attempt_id,
                result.cleanup_receipt.receipt_id,
                frozenset(receipt.operation_id for receipt in result.operation_receipts),
            )
            for result in results
        ]
        if [
            (item.execution_attempt_id, item.cleanup_receipt_ref, frozenset(item.operation_refs))
            for item in run.trial_provenance.execution_attempts
        ] != expected_attempts:
            raise ValueError("archive does not retain all runtime attempts")
        terminal = results[-1].cleanup_receipt.trial_outcome
        if terminal != "succeeded" and run.outcome_status == "succeeded":
            raise ValueError("archive changed the runtime execution outcome")
        if not unit.capture_succeeded() and run.run_status == "completed":
            raise ValueError("archive hides a failed capture")
        engine._execution_adapter.call(
            "control", _write_archive, archive, run, timeout_ms=engine._supervision.commit_ms
        )
        prior = TrialArchiveDecision(experiment_id=experiment.experiment_id, run=run)
        engine._store.claim_runtime_decision(prior)
    else:
        run = prior.run
    policy = experiment.plan.replacement_policy
    if policy is None or not allow_replacement:
        return False
    history = sorted(
        (
            record
            for record in records
            if isinstance(record, TrialReplacementDecision)
            and record.experiment_id == experiment.experiment_id
            and record.root_entry_id == slot.root_entry_id
        ),
        key=lambda item: item.ordinal,
    )
    # Resume an already committed child after archive or dispatch interruption.
    child = next((item for item in history if item.parent_run.run_id == run.run_id), None)
    if child is not None:
        engine._execution_adapter.call(
            "control", _write_archive, archive, child.superseded_run, timeout_ms=engine._supervision.commit_ms
        )
        return False
    if run.run_status not in policy.replace_on or len(history) >= policy.max_replacements:
        return False
    previous = tuple(
        TrialReplacementResult(
            item.plan, item.superseded_run, parent_run=item.parent_run, cleanup_receipts=item.cleanup_receipts
        )
        for item in history
    )
    receipts = tuple(item.result().cleanup_receipt for item in attempts)
    result = compile_replacement_trial(
        binding.compilation_request,
        original_plan=experiment.plan,
        root_entry_id=slot.root_entry_id,
        previous_allocations=previous,
        failed_run=run,
        cleanup_receipts=receipts,
    )
    if result.plan is None:
        raise ValueError("replacement compiler refused the recorded runtime outcome")
    child = TrialReplacementDecision(
        experiment_id=experiment.experiment_id,
        root_entry_id=slot.root_entry_id,
        ordinal=result.plan.replacement_origin.ordinal,
        plan=result.plan,
        superseded_run=result.superseded_run,
        parent_run=run,
        cleanup_receipts=receipts,
    )
    # The ordinal and child identity commit before archive publication or effects.
    engine._store.claim_runtime_decision(child)
    engine._execution_adapter.call(
        "control", _write_archive, archive, child.superseded_run, timeout_ms=engine._supervision.commit_ms
    )
    return True
