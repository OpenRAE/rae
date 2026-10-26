"""Archival successor construction; preserve the original failure and evidence."""

from __future__ import annotations

from collections.abc import Sequence

from .admitted_trial_plan import AdmittedTrialPlanModel
from .experiment_run import ExperimentRunModel
from .trial_analysis import reconcile_admitted_trial_plan
from .trial_cleanup import TrialCleanupPlanModel, TrialCleanupReceiptModel


def replacement_parent_cleanup(
    plan: AdmittedTrialPlanModel,
    run: ExperimentRunModel,
    receipts: Sequence[TrialCleanupReceiptModel],
) -> TrialCleanupReceiptModel:
    """Validate complete attempt accounting and return the terminal cleanup."""
    reconcile_admitted_trial_plan(plan, [run], list(receipts))
    linkage = run.trial_provenance
    terminal = next(
        attempt for attempt in linkage.execution_attempts if attempt.execution_attempt_id == linkage.terminal_attempt_id
    )
    return next(item for item in receipts if item.receipt_id == terminal.cleanup_receipt_ref)


def replacement_resources_reusable(cleanup: TrialCleanupPlanModel, receipt: TrialCleanupReceiptModel) -> bool:
    """Require positive scope-complete evidence, not just a valid failed receipt."""
    claim = receipt.clean_state_claim
    return bool(
        receipt.cleanup_status == "succeeded"
        and claim is not None
        and claim.disposition != "fresh-range-required"
        and set(claim.boundary_refs) == set(cleanup.resource_boundaries)
        and (claim.disposition != "declared-reusable" or cleanup.clean_state.mode == "declared-reusable")
        and cleanup.clean_state.mode != "fresh-range-required"
    )


def build_superseded_trial_run(run: ExperimentRunModel, child: AdmittedTrialPlanModel) -> ExperimentRunModel:
    entry = next(iter(child.entries.values()))
    payload = run.model_dump(mode="json")
    # New immutable archive version; timestamps, outcomes and all evidence are
    # preserved. The prior version remains available by its exact reference.
    payload["run_version"] = f"{run.run_version}.superseded-{child.replacement_origin.ordinal}"
    payload["run_status"] = "superseded"
    # These attestations name the exact original artifact version. Retain them
    # through derived_from_refs; rebinding would invent validation/evidence
    # authority for this new status-only artifact.
    payload["validation_basis_disclosures"] = []
    payload["evidence_requirement_relations"] = []
    invalidation = payload.get("invalidation") or {
        "invalidated_at": run.ended_at,
        "reason": "failed trial replaced under the admitted experiment policy",
    }
    invalidation["superseded_by"] = {
        "ref_kind": "run",
        "ref_id": entry.run_id,
        "ref_version": "1",
    }
    payload["invalidation"] = invalidation
    reference = {"ref_kind": "run", "ref_id": run.run_id, "ref_version": run.run_version}
    if reference not in payload["derived_from_refs"]:
        payload["derived_from_refs"].append(reference)
    return ExperimentRunModel.model_validate(payload)
