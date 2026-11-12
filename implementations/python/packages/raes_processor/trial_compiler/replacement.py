"""Explicit experiment allocation; never called by operation/engine recovery.

This pure seam returns existing portable artifacts for one allocation decision.
The embedding experiment coordinator must atomically claim the original slot's
next ordinal and persist the child plan and archival successor before dispatch.
Its authoritative readback is supplied as ``previous_allocations`` on restart.
Identical notifications compile the same child; compiling is not effect admission.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import AdmittedTrialPlanModel, ExperimentRunModel, TrialCleanupReceiptModel
from raes_contracts.contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.contracts.trial_replacement import TrialReplacementOriginModel
from raes_contracts.contracts.trial_replacement_archive import (
    build_superseded_trial_run as _supersede,
)
from raes_contracts.contracts.trial_replacement_archive import (
    replacement_parent_cleanup,
    replacement_resources_reusable,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError

from .compiler import _INPUT_REFUSALS, _CaptureAdmissionFailure, _compile, _diagnostic
from .inputs import coordinates
from .models import CompilationFailure, TrialCompilationRequest
from .replacement_inputs import ReplacementCompilationContext


@dataclass(frozen=True)
class TrialReplacementResult:
    """One decision, or a safe refusal with no budget debit or archive mutation."""

    plan: AdmittedTrialPlanModel | None
    superseded_run: ExperimentRunModel | None
    diagnostics: tuple[Diagnostic, ...] = ()
    parent_run: ExperimentRunModel | None = None
    cleanup_receipts: tuple[TrialCleanupReceiptModel, ...] = ()


def _refuse(code: str, message: str) -> CompilationFailure:
    return CompilationFailure(f"replacement-{code}", "/run_plan/replacement_policy", message)


def _clean_parent(
    plan: AdmittedTrialPlanModel,
    run: ExperimentRunModel,
    receipts: Sequence[TrialCleanupReceiptModel],
) -> TrialCleanupReceiptModel:
    try:
        receipt = replacement_parent_cleanup(plan, run, receipts)
    except ValueError as exc:
        # The contract owner reports unreconciled parent evidence with ValueError (E3); refuse here (E9).
        raise InvalidInputError("replacement parent evidence does not reconcile with its admitted plan") from exc
    entry = plan.entries[run.trial_provenance.plan_entry_id]
    cleanup = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
    if not replacement_resources_reusable(cleanup, receipt):
        raise _refuse("clean-state-unverified", "terminal cleanup does not establish reusable initial state")
    return receipt


def _context(
    root: AdmittedTrialPlanModel,
    root_entry_id: str,
    parent: AdmittedTrialPlanModel,
    run: ExperimentRunModel,
    receipts: Sequence[TrialCleanupReceiptModel],
    ordinal: int,
    request: TrialCompilationRequest,
) -> ReplacementCompilationContext:
    policy = root.replacement_policy
    if run.run_status not in policy.replace_on:
        raise _refuse("not-authorized", "the authored policy does not replace this trial disposition")
    if run.task_ref != request.experiment.task_ref:
        raise _refuse("parent-invalid", "replacement parent does not belong to the admitted experiment task")
    if parent.replacement_origin is not None and run.run_version != "1":
        raise _refuse("parent-invalid", "replacement parent must resolve its reserved first archival version")
    receipt = _clean_parent(parent, run, receipts)
    linkage = run.trial_provenance
    expected_entry = root_entry_id if parent is root else next(iter(parent.entries))
    if linkage.plan_entry_id != expected_entry:
        raise _refuse("parent-invalid", "replacement parent does not match the original allocation slot")
    root_coordinate = root.entries[root_entry_id].coordinate
    index = coordinates(request).index(root_coordinate)
    origin = TrialReplacementOriginModel(
        root_plan_id=root.plan_id,
        root_plan_digest=root.plan_digest,
        root_entry_id=root_entry_id,
        ordinal=ordinal,
        parent_plan_id=parent.plan_id,
        parent_plan_digest=parent.plan_digest,
        parent_entry_id=linkage.plan_entry_id,
        parent_run_id=run.run_id,
        parent_run_version=run.run_version,
        parent_run_digest=canonical_json_digest(run.model_dump(mode="json")),
        cleanup_receipt_ref=receipt.receipt_id,
    )
    return ReplacementCompilationContext(origin, index)


def _validated_run(run: ExperimentRunModel) -> ExperimentRunModel:
    return ExperimentRunModel.model_validate(run.model_dump(mode="python"))


def _validated_receipts(receipts: Sequence[TrialCleanupReceiptModel]) -> tuple[TrialCleanupReceiptModel, ...]:
    return tuple(
        sorted(
            (TrialCleanupReceiptModel.model_validate(item.model_dump(mode="python")) for item in receipts),
            key=lambda item: item.execution_attempt_id,
        )
    )


def _validated_root(
    request: TrialCompilationRequest,
    original_plan: AdmittedTrialPlanModel,
    root_entry_id: str,
    history: Sequence[TrialReplacementResult],
) -> AdmittedTrialPlanModel:
    root = revalidate_admitted_trial_plan(original_plan)
    if root.replacement_origin is not None or root_entry_id not in root.entries:
        raise _refuse("root-invalid", "replacement requires an original admitted allocation slot")
    policy = root.replacement_policy
    if policy is None or policy.max_replacements == 0:
        raise _refuse("not-authorized", "the original experiment authorizes no replacement trials")
    if len(history) > policy.max_replacements:
        raise _refuse("history-invalid", "replacement history exceeds the authored lineage bound")
    if len(root.entries) * (len(history) + 2) > request.limits.max_coordinates:
        raise _refuse("work-limit-exceeded", "replacement traversal exceeds the compilation work limit")
    # Validate exact original inputs, not today's policy or a caller-resealed plan.
    expected_root = _compile(request, None)
    if expected_root.plan_digest != root.plan_digest:
        raise _refuse("root-invalid", "replacement inputs differ from the original admitted experiment")
    return root


def _prior_plan_bytes(prior: TrialReplacementResult) -> int:
    if prior.plan is None or prior.parent_run is None or prior.superseded_run is None or prior.diagnostics:
        raise _refuse("history-invalid", "replacement history contains an uncommitted allocation")
    return len(canonical_json_bytes(prior.plan.model_dump(mode="json")))


def _validated_prior(
    request: TrialCompilationRequest,
    root: AdmittedTrialPlanModel,
    root_entry_id: str,
    parent: AdmittedTrialPlanModel,
    prior: TrialReplacementResult,
    ordinal: int,
) -> tuple[AdmittedTrialPlanModel, ExperimentRunModel, tuple[TrialCleanupReceiptModel, ...]]:
    child = revalidate_admitted_trial_plan(prior.plan)
    old_run = _validated_run(prior.parent_run)
    old_receipts = _validated_receipts(prior.cleanup_receipts)
    context = _context(root, root_entry_id, parent, old_run, old_receipts, ordinal, request)
    # Recompilation prevents forged/forked/cyclic history from minting budget.
    expected_child = _compile(request, None, context)
    if child.plan_digest != expected_child.plan_digest or prior.superseded_run.model_dump(mode="json") != _supersede(
        old_run, child
    ).model_dump(mode="json"):
        raise _refuse("history-invalid", "replacement history does not match its exact admitted lineage")
    return expected_child, old_run, old_receipts


def _replayed_decision(
    run: ExperimentRunModel,
    receipts: tuple[TrialCleanupReceiptModel, ...],
    child: AdmittedTrialPlanModel,
    old_run: ExperimentRunModel,
    old_receipts: tuple[TrialCleanupReceiptModel, ...],
) -> TrialReplacementResult | None:
    if run.run_id != old_run.run_id:
        return None
    if run.model_dump(mode="json") != old_run.model_dump(mode="json") or [
        item.model_dump(mode="json") for item in receipts
    ] != [item.model_dump(mode="json") for item in old_receipts]:
        raise _refuse("decision-conflict", "a committed replacement has different parent evidence")
    return TrialReplacementResult(child, _supersede(old_run, child), (), old_run, old_receipts)


def _replay_history(
    request: TrialCompilationRequest,
    root: AdmittedTrialPlanModel,
    root_entry_id: str,
    history: Sequence[TrialReplacementResult],
    run: ExperimentRunModel,
    receipts: tuple[TrialCleanupReceiptModel, ...],
) -> tuple[AdmittedTrialPlanModel, TrialReplacementResult | None]:
    parent = root
    replay = None
    total_bytes = 0
    for ordinal, prior in enumerate(history, 1):
        total_bytes += _prior_plan_bytes(prior)
        if total_bytes > request.limits.max_plan_bytes:
            raise _refuse("history-limit-exceeded", "replacement history exceeds the compilation byte limit")
        child, old_run, old_receipts = _validated_prior(request, root, root_entry_id, parent, prior, ordinal)
        replay = _replayed_decision(run, receipts, child, old_run, old_receipts) or replay
        parent = child
    return parent, replay


def _allocate(
    request: TrialCompilationRequest,
    original_plan: AdmittedTrialPlanModel,
    root_entry_id: str,
    history: Sequence[TrialReplacementResult],
    failed_run: ExperimentRunModel,
    cleanup_receipts: Sequence[TrialCleanupReceiptModel],
) -> TrialReplacementResult:
    root = _validated_root(request, original_plan, root_entry_id, history)
    run = _validated_run(failed_run)
    receipts = _validated_receipts(cleanup_receipts)
    parent, replay = _replay_history(request, root, root_entry_id, history, run, receipts)
    if replay is not None:
        return replay
    if len(history) >= root.replacement_policy.max_replacements:
        raise _refuse("limit-exhausted", "the original allocation slot has exhausted its replacement limit")
    context = _context(root, root_entry_id, parent, run, receipts, len(history) + 1, request)
    child = _compile(request, None, context)
    return TrialReplacementResult(child, _supersede(run, child), (), run, receipts)


def compile_replacement_trial(
    request: TrialCompilationRequest,
    *,
    original_plan: AdmittedTrialPlanModel,
    root_entry_id: str,
    previous_allocations: Sequence[TrialReplacementResult] = (),
    failed_run: ExperimentRunModel,
    cleanup_receipts: Sequence[TrialCleanupReceiptModel],
) -> TrialReplacementResult:
    """Compile one explicitly requested fresh trial, with no effects or hidden recovery.

    History must be the coordinator's complete committed prefix for this slot.
    After uncertain commit, read it back before invoking this seam again. Each
    child still needs ordinary actor, backend, clean-state and live resource
    admission. No new identity alone proves isolation from the old trial.
    """
    try:
        return _allocate(request, original_plan, root_entry_id, previous_allocations, failed_run, cleanup_receipts)
    except _CaptureAdmissionFailure as exc:
        return TrialReplacementResult(None, None, exc.diagnostics)
    except CompilationFailure as exc:
        failure = exc
    except _INPUT_REFUSALS as exc:
        failure = _refuse("input-invalid", "replacement input failed closed validation")
        failure.__cause__ = exc
    return TrialReplacementResult(None, None, (_diagnostic(failure),))


__all__ = ["TrialReplacementResult", "compile_replacement_trial"]
