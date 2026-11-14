"""Resolve governed step success through admitted objective and truth contracts."""

from raes_contracts.contracts.execution_state import (
    PropositionTruthResultModel,
    WorkflowStepAttemptProvenanceModel,
)
from raes_contracts.contracts.workflow_dispatch import WorkflowStepDispatch, WorkflowStepResponse
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry

from .proposition_truth_contracts import proposition_truth_contract_diagnostics


def require_success_evidence(
    snapshot: RuntimeSnapshot, dispatch: WorkflowStepDispatch, response: WorkflowStepResponse
) -> None:
    if dispatch.execution_mode == "scripted" or response.outcome != "succeeded":
        return
    provenance = response.attempt_provenance
    objective = snapshot.entries.get(dispatch.objective_address)
    if provenance is None or objective is None or objective.resource_type != "objective":
        raise ConflictError("governed workflow success has no admitted objective evidence")
    required = objective.payload.get("success_addresses", objective.payload.get("success_refs", ()))
    if not required or proposition_truth_contract_diagnostics(snapshot):
        raise ConflictError("governed workflow success requires valid admitted assertion truth")
    require_selected_truths(snapshot, required, provenance, success_threshold(objective, len(required)))


def require_selected_truths(
    snapshot: RuntimeSnapshot,
    required: tuple[str, ...],
    provenance: WorkflowStepAttemptProvenanceModel,
    threshold: int,
) -> None:
    truths = [
        PropositionTruthResultModel.model_validate(snapshot.proposition_truth_results[address])
        for address in required
        if address in snapshot.proposition_truth_results
    ]
    selected = [item for item in truths if item.result_id in provenance.assertion_truth_refs]
    if len(selected) < threshold or any(item.assertion_outcome.value != "true" for item in selected):
        raise ConflictError("governed workflow success does not resolve accepted objective truth")
    require_truth_references(selected, provenance)


def require_truth_references(
    selected: list[PropositionTruthResultModel], provenance: WorkflowStepAttemptProvenanceModel
) -> None:
    if set(provenance.assertion_truth_refs) != {item.result_id for item in selected} or not set(
        provenance.evidence_refs
    ) <= {ref for item in selected for ref in item.evidence_refs}:
        raise ConflictError("governed workflow success does not resolve accepted objective truth")


def success_threshold(objective: SnapshotEntry, required_count: int) -> int:
    success = objective.payload.get("spec", {}).get("success", {})
    mode = success.get("mode", "all_of")
    if mode == "all_of":
        threshold = required_count
    elif mode == "any_of":
        threshold = 1
    else:
        threshold = success.get("threshold")
    if mode not in {"all_of", "any_of", "at_least"} or type(threshold) is not int:
        raise ConflictError("governed workflow success does not resolve accepted objective truth")
    return threshold
