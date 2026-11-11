"""Checked remote facts projected into the existing trial and record interfaces."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING

from raes_contracts.assigned_trial import TrialAssignmentModel, TrialOutcomeModel
from raes_contracts.contracts.trial_cleanup import validate_trial_cleanup_receipt
from raes_contracts.contracts.trial_replacement_archive import replacement_resources_reusable
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import EvidenceIntegrityError
from raes_contracts.json_serialization import sorted_json_text
from raes_contracts.runtime_state import OperationReceipt
from raes_contracts.trial_unit import TrialUnitRequest, TrialUnitResult, validate_trial_unit_result

from .errors import TrialPending
from .experiment_records import ExperimentRecordSource
from .runtime_assignment_decisions import TrialOutcomeDecision
from .runtime_trial_decisions import TrialObservationDecision
from .snapshot_contract import runtime_snapshot_from_contract

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from raes_contracts.assigned_trial import TrialFactModel

    from .control_plane_store import ControlPlaneStore
    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment import TrialSlot
    from .runtime_trial_decisions import TrialAttemptDecision


def latest_trial_outcome(records: Iterable[RuntimeDecision], assignment_digest: str) -> TrialOutcomeDecision | None:
    return max(
        (
            item
            for item in records
            if isinstance(item, TrialOutcomeDecision) and item.outcome.assignment_digest == assignment_digest
        ),
        key=lambda item: item.sequence,
        default=None,
    )


def validate_remote_outcome(
    request: TrialUnitRequest, assignment: TrialAssignmentModel, outcome: TrialOutcomeModel
) -> None:
    """Check retained joins before the installed native evidence reader is called."""
    if outcome.assignment_digest != assignment.content_digest:
        raise EvidenceIntegrityError("trial outcome differs from its assigned attempt")
    _validate_fact_bindings(request, assignment, outcome)
    facts = {fact.observation.kind: fact for fact in outcome.facts}
    configuration = facts.get("configuration")
    if configuration and configuration.observation.configurations != request.participant_configurations:
        raise EvidenceIntegrityError("trial configuration differs from admitted settings")
    execution, cleanup = facts.get("execution"), facts.get("cleanup")
    if execution and execution.observation.ceased and not execution.observation.evidence:
        raise EvidenceIntegrityError("execution cessation requires observed evidence")
    _validate_cleanup(request, execution, cleanup)
    _validate_operation_bindings(request, assignment, outcome)
    if cleanup is not None:
        trial_outcome_result(request, assignment, outcome)


def _validate_fact_bindings(
    request: TrialUnitRequest, assignment: TrialAssignmentModel, outcome: TrialOutcomeModel
) -> None:
    for fact in outcome.facts:
        if datetime.fromisoformat(fact.observed_at) < datetime.fromisoformat(assignment.started_at):
            raise EvidenceIntegrityError("trial observation precedes its assigned attempt")
        if any(
            item.run_ref.ref_kind != "run" or item.run_ref.ref_id != request.run_id
            for item in fact.observation.evidence
        ):
            raise EvidenceIntegrityError("trial evidence belongs to another run")


def _validate_cleanup(
    request: TrialUnitRequest, execution: TrialFactModel | None, cleanup: TrialFactModel | None
) -> None:
    if cleanup is None:
        return
    if not execution or not execution.observation.ceased or execution.observation.state == "running":
        raise EvidenceIntegrityError("cleanup does not establish execution cessation")
    receipt = cleanup.observation.receipt
    try:
        validate_trial_cleanup_receipt(request.cleanup_plan, receipt)
    except ValueError:
        raise EvidenceIntegrityError("trial cleanup differs from the assigned obligations") from None
    if (
        receipt.execution_attempt_id != request.execution_attempt_id
        or receipt.trial_outcome != execution.observation.state
    ):
        raise EvidenceIntegrityError("trial cleanup differs from the assigned outcome")


def _validate_operation_bindings(
    request: TrialUnitRequest, assignment: TrialAssignmentModel, outcome: TrialOutcomeModel
) -> None:
    for item in outcome.operations:
        context = item.receipt.context
        if (context.target_scope, context.run_scope, context.actor_id) != (
            assignment.target_scope,
            "run:" + request.run_id,
            assignment.owner_id,
        ):
            raise EvidenceIntegrityError("trial operation belongs to another execution owner or run")


def require_outcome_extension(previous: TrialOutcomeModel, candidate: TrialOutcomeModel) -> None:
    facts = {fact.observation.kind: fact for fact in candidate.facts}
    if any(facts.get(fact.observation.kind) != fact for fact in previous.facts):
        raise EvidenceIntegrityError("trial outcome changes retained observations")
    operations = {item.receipt.operation_id: item for item in candidate.operations}
    for item in previous.operations:
        changed = operations.get(item.receipt.operation_id)
        if changed is None or changed.receipt != item.receipt:
            raise EvidenceIntegrityError("trial outcome changes retained operations")
        if item.status.state.value in {"succeeded", "failed", "cancelled"} and changed.status != item.status:
            raise EvidenceIntegrityError("trial outcome changes a settled operation")
    for name in ("configuration_state", "capture_state", "retry_state"):
        prior = getattr(previous, name)
        if prior in {"succeeded", "failed", "cancelled"} and getattr(candidate, name) != prior:
            raise EvidenceIntegrityError("trial outcome changes a settled phase")


def remote_observations(
    assignment: TrialAssignmentModel, outcome: TrialOutcomeModel
) -> tuple[TrialObservationDecision, ...]:
    return tuple(
        TrialObservationDecision(
            execution_attempt_id=assignment.execution_attempt_id,
            observation=fact.observation,
            observed_at=fact.observed_at,
            snapshot_json=None
            if fact.execution_snapshot is None
            else sorted_json_text(fact.execution_snapshot.model_dump(mode="json")),
        )
        for fact in outcome.facts
    )


def remote_receipts(outcome: TrialOutcomeModel) -> tuple[OperationReceipt, ...]:
    return tuple(
        OperationReceipt(
            schema_version=item.receipt.schema_version,
            operation_id=item.receipt.operation_id,
            domain=item.receipt.domain,
            submitted_at=item.receipt.submitted_at,
            accepted=item.receipt.accepted,
            context=item.receipt.context,
            diagnostics=[Diagnostic(**diagnostic.model_dump()) for diagnostic in item.receipt.diagnostics],
        )
        for item in outcome.operations
    )


def trial_outcome_result(
    request: TrialUnitRequest, assignment: TrialAssignmentModel, outcome: TrialOutcomeModel | None
) -> TrialUnitResult:
    facts = {} if outcome is None else {fact.observation.kind: fact for fact in outcome.facts}
    if not {"execution", "cleanup"} <= facts.keys():
        raise TrialPending("assigned trial does not have terminal execution and cleanup observations")
    try:
        result = TrialUnitResult(
            operation_receipts=remote_receipts(outcome),
            execution_snapshot=runtime_snapshot_from_contract(facts["execution"].execution_snapshot),
            evidence=tuple(
                item
                for kind in ("configuration", "execution", "capture", "retry")
                if kind in facts
                for item in facts[kind].observation.evidence
            ),
            cleanup_receipt=facts["cleanup"].observation.receipt,
            cleanup_evidence=facts["cleanup"].observation.evidence,
        )
        validate_trial_unit_result(request, result, target_scope=assignment.target_scope)
    except ValueError:
        raise EvidenceIntegrityError("assigned trial result failed validation") from None
    return result


class RemoteTrialUnit:
    """Read-only adapter of accepted facts; it cannot dispatch native operations."""

    def __init__(
        self, slot: TrialSlot, attempt: TrialAttemptDecision, assignment: TrialAssignmentModel, store: ControlPlaneStore
    ) -> None:
        self.slot, self.attempt, self.assignment, self.store = slot, attempt, assignment, store
        self.realization = slot.realization
        self.request = TrialUnitRequest(
            plan=slot.plan,
            plan_entry_id=slot.entry.plan_entry_id,
            execution_attempt_id=attempt.execution_attempt_id,
            instantiated_sdl_digest=slot.realization.snapshot_digest,
            provisioning_plan=slot.realization.provisioning_plan,
            orchestration_plan=slot.realization.orchestration_plan,
            evaluation_plan=slot.realization.evaluation_plan,
        )

    def outcome(self) -> TrialOutcomeModel | None:
        decision = latest_trial_outcome(self.store.load_runtime_decisions(), self.assignment.content_digest)
        return None if decision is None else decision.outcome

    def observations(self) -> dict[str, TrialObservationDecision]:
        outcome = self.outcome()
        return (
            {}
            if outcome is None
            else {item.observation.kind: item for item in remote_observations(self.assignment, outcome)}
        )

    def result(self) -> TrialUnitResult:
        return trial_outcome_result(self.request, self.assignment, self.outcome())

    def reusable(self) -> bool:
        return replacement_resources_reusable(self.request.cleanup_plan, self.result().cleanup_receipt)

    def capture_succeeded(self) -> bool:
        outcome = self.outcome()
        capture = self.observations().get("capture")
        return bool(outcome and outcome.capture_state == "succeeded" and capture and capture.observation.complete)

    def prepare_retry_runtime(self) -> str:
        outcome = self.outcome()
        return "succeeded" if outcome is not None and outcome.retry_state == "succeeded" else "pending"

    def retire(self) -> None:
        """Verified terminal facts release coordinator capacity, never host leases."""


def remote_trial_source(
    slot: TrialSlot,
    attempts: tuple[TrialAttemptDecision, ...],
    assignments: Mapping[str, TrialAssignmentModel],
    records: tuple[RuntimeDecision, ...],
) -> ExperimentRecordSource:
    observations, snapshots, refs, phases, states, receipts = [], {}, {}, {}, {}, []
    for attempt in attempts:
        assignment = assignments.get(attempt.execution_attempt_id)
        if assignment is None:
            refs[attempt.execution_attempt_id] = ()
            continue
        decision = latest_trial_outcome(records, assignment.content_digest)
        if decision is None:
            refs[attempt.execution_attempt_id] = ()
            continue
        outcome = decision.outcome
        observations.extend(remote_observations(assignment, outcome))
        for fact in outcome.facts:
            if fact.execution_snapshot is not None:
                snapshots[attempt.execution_attempt_id] = runtime_snapshot_from_contract(fact.execution_snapshot)
        refs[attempt.execution_attempt_id] = tuple(item.receipt.operation_id for item in outcome.operations)
        for phase, name in ((0, "configuration_state"), (1, "capture_state"), (4, "retry_state")):
            phases[attempt.execution_attempt_id + ":" + str(phase)] = getattr(outcome, name)
        states.update({item.receipt.operation_id: item.status.state.value for item in outcome.operations})
        receipts.extend(remote_receipts(outcome))
    return ExperimentRecordSource(
        run_id=slot.entry.run_id,
        plan=slot.plan.model_copy(deep=True),
        realization=deepcopy(slot.realization),
        attempts=attempts,
        observations=tuple(observations),
        execution_snapshots=snapshots,
        phase_states=phases,
        operation_refs=refs,
        operation_states=states,
        operation_receipts=tuple(receipts),
    )
