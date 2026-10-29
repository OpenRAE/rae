"""Author-directed fresh trials through the incumbent compiler and archive owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel, validate_admitted_trial_run
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan
from raes_processor.trial_compiler.replacement import TrialReplacementResult, compile_replacement_trial

from .runtime_record_versions import require_compatible_record_versions
from .runtime_trial_decisions import TrialArchiveCandidateDecision, TrialArchiveDecision, TrialReplacementDecision

if TYPE_CHECKING:
    from raes_contracts.contracts import AdmittedTrialPlanModel
    from raes_contracts.trial_unit import TrialUnitRequest, TrialUnitResult
    from raes_processor.trial_realization import TrialRealization

    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment import RuntimeExperiment, TrialSlot
    from .runtime_trial_unit import RuntimeTrialUnit


class TrialArchiveOwner(Protocol):
    """Installed archival producer; immutable write and exact readback are required."""

    def build_run(
        self, request: TrialUnitRequest, realization: TrialRealization, results: tuple[TrialUnitResult, ...]
    ) -> ExperimentRunModel: ...
    def write_run(self, run: ExperimentRunModel) -> None: ...
    def read_run(self, run_id: str, run_version: str) -> ExperimentRunModel: ...


@dataclass(frozen=True)
class ExperimentReplacementBinding:
    compilation_request: TrialCompilationRequest
    archive: TrialArchiveOwner

    def require_root(self, plan: AdmittedTrialPlanModel) -> None:
        result = compile_admitted_trial_plan(self.compilation_request)
        if result.plan is None or result.plan.model_dump(mode="json") != plan.model_dump(mode="json"):
            raise ValueError("replacement requires the exact original compilation request")
        if not all(callable(getattr(self.archive, name, None)) for name in ("build_run", "write_run", "read_run")):
            raise ValueError("replacement requires an installed immutable archive owner")


def _write_archive(owner: TrialArchiveOwner, run: ExperimentRunModel) -> None:
    expected = canonical_json_digest(run.model_dump(mode="json"))
    owner.write_run(run.model_copy(deep=True))
    observed = owner.read_run(run.run_id, run.run_version)
    if (
        canonical_json_digest(
            ExperimentRunModel.model_validate(observed.model_dump(mode="json")).model_dump(mode="json")
        )
        != expected
    ):
        raise ValueError("archive readback differs from the committed trial run")


def archive_and_replace(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    unit: RuntimeTrialUnit,
    records: tuple[RuntimeDecision, ...],
    *,
    allow_replacement: bool = True,
) -> bool:
    binding = experiment.replacement
    if binding is None:
        return False
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
    attempts = _run_attempts(experiment, unit.request.run_id)
    if prior is None:
        prior = _archive_attempts(experiment, slot, unit, attempts)
    policy = experiment.plan.replacement_policy
    if policy is None or not allow_replacement:
        return False
    return _replace_archived_run(experiment, slot, prior.run, attempts, records)


def _run_attempts(experiment: RuntimeExperiment, run_id: str) -> tuple[RuntimeTrialUnit, ...]:
    return tuple(
        sorted(
            (item for item in experiment._units.values() if item.request.run_id == run_id),
            key=lambda item: item.attempt.attempt,
        )
    )


def _archive_attempts(
    experiment: RuntimeExperiment, slot: TrialSlot, unit: RuntimeTrialUnit, attempts: tuple[RuntimeTrialUnit, ...]
) -> TrialArchiveDecision:
    engine, archive = experiment.engine, experiment.replacement.archive
    results = tuple(item.result() for item in attempts)
    frozen = next(
        (
            item
            for item in engine._store.load_runtime_decisions()
            if isinstance(item, TrialArchiveCandidateDecision)
            and item.experiment_id == experiment.experiment_id
            and item.run.run_id == unit.request.run_id
        ),
        None,
    )
    run = (
        frozen.run
        if frozen is not None
        else engine._execution_adapter.call(
            "control",
            archive.build_run,
            unit.request,
            unit.realization,
            results,
            timeout_ms=engine._supervision.observation_ms,
        )
    )
    run = ExperimentRunModel.model_validate(run.model_dump(mode="json"))
    validate_admitted_trial_run(slot.plan, run, [result.cleanup_receipt for result in results])
    _validate_archive_attempts(run, results)
    if not unit.capture_succeeded() and run.run_status == "completed":
        raise ValueError("archive hides a failed capture")
    require_compatible_record_versions(engine._store.load_runtime_decisions(), experiment.experiment_id, (run,))
    engine._store.claim_runtime_decision(TrialArchiveCandidateDecision(experiment_id=experiment.experiment_id, run=run))
    engine._execution_adapter.call("control", _write_archive, archive, run, timeout_ms=engine._supervision.commit_ms)
    prior = TrialArchiveDecision(experiment_id=experiment.experiment_id, run=run)
    engine._store.claim_runtime_decision(prior)
    return prior


def _validate_archive_attempts(run: ExperimentRunModel, results: tuple[TrialUnitResult, ...]) -> None:
    expected = [
        (
            result.cleanup_receipt.execution_attempt_id,
            result.cleanup_receipt.receipt_id,
            frozenset(receipt.operation_id for receipt in result.operation_receipts),
        )
        for result in results
    ]
    observed = [
        (item.execution_attempt_id, item.cleanup_receipt_ref, frozenset(item.operation_refs))
        for item in run.trial_provenance.execution_attempts
    ]
    if observed != expected:
        raise ValueError("archive does not retain all runtime attempts")


def _replace_archived_run(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    run: ExperimentRunModel,
    attempts: tuple[RuntimeTrialUnit, ...],
    records: tuple[RuntimeDecision, ...],
) -> bool:
    engine, binding = experiment.engine, experiment.replacement
    policy = experiment.plan.replacement_policy
    history = tuple(
        sorted(
            (
                record
                for record in records
                if isinstance(record, TrialReplacementDecision)
                and record.experiment_id == experiment.experiment_id
                and record.root_entry_id == slot.root_entry_id
            ),
            key=lambda item: item.ordinal,
        )
    )
    # Resume an already committed child after archive or dispatch interruption.
    child = next((item for item in history if item.parent_run.run_id == run.run_id), None)
    if child is not None:
        engine._execution_adapter.call(
            "control", _write_archive, binding.archive, child.superseded_run, timeout_ms=engine._supervision.commit_ms
        )
        return False
    if run.run_status not in policy.replace_on or len(history) >= policy.max_replacements:
        return False
    child = _compile_replacement(experiment, slot, run, attempts, history)
    # The ordinal and child identity commit before archive publication or effects.
    engine._store.claim_runtime_decision(child)
    engine._execution_adapter.call(
        "control", _write_archive, binding.archive, child.superseded_run, timeout_ms=engine._supervision.commit_ms
    )
    return True


def _compile_replacement(
    experiment: RuntimeExperiment,
    slot: TrialSlot,
    run: ExperimentRunModel,
    attempts: tuple[RuntimeTrialUnit, ...],
    history: tuple[TrialReplacementDecision, ...],
) -> TrialReplacementDecision:
    previous = tuple(
        TrialReplacementResult(
            item.plan, item.superseded_run, parent_run=item.parent_run, cleanup_receipts=item.cleanup_receipts
        )
        for item in history
    )
    receipts = tuple(item.result().cleanup_receipt for item in attempts)
    result = compile_replacement_trial(
        experiment.replacement.compilation_request,
        original_plan=experiment.plan,
        root_entry_id=slot.root_entry_id,
        previous_allocations=previous,
        failed_run=run,
        cleanup_receipts=receipts,
    )
    if result.plan is None:
        raise ValueError("replacement compiler refused the recorded runtime outcome")
    require_compatible_record_versions(
        experiment.engine._store.load_runtime_decisions(), experiment.experiment_id, (run, result.superseded_run)
    )
    return TrialReplacementDecision(
        experiment_id=experiment.experiment_id,
        root_entry_id=slot.root_entry_id,
        ordinal=result.plan.replacement_origin.ordinal,
        plan=result.plan,
        superseded_run=result.superseded_run,
        parent_run=run,
        cleanup_receipts=receipts,
    )
