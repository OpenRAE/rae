"""Portable resource transitions under independently captured plan authority."""

from __future__ import annotations

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
    if entry.domain != domain:
        return "Backend changed a plan-owned runtime domain."
    if entry.resource_type != operation.resource_type:
        return "Backend changed a plan-owned resource type."
    if not snapshot_values_equal(entry.profile_bindings, getattr(operation, "profile_bindings", ())):
        return "Backend did not deliver its admitted profile completion."
    require_plan_operation_identity(domain, entry.address, entry.resource_type)
    if planned_resource_authored_name(operation) != planned_resource_authored_name(entry):
        return "Backend changed a plan-owned resource identity."
    if (
        entry.ordering_dependencies != operation.ordering_dependencies
        or entry.refresh_dependencies != operation.refresh_dependencies
    ):
        return "Backend changed plan-owned resource dependencies."
    return None


def _completed_transition(action: ChangeAction, previous: SnapshotEntry | None, actual: SnapshotEntry | None) -> bool:
    if action is ChangeAction.CREATE:
        return previous is None and actual is not None
    if action is ChangeAction.DELETE:
        return previous is not None and actual is None
    if action is ChangeAction.UPDATE:
        # Dependency refresh is a real UPDATE even with equal portable payloads.
        return previous is not None and actual is not None
    return previous is not None and _same_resource(previous, actual)


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
    next_entries = result.snapshot.entries
    for address in sorted(previous.entries.keys() | next_entries.keys()):
        before, after = previous.entries.get(address), next_entries.get(address)
        operation = operations.get(address)
        if operation is None:
            if before is None:
                return _invalid(address, "Backend added a resource without admitted collection authority.")
            if not _same_resource(before, after):
                return _invalid(address, "Backend changed a resource outside the submitted authority.")
        elif after is not None:
            message = _identity_violation(operation, after, domain)
            if message:
                return _invalid(address, message)
    for operation in plan.operations:
        before, after = previous.entries.get(operation.address), next_entries.get(operation.address)
        if result.success and not _completed_transition(operation.action, before, after):
            return _invalid(operation.address, "Backend did not complete the authorized resource transition.")
        changed = not _same_resource(before, after)
        required = changed or (result.success and operation.action is not ChangeAction.UNCHANGED)
        reported = operation.address in result.changed_addresses
        if required and not reported:
            return _invalid("runtime.changed-addresses", "Backend omitted an authorized resource change.")
        if reported and not required:
            return _invalid(
                "runtime.changed-addresses", "Backend reported a resource change without an authorized transition."
            )
    return []
