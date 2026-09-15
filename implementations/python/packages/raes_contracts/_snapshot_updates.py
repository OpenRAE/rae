"""Immutable field-update builders for :meth:`RuntimeSnapshot.with_entries`.

Split out of ``runtime_state.py`` (which reached the 500-line source cap) as a
cohesive unit: the per-field update primitives, the two update builders, the
combined builder, and the allowed-update-key guard. These are private helpers
used only by ``runtime_state.py``; the module deliberately avoids a top-level
import of ``runtime_state`` (types are string annotations under
``from __future__ import annotations`` or resolved through local imports) so
``runtime_state`` can import these builders without an import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from raes_contracts.realization_observation import RealizationObservationDisclosure

if TYPE_CHECKING:
    from raes_contracts.contracts import RealizationEnvelopeIdentityModel
    from raes_contracts.contracts.time_model import TimeRuntimeStateModel
    from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot


def _snapshot_result_updates(
    snapshot: RuntimeSnapshot,
    updates: Mapping[str, object],
) -> dict[str, Any]:
    return {
        "orchestration_results": _mapping_update(
            updates,
            "orchestration_results",
            snapshot.orchestration_results,
        ),
        "orchestration_history": _history_update(
            updates,
            "orchestration_history",
            snapshot.orchestration_history,
        ),
        "evaluation_results": _mapping_update(updates, "evaluation_results", snapshot.evaluation_results),
        "evaluation_history": _history_update(updates, "evaluation_history", snapshot.evaluation_history),
        "proposition_truth_results": _mapping_update(
            updates,
            "proposition_truth_results",
            snapshot.proposition_truth_results,
        ),
        "participant_episode_results": _mapping_update(
            updates,
            "participant_episode_results",
            snapshot.participant_episode_results,
        ),
        "participant_episode_history": _history_update(
            updates,
            "participant_episode_history",
            snapshot.participant_episode_history,
        ),
        "participant_episode_closure_records": _history_update(
            updates,
            "participant_episode_closure_records",
            snapshot.participant_episode_closure_records,
        ),
        "participant_behavior_history": _history_update(
            updates,
            "participant_behavior_history",
            snapshot.participant_behavior_history,
        ),
        "participant_control_history": _history_update(
            updates,
            "participant_control_history",
            snapshot.participant_control_history,
        ),
        "participant_crossing_history": _history_update(
            updates,
            "participant_crossing_history",
            snapshot.participant_crossing_history,
        ),
        "information_state_history": _history_update(
            updates,
            "information_state_history",
            snapshot.information_state_history,
        ),
    }


def _snapshot_participant_updates(
    snapshot: RuntimeSnapshot,
    updates: Mapping[str, object],
) -> dict[str, Any]:
    return {
        "participant_autonomous_execution_states": _mapping_update(
            updates,
            "participant_autonomous_execution_states",
            snapshot.participant_autonomous_execution_states,
        ),
        "participant_execution_services": _mapping_update(
            updates,
            "participant_execution_services",
            snapshot.participant_execution_services,
        ),
        "participant_resource_budget_states": _mapping_update(
            updates,
            "participant_resource_budget_states",
            snapshot.participant_resource_budget_states,
        ),
        "participant_resource_pool_states": _mapping_update(
            updates,
            "participant_resource_pool_states",
            snapshot.participant_resource_pool_states,
        ),
        "participant_resource_budget_events": _mapping_update(
            updates,
            "participant_resource_budget_events",
            snapshot.participant_resource_budget_events,
        ),
        "shared_state_records": _mapping_update(
            updates,
            "shared_state_records",
            snapshot.shared_state_records,
        ),
        "shared_state_history": _history_update(
            updates,
            "shared_state_history",
            snapshot.shared_state_history,
        ),
        "joint_action_records": _mapping_update(
            updates,
            "joint_action_records",
            snapshot.joint_action_records,
        ),
        "time_management_contexts": _mapping_update(
            updates,
            "time_management_contexts",
            snapshot.time_management_contexts,
        ),
    }


def _snapshot_updates(
    snapshot: RuntimeSnapshot,
    updates: Mapping[str, object],
) -> dict[str, Any]:
    return {
        **_snapshot_result_updates(snapshot, updates),
        "materialization_attestations": updates.get(
            "materialization_attestations", snapshot.materialization_attestations
        ),
        **_snapshot_participant_updates(snapshot, updates),
        "time_model_state": _time_model_state_update(
            updates,
            "time_model_state",
            snapshot.time_model_state,
        ),
        "realization_provenance": _provenance_update(
            updates,
            "realization_provenance",
            snapshot.realization_provenance,
        ),
        "realization_observations": _observation_disclosures_update(
            updates,
            "realization_observations",
            snapshot.realization_observations,
        ),
        "realization_envelope": _identity_update(
            updates,
            "realization_envelope",
            snapshot.realization_envelope,
        ),
        "metadata": _mapping_update(updates, "metadata", snapshot.metadata),
    }


_SNAPSHOT_UPDATE_KEYS = {
    "materialization_attestations",
    "orchestration_results",
    "orchestration_history",
    "evaluation_results",
    "evaluation_history",
    "proposition_truth_results",
    "participant_episode_results",
    "participant_episode_history",
    "participant_episode_closure_records",
    "participant_behavior_history",
    "participant_control_history",
    "participant_crossing_history",
    "information_state_history",
    "participant_autonomous_execution_states",
    "participant_execution_services",
    "participant_resource_budget_states",
    "participant_resource_pool_states",
    "participant_resource_budget_events",
    "shared_state_records",
    "shared_state_history",
    "joint_action_records",
    "time_management_contexts",
    "time_model_state",
    "realization_provenance",
    "realization_observations",
    "realization_envelope",
    "metadata",
}


def _validate_snapshot_update_keys(updates: Mapping[str, object]) -> None:
    unknown = sorted(key for key in updates if key not in _SNAPSHOT_UPDATE_KEYS)
    if unknown:
        raise TypeError("unknown runtime snapshot update fields: " + ", ".join(unknown))


def _mapping_update(
    updates: Mapping[str, object],
    key: str,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    raw = updates.get(key)
    if raw is None:
        return dict(current)
    if not isinstance(raw, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return dict(raw)


def _history_update(
    updates: Mapping[str, object],
    key: str,
    current: Mapping[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    raw = updates.get(key)
    if raw is None:
        return {address: list(events) for address, events in current.items()}
    if not isinstance(raw, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return {str(address): list(events) for address, events in raw.items()}


def _provenance_update(
    updates: Mapping[str, object],
    key: str,
    current: tuple[RealizationProvenanceEntry, ...],
) -> tuple[RealizationProvenanceEntry, ...]:
    from raes_contracts.runtime_state import RealizationProvenanceEntry

    raw = updates.get(key)
    if raw is None:
        return tuple(current)
    if not isinstance(raw, tuple) or any(not isinstance(entry, RealizationProvenanceEntry) for entry in raw):
        raise TypeError(f"{key} must be a tuple of RealizationProvenanceEntry")
    return raw


def _observation_disclosures_update(
    updates: Mapping[str, object],
    key: str,
    current: tuple[RealizationObservationDisclosure, ...],
) -> tuple[RealizationObservationDisclosure, ...]:
    raw = updates.get(key)
    if raw is None:
        return tuple(current)
    if not isinstance(raw, tuple) or any(not isinstance(entry, RealizationObservationDisclosure) for entry in raw):
        raise TypeError(f"{key} must be a tuple of RealizationObservationDisclosure")
    return raw


def _identity_update(
    updates: Mapping[str, object],
    key: str,
    current: RealizationEnvelopeIdentityModel | None,
) -> RealizationEnvelopeIdentityModel | None:
    from raes_contracts.contracts import RealizationEnvelopeIdentityModel

    raw = updates.get(key)
    if raw is None:
        return current
    if not isinstance(raw, RealizationEnvelopeIdentityModel):
        raise TypeError(f"{key} must be a RealizationEnvelopeIdentityModel")
    return raw


def _time_model_state_update(
    updates: Mapping[str, object],
    key: str,
    current: TimeRuntimeStateModel | None,
) -> TimeRuntimeStateModel | None:
    from raes_contracts.contracts.time_model import TimeRuntimeStateModel

    if key not in updates:
        return current
    raw = updates[key]
    if raw is None:
        return None
    if not isinstance(raw, TimeRuntimeStateModel):
        raise TypeError(f"{key} must be a TimeRuntimeStateModel")
    return raw
