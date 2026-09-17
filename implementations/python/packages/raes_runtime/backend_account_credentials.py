"""Closed account-credential egress contract for backend execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from typing import cast

from raes_contracts.account_credentials import (
    account_placement_has_credential_bindings,
    value_free_account_placement_payload,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry

_APPROVED_REALIZATION_FIELDS = frozenset(
    {
        "entries",
        "realization_provenance",
        "realization_observations",
        "realization_envelope",
    }
)
_GENERIC_DIAGNOSTIC_MESSAGE = "Backend reported an account credential diagnostic."


def plan_has_account_credentials(plan: ProvisioningPlan) -> bool:
    """Return whether a provisioning plan exercises credential bindings."""

    return any(
        operation.resource_type == "account-placement" and account_placement_has_credential_bindings(operation.payload)
        for operation in plan.operations
    )


def plan_arguments_have_account_credentials(args: tuple[object, ...]) -> bool:
    """Return whether backend call arguments include a credential-bearing plan."""

    return any(isinstance(arg, ProvisioningPlan) and plan_has_account_credentials(arg) for arg in args)


def value_free_backend_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Preserve diagnostic identity while discarding backend-authored prose."""

    return [replace(diagnostic, message=_GENERIC_DIAGNOSTIC_MESSAGE) for diagnostic in diagnostics]


def sanitize_account_credential_result(
    result: ApplyResult,
    plan: ProvisioningPlan,
    baseline: RuntimeSnapshot,
) -> ApplyResult:
    """Validate and construct the closed value-free result for a credential plan."""

    if not plan_has_account_credentials(plan):
        return result
    if result.details:
        raise ValueError("credential-bearing backend results must not publish arbitrary details")
    diagnostics = value_free_backend_diagnostics(result.diagnostics)
    if not result.success and result.snapshot == baseline:
        return ApplyResult(success=False, snapshot=deepcopy(baseline), diagnostics=diagnostics)

    # A failed native readback can follow completed resource changes. Admit that
    # cleanup inventory only through the same closed, value-free projection as
    # successful results; arbitrary partial entries remain unsupported.
    _require_only_approved_snapshot_changes(result.snapshot, baseline)
    safe_entries = _closed_plan_entries(result.snapshot, baseline, plan)
    safe_snapshot = baseline.with_entries(
        safe_entries,
        realization_provenance=result.snapshot.realization_provenance,
        realization_observations=result.snapshot.realization_observations,
        realization_envelope=result.snapshot.realization_envelope,
    )
    return ApplyResult(
        success=result.success,
        snapshot=safe_snapshot,
        diagnostics=diagnostics,
        changed_addresses=list(result.changed_addresses),
    )


def _require_only_approved_snapshot_changes(snapshot: RuntimeSnapshot, baseline: RuntimeSnapshot) -> None:
    for snapshot_field in fields(RuntimeSnapshot):
        if snapshot_field.name in _APPROVED_REALIZATION_FIELDS:
            continue
        if getattr(snapshot, snapshot_field.name) != getattr(baseline, snapshot_field.name):
            raise ValueError("credential-bearing backend changed an unapproved snapshot carrier")


def _expected_entry_addresses(baseline: RuntimeSnapshot, plan: ProvisioningPlan) -> set[str]:
    expected_addresses = set(baseline.entries)
    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE:
            expected_addresses.discard(operation.address)
        else:
            expected_addresses.add(operation.address)
    return expected_addresses


def _closed_plan_entry(snapshot: RuntimeSnapshot, operation: ProvisionOp) -> SnapshotEntry:
    entry = snapshot.entries.get(operation.address)
    if entry is None:
        raise ValueError("credential-bearing backend omitted a submitted plan entry")
    expected_status = "unchanged" if operation.action is ChangeAction.UNCHANGED else "applied"
    if (
        entry.domain is not RuntimeDomain.PROVISIONING
        or entry.resource_type != operation.resource_type
        or entry.ordering_dependencies != operation.ordering_dependencies
        or entry.refresh_dependencies != operation.refresh_dependencies
        or entry.status != expected_status
        or entry.payload != operation.payload
    ):
        raise ValueError("credential-bearing backend entry does not match the submitted plan")
    payload = deepcopy(operation.payload)
    if operation.resource_type == "account-placement":
        payload = value_free_account_placement_payload(operation.payload)
    return cast(SnapshotEntry, replace(entry, payload=payload))


def _closed_plan_entries(
    snapshot: RuntimeSnapshot,
    baseline: RuntimeSnapshot,
    plan: ProvisioningPlan,
) -> dict[str, SnapshotEntry]:
    if set(snapshot.entries) != _expected_entry_addresses(baseline, plan):
        raise ValueError("credential-bearing backend returned entries outside the submitted plan")

    safe_entries = deepcopy(dict(baseline.entries))
    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE:
            safe_entries.pop(operation.address, None)
            continue
        safe_entries[operation.address] = _closed_plan_entry(snapshot, operation)
    return safe_entries


__all__ = [
    "plan_arguments_have_account_credentials",
    "plan_has_account_credentials",
    "sanitize_account_credential_result",
    "value_free_backend_diagnostics",
]
