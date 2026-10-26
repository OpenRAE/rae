"""Runtime-owned inventory publication after strict backend proposal admission."""

from copy import deepcopy
from dataclasses import replace

from raes_contracts.materialization_inventory import InventoryInvariant
from raes_processor.planner.augmentation_admission import validate_actual_augmentation
from raes_processor.planner.materialization_admission import validate_materialization_archive_record
from raes_processor.planner.materialization_inventory import admit_runtime_inventory

from .backend_account_credentials import plan_has_account_credentials, value_free_backend_diagnostics
from .backend_call_contracts import _apply_result_contract_violation
from .backend_result_diagnostics import _backend_contract_invalid, _failed_apply_result
from .backend_snapshot_contracts import snapshot_shape_violation, snapshot_values_equal
from .diagnostics import _failure_diagnostic


def admit_refresh_proposal(result, previous, plan):
    """A read-only collector returns the exact predecessor and a separate report."""
    invalid = _apply_result_contract_violation(result, "runtime.inventory-refresh")
    if invalid is None and (not snapshot_values_equal(result.snapshot, previous) or result.changed_addresses):
        invalid = "Inventory collector changed the runtime-owned predecessor snapshot."
    if invalid is None and result.details:
        invalid = "Inventory collectors must not publish arbitrary result details."
    if invalid is not None:
        return _failed_apply_result(previous, _backend_contract_invalid("runtime.inventory-refresh", invalid))
    if plan_has_account_credentials(plan):
        result = replace(result, diagnostics=value_free_backend_diagnostics(result.diagnostics))
    return deepcopy(result)


def finalize_runtime_inventory(raw, accepted, context, previous, archive):
    """Publish admitted bytes before the accepted snapshot; refuse atomically."""
    if not accepted.success:
        return replace(accepted, materialization_attestation=None)
    stage = InventoryInvariant.SHAPE
    try:
        if raw.materialization_attestation is None or archive is None:
            raise ValueError("inventory report or archive owner is missing")
        admitted, snapshot = admit_runtime_inventory(
            raw.materialization_attestation,
            context.operation_plan,
            context.manifest,
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
        invariant = error.args[0] if type(error) is ValueError and len(error.args) == 1 else stage
        if not isinstance(invariant, InventoryInvariant):
            invariant = stage
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
    return replace(accepted, snapshot=snapshot, changed_addresses=sorted(changed), materialization_attestation=admitted)
