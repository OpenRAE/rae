"""Runtime-owned inventory publication after strict backend proposal admission."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.materialization import MaterializationArchive
from raes_contracts.materialization_inventory import InventoryInvariant
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.planner.augmentation_admission import validate_actual_augmentation
from raes_processor.planner.materialization_admission import validate_materialization_archive_record
from raes_processor.planner.materialization_inventory import admit_runtime_inventory

from .backend_account_credentials import plan_has_account_credentials, value_free_backend_diagnostics
from .backend_call_contracts import _apply_result_contract_violation
from .backend_result_diagnostics import _backend_contract_invalid, _failed_apply_result
from .backend_snapshot_contracts import snapshot_shape_violation, snapshot_values_equal
from .diagnostics import _failure_diagnostic

if TYPE_CHECKING:
    from .backend_realization_authority import _RealizationApplyContext


def admit_refresh_proposal(result: object, previous: RuntimeSnapshot, plan: ProvisioningPlan) -> ApplyResult:
    """A read-only collector returns the exact predecessor and a separate report."""
    invalid = _apply_result_contract_violation(result, "runtime.inventory-refresh")
    candidate = cast(ApplyResult, result)
    if invalid is None and (not snapshot_values_equal(candidate.snapshot, previous) or candidate.changed_addresses):
        invalid = "Inventory collector changed the runtime-owned predecessor snapshot."
    if invalid is None and candidate.details:
        invalid = "Inventory collectors must not publish arbitrary result details."
    if invalid is not None:
        return _failed_apply_result(previous, _backend_contract_invalid("runtime.inventory-refresh", invalid))
    if plan_has_account_credentials(plan):
        candidate = replace(candidate, diagnostics=value_free_backend_diagnostics(candidate.diagnostics))
    return deepcopy(candidate)


def finalize_runtime_inventory(
    raw: ApplyResult,
    accepted: ApplyResult,
    context: _RealizationApplyContext,
    previous: RuntimeSnapshot,
    archive: MaterializationArchive | None,
) -> ApplyResult:
    """Publish admitted bytes before the accepted snapshot; refuse atomically."""
    if not accepted.success:
        return cast(ApplyResult, replace(accepted, materialization_attestation=None))
    stage = InventoryInvariant.SHAPE
    try:
        if raw.materialization_attestation is None or archive is None:
            raise ValueError("inventory report or archive owner is missing")
        request, manifest = _inventory_context(context)
        admitted, snapshot = admit_runtime_inventory(
            raw.materialization_attestation,
            request,
            manifest,
            previous,
            accepted.snapshot,
            archive,
        )
        validate_actual_augmentation(admitted, context.augmentation)
        if snapshot_shape_violation(snapshot):
            raise ValueError(InventoryInvariant.SHAPE)
        stage = InventoryInvariant.ARCHIVE
        record = archive.publish(admitted.sdl)
        validate_materialization_archive_record(admitted, record)
        snapshot = snapshot.with_entries(
            dict(snapshot.entries), materialization_attestations=(*previous.materialization_attestations, record)
        )
        if snapshot_shape_violation(snapshot):
            raise ValueError(InventoryInvariant.SHAPE)
    except Exception as error:
        invariant = _inventory_failure_invariant(error, stage)
        return _failed_apply_result(
            deepcopy(previous),
            _failure_diagnostic(
                f"runtime.inventory-{invariant.value}-invalid",
                "runtime.inventory",
                "Inventory report, authority, lineage, coverage or protected archival delivery is invalid.",
            ),
        )
    changed = set(accepted.changed_addresses)
    changed.update(
        address
        for address in previous.entries.keys() | snapshot.entries.keys()
        if not snapshot_values_equal(previous.get(address), snapshot.get(address))
    )
    return cast(
        ApplyResult,
        replace(accepted, snapshot=snapshot, changed_addresses=sorted(changed), materialization_attestation=admitted),
    )


def _inventory_context(context: _RealizationApplyContext) -> tuple[ProvisioningPlan, BackendManifest]:
    request, manifest = context.operation_plan, context.manifest
    if not isinstance(request, ProvisioningPlan) or manifest is None:
        raise ValueError(InventoryInvariant.BINDING)
    return request, manifest


def _inventory_failure_invariant(error: Exception, stage: InventoryInvariant) -> InventoryInvariant:
    invariant = error.args[0] if type(error) is ValueError and len(error.args) == 1 else stage
    if not isinstance(invariant, InventoryInvariant):
        invariant = stage
    return invariant
