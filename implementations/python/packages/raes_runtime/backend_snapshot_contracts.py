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


def _carrier_classification_violation(snapshot: RuntimeSnapshot) -> str | None:
    """Require every snapshot field to be claimed by a declared transition owner."""

    if {field.name for field in fields(snapshot)} != SNAPSHOT_CARRIER_OWNERS.keys() | SNAPSHOT_VALUE_OWNERS.keys():
        return "Backend snapshot contains an unclassified carrier."
    return None


def _carrier_identity_violation(carrier: object) -> str | None:
    """Admit one addressed carrier as a bounded, string-keyed mapping."""

    if not isinstance(carrier, dict):
        return "Backend snapshot contains an invalid addressed carrier."
    if len(carrier) > _VALUE_LIMITS.max_members or any(not isinstance(key, str) for key in carrier):
        return "Backend snapshot contains invalid or excessive carrier identities."
    return None


def _carrier_value_violation(name: str, carrier: object) -> str | None:
    """Admit a non-entry carrier's aggregate portable value.

    ``entries`` carries typed resource records admitted entry by entry below,
    so only the remaining carriers are bounded as opaque portable values here.
    """

    if name == "entries" or validate_realization_value(carrier, limits=_VALUE_LIMITS, python_carriers=True).conformant:
        return None
    return "Backend snapshot contains an invalid or excessive carrier value."


def _carrier_violation(snapshot: RuntimeSnapshot) -> str | None:
    """Admit every addressed carrier's identities and portable value bounds."""

    for name in SNAPSHOT_CARRIER_OWNERS:
        carrier = getattr(snapshot, name)
        violation = _carrier_identity_violation(carrier) or _carrier_value_violation(name, carrier)
        if violation is not None:
            return violation
    return None


def _metadata_violation(snapshot: RuntimeSnapshot) -> str | None:
    """Admit snapshot metadata as a bounded portable mapping."""

    if (
        isinstance(snapshot.metadata, dict)
        and validate_realization_value(snapshot.metadata, limits=_VALUE_LIMITS).conformant
    ):
        return None
    return "Backend snapshot contains invalid metadata."


def _typed_profile_binding_violation(entry: SnapshotEntry) -> str | None:
    """Require every profile binding to be a bounded, revalidating typed model."""

    if (
        type(entry.profile_bindings) is not tuple
        or not validate_realization_value(entry.profile_bindings, python_carriers=True).conformant
    ):
        return "Backend snapshot contains invalid profile bindings."
    for binding in entry.profile_bindings:
        if not isinstance(binding, DomainProfileBindingModel):
            return "Backend snapshot contains untyped profile bindings."
        DomainProfileBindingModel.model_validate(binding.model_dump(mode="json"))
    return None


def _profile_binding_violation(entry: SnapshotEntry) -> str | None:
    """Admit one entry's profile bindings, treating any refusal as invalid bindings."""

    try:
        return _typed_profile_binding_violation(entry)
    except (TypeError, ValueError, RecursionError):
        return "Backend snapshot contains invalid profile bindings."


def _payload_violation(entry: SnapshotEntry) -> str | None:
    """Admit one entry payload as a bounded portable mapping."""

    if (
        isinstance(entry.payload, dict)
        and validate_realization_value(entry.payload, limits=_VALUE_LIMITS, python_carriers=True).conformant
    ):
        return None
    return "Backend snapshot contains an invalid resource payload."


def _status_violation(entry: SnapshotEntry) -> str | None:
    """Admit one entry status as a bounded, non-empty string."""

    if not isinstance(entry.status, str) or not entry.status or len(entry.status) > 128:
        return "Backend snapshot contains an invalid resource status."
    return None


def _compiled_dependency_addresses(dependencies: tuple[object, ...]) -> bool:
    """Report whether every dependency in one collection is a compiled address."""

    try:
        for dependency in dependencies:
            require_compiled_address(dependency, field_name="dependency address")
    except ValueError:
        return False
    return True


def _dependency_violation(entry: SnapshotEntry) -> str | None:
    """Admit one entry's ordering and refresh dependency collections."""

    for dependencies in (entry.ordering_dependencies, entry.refresh_dependencies):
        if not isinstance(dependencies, tuple) or len(dependencies) > _VALUE_LIMITS.max_members:
            return "Backend snapshot contains invalid resource dependencies."
        if not _compiled_dependency_addresses(dependencies):
            return "Backend snapshot contains invalid resource dependencies."
    return None


def _entry_violation(entry: object) -> str | None:
    """Admit one snapshot resource entry against its bounded shape contract."""

    if not isinstance(entry, SnapshotEntry):
        return "Backend snapshot contains a non-SnapshotEntry resource."
    return (
        _profile_binding_violation(entry)
        or _payload_violation(entry)
        or _status_violation(entry)
        or _dependency_violation(entry)
    )


def _entries_violation(snapshot: RuntimeSnapshot) -> str | None:
    """Admit every resource entry, reporting the first one that is not portable."""

    for entry in snapshot.entries.values():
        violation = _entry_violation(entry)
        if violation is not None:
            return violation
    return None


def _aggregate_violation(snapshot: RuntimeSnapshot) -> str | None:
    """Admit the snapshot's aggregate portable value bounds."""

    if validate_realization_value(snapshot, limits=_VALUE_LIMITS, python_carriers=True).conformant:
        return None
    return "Backend snapshot exceeds the aggregate portable value bounds."


def snapshot_shape_violation(snapshot: RuntimeSnapshot) -> str | None:
    """Name the first bounded-shape violation a backend snapshot carries, if any.

    The checks stay ordered from the whole snapshot inwards - carrier
    classification, carrier shape, metadata, resource entries, then the
    aggregate bound - so the reported message names the outermost refusal.
    """

    return (
        _carrier_classification_violation(snapshot)
        or _carrier_violation(snapshot)
        or _metadata_violation(snapshot)
        or _entries_violation(snapshot)
        or _aggregate_violation(snapshot)
    )


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
