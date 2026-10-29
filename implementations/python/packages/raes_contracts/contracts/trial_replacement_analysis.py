"""Cross-plan replacement lineage and single-slot archival analysis accounting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..admitted_trial_plan_ingress import AdmittedTrialPlanIngressError, revalidate_admitted_trial_plan
from ..canonical import canonical_json_digest
from .admitted_trial_plan import AdmittedTrialEntryModel, AdmittedTrialPlanModel
from .experiment_run import ExperimentRunModel
from .trial_analysis import validate_admitted_trial_run
from .trial_cleanup import TrialCleanupReceiptModel, validate_trial_cleanup_receipt
from .trial_replacement import TrialReplacementOriginModel, TrialReplacementPolicyModel
from .trial_replacement_archive import (
    build_superseded_trial_run,
    replacement_parent_cleanup,
    replacement_resources_reusable,
)

_Plans = dict[str, AdmittedTrialPlanModel]
_RunVersions = dict[tuple[str, str], ExperimentRunModel]
_RunsById = dict[str, list[ExperimentRunModel]]
_ReceiptsByEntry = dict[str, list[TrialCleanupReceiptModel]]


@dataclass(frozen=True)
class ReplacementTrialReconciliation:
    """Retained history and eligible leaves, without asserting study completion."""

    analysis_runs: tuple[ExperimentRunModel, ...]
    shortfall_entry_ids: tuple[str, ...]
    exhausted_entry_ids: tuple[str, ...]


def _key(run: ExperimentRunModel) -> tuple[str, str]:
    return run.run_id, run.run_version


def _digest(run: ExperimentRunModel) -> str:
    return canonical_json_digest(run.model_dump(mode="json"))


def _revalidated(plan: AdmittedTrialPlanModel) -> AdmittedTrialPlanModel:
    """Keep the ValueError contract of this lineage validation (E3)."""

    try:
        return revalidate_admitted_trial_plan(plan)
    except AdmittedTrialPlanIngressError as exc:
        raise ValueError("Admitted trial plan contract validation failed") from exc


def _index(
    root: AdmittedTrialPlanModel,
    replacements: list[AdmittedTrialPlanModel],
    runs: list[ExperimentRunModel],
    receipts: list[TrialCleanupReceiptModel],
) -> tuple[
    dict[str, AdmittedTrialPlanModel], dict[tuple[str, str], ExperimentRunModel], dict[str, list[ExperimentRunModel]]
]:
    plans = _index_plans(root, replacements)
    by_version = {_key(run): run for run in runs}
    if len(by_version) != len(runs):
        raise ValueError("archival run versions must be unique")
    by_entry = _index_receipts(plans, receipts)
    return plans, by_version, _index_runs(plans, runs, by_entry)


def _index_plans(root: AdmittedTrialPlanModel, replacements: list[AdmittedTrialPlanModel]) -> _Plans:
    plans = {root.plan_id: root}
    for candidate in replacements:
        plan = _revalidated(candidate)
        if plan.plan_id in plans or plan.replacement_origin is None:
            raise ValueError("replacement plans must be distinct linked children")
        plans[plan.plan_id] = plan
    all_entries = [entry for plan in plans.values() for entry in plan.entries.values()]
    if len({entry.run_id for entry in all_entries}) != len(all_entries) or len(
        {entry.plan_entry_id for entry in all_entries}
    ) != len(all_entries):
        raise ValueError("replacement plans must have globally distinct entry and run identities")
    return plans


def _validate_receipt_identities(receipts: list[TrialCleanupReceiptModel]) -> None:
    if len({receipt.receipt_id for receipt in receipts}) != len(receipts):
        raise ValueError("cleanup receipt identities must be unique")
    if len({receipt.execution_attempt_id for receipt in receipts}) != len(receipts):
        raise ValueError("execution attempt identities must be unique")


def _index_receipts(plans: _Plans, receipts: list[TrialCleanupReceiptModel]) -> _ReceiptsByEntry:
    _validate_receipt_identities(receipts)
    by_entry = defaultdict(list)
    for receipt in receipts:
        by_entry[receipt.plan_entry_id].append(receipt)
    for plan in plans.values():
        for entry in plan.entries.values():
            cleanup = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
            if len(by_entry[entry.plan_entry_id]) > cleanup.retry_policy.max_attempts:
                raise ValueError("execution attempt history exceeds the admitted budget")
            for receipt in by_entry[entry.plan_entry_id]:
                validate_trial_cleanup_receipt(cleanup, receipt)
    known_entries = {entry.plan_entry_id for plan in plans.values() for entry in plan.entries.values()}
    if set(by_entry) - known_entries:
        raise ValueError("cleanup evidence references an unknown trial")
    return by_entry


def _index_runs(plans: _Plans, runs: list[ExperimentRunModel], by_entry: _ReceiptsByEntry) -> _RunsById:
    by_run_id = defaultdict(list)
    for run in runs:
        linkage = run.trial_provenance
        plan = plans.get(linkage.plan_id) if linkage is not None else None
        if plan is None:
            raise ValueError("every retained run must resolve to an admitted plan")
        attempt_receipts = by_entry[linkage.plan_entry_id]
        validate_admitted_trial_run(plan, run, attempt_receipts)
        if {item.cleanup_receipt_ref for item in linkage.execution_attempts} != {
            item.receipt_id for item in attempt_receipts
        }:
            raise ValueError("archival history must account for every execution attempt")
        cleanup = plan.cleanup_plans[plan.entries[linkage.plan_entry_id].execution_controls.cleanup_plan_ref]
        if len(attempt_receipts) > cleanup.retry_policy.max_attempts:
            raise ValueError("execution attempt history exceeds the admitted budget")
        by_run_id[run.run_id].append(run)
    return by_run_id


def _validate_child(
    root: AdmittedTrialPlanModel,
    parent: AdmittedTrialPlanModel,
    child: AdmittedTrialPlanModel,
    origin: TrialReplacementOriginModel,
    by_version: dict[tuple[str, str], ExperimentRunModel],
    receipts: list[TrialCleanupReceiptModel],
) -> None:
    _validate_child_authority(root, parent, child, origin)
    run = _validate_child_parent(root, parent, child, origin, by_version)
    _validate_child_evidence(parent, child, origin, run, by_version, receipts)


def _validate_child_authority(
    root: AdmittedTrialPlanModel,
    parent: AdmittedTrialPlanModel,
    child: AdmittedTrialPlanModel,
    origin: TrialReplacementOriginModel,
) -> None:
    if (
        child.input_refs.authoring_input_ref != root.input_refs.authoring_input_ref
        or child.input_refs.task_ref != root.input_refs.task_ref
    ):
        raise ValueError("replacement must preserve original experiment and task authority")
    if child.replacement_policy != root.replacement_policy or origin.parent_plan_digest != parent.plan_digest:
        raise ValueError("replacement must preserve the original budget and exact parent plan")
    prior_entry = parent.entries.get(origin.parent_entry_id)
    entry = next(iter(child.entries.values()))
    original_entry = root.entries[origin.root_entry_id]
    if prior_entry is None or prior_entry.run_id != origin.parent_run_id:
        raise ValueError("replacement parent entry does not resolve")
    if (entry.coordinate.condition_id, entry.coordinate.block_id) != (
        original_entry.coordinate.condition_id,
        original_entry.coordinate.block_id,
    ):
        raise ValueError("replacement must retain the original condition and block")


def _validate_child_parent(
    root: AdmittedTrialPlanModel,
    parent: AdmittedTrialPlanModel,
    child: AdmittedTrialPlanModel,
    origin: TrialReplacementOriginModel,
    by_version: _RunVersions,
) -> ExperimentRunModel:
    run = by_version.get((origin.parent_run_id, origin.parent_run_version))
    if (
        run is None
        or _digest(run) != origin.parent_run_digest
        or run.run_status not in root.replacement_policy.replace_on
    ):
        raise ValueError("replacement must preserve its exact qualifying parent artifact")
    if parent.replacement_origin is not None and run.run_version != "1":
        raise ValueError("intermediate replacement must resolve its reserved first archival version")
    if run.task_ref != child.input_refs.task_ref:
        raise ValueError("replacement parent task does not match the admitted experiment")
    if run.trial_provenance.plan_entry_id != origin.parent_entry_id:
        raise ValueError("replacement parent run does not match its entry")
    return run


def _validate_child_evidence(
    parent: AdmittedTrialPlanModel,
    child: AdmittedTrialPlanModel,
    origin: TrialReplacementOriginModel,
    run: ExperimentRunModel,
    by_version: _RunVersions,
    receipts: list[TrialCleanupReceiptModel],
) -> None:
    prior_entry = parent.entries[origin.parent_entry_id]
    relevant_receipts = [item for item in receipts if item.plan_entry_id == prior_entry.plan_entry_id]
    receipt = replacement_parent_cleanup(parent, run, relevant_receipts)
    cleanup = parent.cleanup_plans[prior_entry.execution_controls.cleanup_plan_ref]
    if receipt.receipt_id != origin.cleanup_receipt_ref or not replacement_resources_reusable(cleanup, receipt):
        raise ValueError("replacement requires established reusable initial state")
    superseded = build_superseded_trial_run(run, child)
    retained = by_version.get(_key(superseded))
    if retained is None or _digest(retained) != _digest(superseded):
        raise ValueError("replacement must retain the evidence-preserving supersession version")


def _chains(root: AdmittedTrialPlanModel, plans: _Plans) -> dict[str, list[AdmittedTrialPlanModel]]:
    chains = defaultdict(list)
    for plan in plans.values():
        if plan is root:
            continue
        origin = plan.replacement_origin
        if (
            origin.root_plan_id != root.plan_id
            or origin.root_plan_digest != root.plan_digest
            or origin.root_entry_id not in root.entries
        ):
            raise ValueError("replacement root does not match the original allocation")
        chains[origin.root_entry_id].append(plan)
    return chains


def _follow_chain(
    root: AdmittedTrialPlanModel,
    entry_id: str,
    chain: list[AdmittedTrialPlanModel],
    by_version: _RunVersions,
    by_run_id: _RunsById,
    receipts: list[TrialCleanupReceiptModel],
) -> tuple[AdmittedTrialEntryModel, set[str]]:
    parent, leaf = root, root.entries[entry_id]
    used_superseded = set()
    for ordinal, child in enumerate(chain, 1):
        origin = child.replacement_origin
        expected_parent = entry_id if parent is root else leaf.plan_entry_id
        if (
            origin.ordinal != ordinal
            or origin.parent_plan_id != parent.plan_id
            or origin.parent_entry_id != expected_parent
        ):
            raise ValueError("replacement lineage must be contiguous and have exactly one successor")
        _validate_child(root, parent, child, origin, by_version, receipts)
        prior_versions = by_run_id[origin.parent_run_id]
        expected_versions = {
            origin.parent_run_version,
            build_superseded_trial_run(
                by_version[(origin.parent_run_id, origin.parent_run_version)], child
            ).run_version,
        }
        if {item.run_version for item in prior_versions} != expected_versions:
            raise ValueError("replaced parent has ambiguous archival versions")
        used_superseded.add(origin.parent_run_id)
        parent, leaf = child, next(iter(child.entries.values()))
    return leaf, used_superseded


def _leaf_run(
    leaf: AdmittedTrialEntryModel,
    chain: list[AdmittedTrialPlanModel],
    by_run_id: _RunsById,
) -> ExperimentRunModel | None:
    versions = by_run_id[leaf.run_id]
    if len(versions) > 1:
        raise ValueError("an unreplaced allocation slot has ambiguous archival versions")
    if chain and versions and versions[0].run_version != "1":
        raise ValueError("replacement first archival version must match its admitted supersession reference")
    return versions[0] if versions else None


def _eligible(run: ExperimentRunModel | None, policy: TrialReplacementPolicyModel | None) -> bool:
    from .experiment_analysis_eligibility import experiment_run_is_analysis_eligible

    return experiment_run_is_analysis_eligible(run, policy)


def _exhausted(
    run: ExperimentRunModel | None,
    policy: TrialReplacementPolicyModel | None,
    chain: list[AdmittedTrialPlanModel],
) -> bool:
    return bool(run and policy and policy.max_replacements and len(chain) == policy.max_replacements)


def _validate_original(root: AdmittedTrialPlanModel, replacement_plans: list[AdmittedTrialPlanModel]) -> None:
    if root.replacement_origin is not None:
        raise ValueError("replacement analysis requires an original plan")
    policy = root.replacement_policy
    if len(replacement_plans) > len(root.entries) * (policy.max_replacements if policy else 0):
        raise ValueError("replacement count exceeds the original allocation budget")


def reconcile_replacement_trials(
    original_plan: AdmittedTrialPlanModel,
    replacement_plans: list[AdmittedTrialPlanModel],
    runs: list[ExperimentRunModel],
    cleanup_receipts: list[TrialCleanupReceiptModel],
) -> ReplacementTrialReconciliation:
    """Validate complete retained lineage and return at most one analysis run per slot.

    Original and superseded archival versions remain in ``runs`` as evidence.
    Study evaluation membership must name only a returned eligible leaf. Failed
    scientific outcomes stay eligible when they have not been replaced.
    """
    root = _revalidated(original_plan)
    runs = [ExperimentRunModel.model_validate(run.model_dump(mode="python")) for run in runs]
    cleanup_receipts = [
        TrialCleanupReceiptModel.model_validate(item.model_dump(mode="python")) for item in cleanup_receipts
    ]
    _validate_original(root, replacement_plans)
    policy = root.replacement_policy
    plans, by_version, by_run_id = _index(root, replacement_plans, runs, cleanup_receipts)
    chains = _chains(root, plans)
    analysis = []
    shortfall = []
    exhausted = []
    used_superseded = set()
    for entry_id in sorted(root.entries):
        chain = sorted(chains[entry_id], key=lambda plan: plan.replacement_origin.ordinal)
        leaf, superseded = _follow_chain(root, entry_id, chain, by_version, by_run_id, cleanup_receipts)
        used_superseded.update(superseded)
        run = _leaf_run(leaf, chain, by_run_id)
        if _eligible(run, policy):
            analysis.append(run)
        else:
            shortfall.append(entry_id)
            if _exhausted(run, policy, chain):
                exhausted.append(entry_id)
    if any(run.run_status == "superseded" and run.run_id not in used_superseded for run in runs):
        raise ValueError("superseded run has no admitted replacement")
    return ReplacementTrialReconciliation(tuple(analysis), tuple(shortfall), tuple(exhausted))


__all__ = ["ReplacementTrialReconciliation", "reconcile_replacement_trials"]
