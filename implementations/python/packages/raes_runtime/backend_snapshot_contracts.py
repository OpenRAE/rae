"""Exhaustive snapshot carrier classification and bounded shape admission."""

from dataclasses import fields

from pydantic_core import to_jsonable_python
from raes_contracts.addressing import require_compiled_address
from raes_contracts.canonical import jsonable_fallback
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileBindingModel
from raes_contracts.realization_structure import (
    ExactRealizationValue,
    structure_matches,
    validate_realization_value,
)
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from .diagnostics import _failure_diagnostic

# Addressed carriers are classified by the owner of their transition contract.
# Cross-domain effects require that owner's explicit call context, not merely a
# mutable dictionary in RuntimeSnapshot.
SNAPSHOT_CARRIER_OWNERS = {
    "entries": "resource",
    "orchestration_results": "orchestration",
    "orchestration_history": "orchestration",
    "evaluation_results": "evaluation",
    "evaluation_history": "evaluation",
    "proposition_truth_results": "evaluation",
    "participant_episode_results": "participant",
    "participant_episode_history": "participant",
    "participant_episode_closure_records": "participant",
    "participant_behavior_history": "participant",
    "participant_control_history": "participant",
    "participant_crossing_history": "participant",
    "information_state_history": "participant",
    "participant_autonomous_execution_states": "participant",
    "participant_execution_services": "participant",
    "participant_resource_budget_states": "runtime",
    "participant_resource_pool_states": "runtime",
    "participant_resource_budget_events": "runtime",
    "shared_state_records": "participant",
    "shared_state_history": "participant",
    "joint_action_records": "participant",
    "time_management_contexts": "participant",
}
SNAPSHOT_VALUE_OWNERS = {
    "time_model_state": "time",
    "realization_provenance": "runtime",
    "realization_observations": "observation",
    "realization_envelope": "realization",
    "metadata": "runtime",
}
# These are linked disclosure records, keyed by event/context IDs rather than
# portable resource addresses. Their participant owner validates reference and
# append-only obligations; their IDs are not ApplyResult.changed_addresses.
SNAPSHOT_RECORD_CARRIERS = frozenset(
    {
        "joint_action_records",
        "time_management_contexts",
        "participant_resource_pool_states",
        "participant_resource_budget_events",
    }
)
_VALUE_LIMITS = RUNTIME_SNAPSHOT_VALUE_LIMITS


def snapshot_values_equal(before: object, after: object) -> bool:
    """Compare admitted portable values through the incumbent exact relation."""

    return structure_matches(
        ExactRealizationValue(kind="exact"),
        to_jsonable_python(before, fallback=jsonable_fallback),
        to_jsonable_python(after, fallback=jsonable_fallback),
    )


def snapshot_shape_violation(snapshot: RuntimeSnapshot) -> str | None:
    if {field.name for field in fields(snapshot)} != SNAPSHOT_CARRIER_OWNERS.keys() | SNAPSHOT_VALUE_OWNERS.keys():
        return "Backend snapshot contains an unclassified carrier."
    for name in SNAPSHOT_CARRIER_OWNERS:
        carrier = getattr(snapshot, name)
        if not isinstance(carrier, dict):
            return "Backend snapshot contains an invalid addressed carrier."
        if len(carrier) > _VALUE_LIMITS.max_members or any(not isinstance(key, str) for key in carrier):
            return "Backend snapshot contains invalid or excessive carrier identities."
        if (
            name != "entries"
            and not validate_realization_value(carrier, limits=_VALUE_LIMITS, python_carriers=True).conformant
        ):
            return "Backend snapshot contains an invalid or excessive carrier value."
    if (
        not isinstance(snapshot.metadata, dict)
        or not validate_realization_value(snapshot.metadata, limits=_VALUE_LIMITS).conformant
    ):
        return "Backend snapshot contains invalid metadata."
    for entry in snapshot.entries.values():
        if not isinstance(entry, SnapshotEntry):
            return "Backend snapshot contains a non-SnapshotEntry resource."
        try:
            if (
                type(entry.profile_bindings) is not tuple
                or not validate_realization_value(entry.profile_bindings, python_carriers=True).conformant
            ):
                return "Backend snapshot contains invalid profile bindings."
            for binding in entry.profile_bindings:
                if not isinstance(binding, DomainProfileBindingModel):
                    return "Backend snapshot contains untyped profile bindings."
                DomainProfileBindingModel.model_validate(binding.model_dump(mode="json"))
        except (TypeError, ValueError, RecursionError):
            return "Backend snapshot contains invalid profile bindings."
        if (
            not isinstance(entry.payload, dict)
            or not validate_realization_value(entry.payload, limits=_VALUE_LIMITS, python_carriers=True).conformant
        ):
            return "Backend snapshot contains an invalid resource payload."
        if not isinstance(entry.status, str) or not entry.status or len(entry.status) > 128:
            return "Backend snapshot contains an invalid resource status."
        for dependencies in (entry.ordering_dependencies, entry.refresh_dependencies):
            if not isinstance(dependencies, tuple) or len(dependencies) > _VALUE_LIMITS.max_members:
                return "Backend snapshot contains invalid resource dependencies."
            try:
                for dependency in dependencies:
                    require_compiled_address(dependency, field_name="dependency address")
            except ValueError:
                return "Backend snapshot contains invalid resource dependencies."
    if not validate_realization_value(snapshot, limits=_VALUE_LIMITS, python_carriers=True).conformant:
        return "Backend snapshot exceeds the aggregate portable value bounds."
    return None


def snapshot_carrier_addresses(snapshot: RuntimeSnapshot) -> set[str]:
    addresses = {
        address
        for name in SNAPSHOT_CARRIER_OWNERS
        if name not in SNAPSHOT_RECORD_CARRIERS
        for address in getattr(snapshot, name)
    }
    if snapshot.time_model_state is not None:
        addresses.update(snapshot.time_model_state.clocks)
    return addresses


def snapshot_address_contract_diagnostics(snapshot: RuntimeSnapshot) -> list[Diagnostic]:
    for map_key, entry in snapshot.entries.items():
        try:
            require_compiled_address(map_key, field_name="snapshot map key")
            require_compiled_address(entry.address)
        except ValueError:
            message = "Backend snapshot contains a non-canonical resource address."
        else:
            if map_key == entry.address:
                continue
            message = "Backend snapshot map key does not equal its embedded address."
        return [_failure_diagnostic("runtime.backend-contract-invalid", "runtime.snapshot", message)]
    return []
