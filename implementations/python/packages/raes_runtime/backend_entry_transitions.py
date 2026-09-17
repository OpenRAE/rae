"""Portable resource transitions under independently captured plan authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import (
    ChangeAction,
    EvaluationPlan,
    OrchestrationPlan,
    PlanOperation,
    ProvisioningPlan,
    RuntimeDomain,
    planned_resource_authored_name,
    require_plan_operation_identity,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry

from .backend_snapshot_contracts import snapshot_values_equal
from .diagnostics import _failure_diagnostic

_PLAN_DOMAINS = {
    ProvisioningPlan: RuntimeDomain.PROVISIONING,
    OrchestrationPlan: RuntimeDomain.ORCHESTRATION,
    EvaluationPlan: RuntimeDomain.EVALUATION,
}


def _invalid(address: str, message: str) -> list[Diagnostic]:
    return [_failure_diagnostic("runtime.backend-contract-invalid", address, message)]


def _same_resource(previous: SnapshotEntry | None, actual: SnapshotEntry | None) -> bool:
    """Status annotations do not describe a change to resource semantics."""

    if previous is None or actual is None:
        return previous is actual
    return (
        replace(previous, status="ready", payload={}, profile_bindings=())
        == replace(actual, status="ready", payload={}, profile_bindings=())
        and snapshot_values_equal(previous.payload, actual.payload)
        and snapshot_values_equal(previous.profile_bindings, actual.profile_bindings)
    )


def _identity_violation(operation: PlanOperation, entry: SnapshotEntry, domain: RuntimeDomain) -> str | None:
    ownership = (
        (entry.domain != domain, "Backend changed a plan-owned runtime domain."),
        (entry.resource_type != operation.resource_type, "Backend changed a plan-owned resource type."),
        (
            not snapshot_values_equal(entry.profile_bindings, getattr(operation, "profile_bindings", ())),
            "Backend did not deliver its admitted profile completion.",
        ),
    )
    violation = next((message for violated, message in ownership if violated), None)
    if violation:
        return violation
    require_plan_operation_identity(domain, entry.address, entry.resource_type)
    residual = (
        (
            planned_resource_authored_name(operation) != planned_resource_authored_name(entry),
            "Backend changed a plan-owned resource identity.",
        ),
        (
            entry.ordering_dependencies != operation.ordering_dependencies
            or entry.refresh_dependencies != operation.refresh_dependencies,
            "Backend changed plan-owned resource dependencies.",
        ),
    )
    return next((message for violated, message in residual if violated), None)


def _completed_transition(action: ChangeAction, previous: SnapshotEntry | None, actual: SnapshotEntry | None) -> bool:
    # Dependency refresh is a real UPDATE even with equal portable payloads.
    completed = {
        ChangeAction.CREATE: previous is None and actual is not None,
        ChangeAction.DELETE: previous is not None and actual is None,
        ChangeAction.UPDATE: previous is not None and actual is not None,
    }
    return completed.get(action, previous is not None and _same_resource(previous, actual))


def _unowned_entry_violation(
    address: str, before: SnapshotEntry | None, after: SnapshotEntry | None
) -> list[Diagnostic]:
    """Refuse a transition at an address the plan never granted."""

    if before is None:
        return _invalid(address, "Backend added a resource without admitted collection authority.")
    unowned_change = not _same_resource(before, after)
    return _invalid(address, "Backend changed a resource outside the submitted authority.") if unowned_change else []


def _entry_authority_violation(
    address: str,
    operation: PlanOperation | None,
    before: SnapshotEntry | None,
    after: SnapshotEntry | None,
    domain: RuntimeDomain,
) -> list[Diagnostic]:
    """Refuse one address whose transition leaves the plan's granted authority."""

    if operation is None:
        return _unowned_entry_violation(address, before, after)
    message = None if after is None else _identity_violation(operation, after, domain)
    return _invalid(address, message) if message else []


def _entry_identity_diagnostics(
    result: ApplyResult,
    previous: RuntimeSnapshot,
    operations: Mapping[str, PlanOperation],
    domain: RuntimeDomain,
) -> list[Diagnostic]:
    """Check every observed address against the authority the plan granted."""

    next_entries = result.snapshot.entries
    for address in sorted(previous.entries.keys() | next_entries.keys()):
        diagnostics = _entry_authority_violation(
            address,
            operations.get(address),
            previous.entries.get(address),
            next_entries.get(address),
            domain,
        )
        if diagnostics:
            return diagnostics
    return []


def _change_accounting_violation(operation: PlanOperation, result: ApplyResult, *, changed: bool) -> list[Diagnostic]:
    """Require the reported change set and the authorized transition to agree."""

    required = changed or (result.success and operation.action is not ChangeAction.UNCHANGED)
    reported = operation.address in result.changed_addresses
    if required and not reported:
        return _invalid("runtime.changed-addresses", "Backend omitted an authorized resource change.")
    if reported and not required:
        return _invalid(
            "runtime.changed-addresses", "Backend reported a resource change without an authorized transition."
        )
    return []


def _operation_accounting_violation(
    operation: PlanOperation, result: ApplyResult, previous: RuntimeSnapshot
) -> list[Diagnostic]:
    """Require one operation's completion and its reported change to agree."""

    before = previous.entries.get(operation.address)
    after = result.snapshot.entries.get(operation.address)
    if result.success and not _completed_transition(operation.action, before, after):
        return _invalid(operation.address, "Backend did not complete the authorized resource transition.")
    return _change_accounting_violation(operation, result, changed=not _same_resource(before, after))


def _plan_accounting_diagnostics(
    result: ApplyResult, previous: RuntimeSnapshot, plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan
) -> list[Diagnostic]:
    """Check every submitted operation's completion and change accounting."""

    for operation in plan.operations:
        accounting = _operation_accounting_violation(operation, result, previous)
        if accounting:
            return accounting
    return []


def backend_entry_transition_diagnostics(
    result: ApplyResult,
    previous: RuntimeSnapshot,
    plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan | None,
) -> list[Diagnostic]:
    """Check identity, permitted effects and accounting before value comparison.

    A legacy plan grants only its explicit operations. Additional membership
    requires a separately admitted enclosing collection contract, not an open
    concern inside one operation. Failed results may retain partial cleanup
    inventory, but cannot rewrite authority or unowned predecessor resources.
    """

    if plan is None:
        return []
    domain = next(owner for kind, owner in _PLAN_DOMAINS.items() if isinstance(plan, kind))
    operations = {operation.address: operation for operation in plan.operations}
    identity = _entry_identity_diagnostics(result, previous, operations, domain)
    return identity or _plan_accounting_diagnostics(result, previous, plan)
