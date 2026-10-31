"""Shared runtime state and control-plane result contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from raes_contracts.addressing import require_compiled_address
from raes_contracts.contracts.materialization_attestation import require_materialization_records
from raes_contracts.contracts.mixed_runtime_history import iter_mixed_runtime_snapshot_violations
from raes_contracts.contracts.participant_outcome_history import require_outcome_history
from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolStateModel,
)
from raes_contracts.contracts.realization_plans import RealizationEnvelopeIdentityModel
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.diagnostics import Diagnostic, Severity, portable_diagnostic_payload
from raes_contracts.explicitness import ExplicitnessClass as _ExplicitnessClass
from raes_contracts.explicitness import ExplicitnessProvenance as _ExplicitnessProvenance
from raes_contracts.materialization import MaterializationSubmission
from raes_contracts.operation_lifecycle import (
    OperationAdmissionContext,
    OperationKind,
    OperationState,
    is_operation_transition_allowed,
    operation_terminal_diagnostic,
    operation_terminal_diagnostics,
    operation_transition_diagnostic,
    require_operation_terminal_diagnostics,
)
from raes_contracts.participant_autonomous_state import require_participant_autonomous_state_snapshot
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.snapshot_histories import seal_history
from raes_contracts.versions import OPERATION_SCHEMA_VERSION, RUNTIME_SNAPSHOT_SCHEMA_VERSION

from .immutable_history import HistoryMap

if TYPE_CHECKING:
    from raes_contracts.artifact_requirements import ArtifactSatisfactionDisclosureModel
    from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord
    from raes_contracts.domain_profiles import DomainProfileBindingModel


@dataclass(frozen=True)
class SnapshotEntry:
    """Recorded runtime state for a single canonical resource."""

    address: str
    domain: RuntimeDomain
    resource_type: str
    payload: dict[str, Any]
    ordering_dependencies: tuple[str, ...] = ()
    refresh_dependencies: tuple[str, ...] = ()
    status: str = "ready"
    profile_bindings: tuple[DomainProfileBindingModel, ...] = ()

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        for dependency in (*self.ordering_dependencies, *self.refresh_dependencies):
            require_compiled_address(dependency, field_name="dependency address")


@dataclass(frozen=True)
class RealizationProvenanceEntry:
    """SEM-218 provenance for one realized realization concern (invariant I5).

    Records, for a single realization concern that entered a runtime snapshot /
    result / history surface, its SEM-218 explicitness class and the origin of
    the realized value: ``author-declared`` (honoured exactly as the author
    wrote it), ``processor-derived`` (produced by deterministic processor
    activity), or ``backend-realized`` (picked by the backend from an open or
    constrained surface admitted by I3). It carries field-path and kind
    references only — never the realized value itself, which may carry sensitive
    material (SEM-218 host-exposure gate).
    """

    address: str
    field_path: str
    domain: str
    requirement_kind: str
    explicitness: _ExplicitnessClass
    provenance: _ExplicitnessProvenance
    governing_scope: str | None = None
    artifact_satisfaction: ArtifactSatisfactionDisclosureModel | None = None


@dataclass
class RuntimeSnapshot:
    """Current runtime snapshot."""

    entries: dict[str, SnapshotEntry] = field(default_factory=dict)
    orchestration_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    orchestration_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    evaluation_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    evaluation_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    proposition_truth_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    participant_episode_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    participant_episode_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_episode_closure_records: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_behavior_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_control_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_crossing_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_control_evaluation_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    mixed_composition_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    mixed_composition_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    information_state_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_outcome_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    participant_autonomous_execution_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    participant_execution_services: dict[str, dict[str, Any]] = field(default_factory=dict)
    participant_resource_budget_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    participant_resource_pool_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    participant_resource_budget_events: dict[str, dict[str, Any]] = field(default_factory=dict)
    shared_state_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    shared_state_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    joint_action_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    time_management_contexts: dict[str, dict[str, Any]] = field(default_factory=dict)
    time_model_state: TimeRuntimeStateModel | None = None
    # SEM-218 invariant I5: per-concern provenance for realized realization
    # concerns recorded across this snapshot's result / history surfaces.
    realization_provenance: tuple[RealizationProvenanceEntry, ...] = ()
    realization_observations: tuple[RealizationObservationDisclosure, ...] = ()
    materialization_attestations: tuple[MaterializationArchiveRecord, ...] = ()
    realization_envelope: RealizationEnvelopeIdentityModel | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:

        require_outcome_history(self.participant_outcome_history, self.participant_behavior_history)
        self.participant_control_evaluation_history = seal_history(
            "participant_control_evaluation_history", self.participant_control_evaluation_history
        )

        violations = list(
            iter_mixed_runtime_snapshot_violations(self.mixed_composition_states, self.mixed_composition_history)
        )
        if violations:
            raise ValueError(violations[0][1])
        require_materialization_records(self.materialization_attestations)
        for map_key, entry in self.entries.items():
            require_compiled_address(map_key, field_name="snapshot map key")
            if map_key != entry.address:
                raise ValueError("RuntimeSnapshot entries map key must equal embedded address")
        require_participant_autonomous_state_snapshot(self.participant_autonomous_execution_states)
        _require_participant_resource_budget_snapshot(
            self.participant_resource_budget_states,
            self.participant_resource_pool_states,
            self.participant_resource_budget_events,
        )
        if any(not isinstance(entry, RealizationObservationDisclosure) for entry in self.realization_observations):
            raise TypeError("RuntimeSnapshot realization_observations must contain typed disclosures")
        observation_keys = [
            (entry.address, entry.field_path, entry.domain, entry.requirement_kind)
            for entry in self.realization_observations
        ]
        if len(observation_keys) != len(set(observation_keys)):
            raise ValueError("RuntimeSnapshot realization_observations must identify unique concerns")

    def get(self, address: str) -> SnapshotEntry | None:
        return self.entries.get(address)

    def for_domain(self, domain: RuntimeDomain) -> dict[str, SnapshotEntry]:
        return {address: entry for address, entry in self.entries.items() if entry.domain == domain}

    def with_entries(
        self,
        entries: dict[str, SnapshotEntry],
        **updates: object,
    ) -> RuntimeSnapshot:
        _validate_snapshot_update_keys(updates)
        return RuntimeSnapshot(entries=entries, **_snapshot_updates(self, updates))


def _require_participant_resource_budget_snapshot(
    states: Mapping[str, Mapping[str, Any]],
    pools: Mapping[str, Mapping[str, Any]],
    events: Mapping[str, Mapping[str, Any]],
) -> None:

    for state_ref, payload in states.items():
        state = ParticipantResourceBudgetStateModel.model_validate(payload)
        if state_ref != state.state_ref:
            raise ValueError("participant resource-budget state key must equal state_ref")
    for pool_state_ref, payload in pools.items():
        pool = ParticipantResourcePoolStateModel.model_validate(payload)
        if pool_state_ref != pool.pool_state_ref:
            raise ValueError("participant resource-pool state key must equal pool_state_ref")
    for event_id, payload in events.items():
        event = ParticipantResourceBudgetEventModel.model_validate(payload)
        if event_id != event.event_id:
            raise ValueError("participant resource-budget event key must equal event_id")


@dataclass
class ApplyResult:
    """Result of applying or starting a runtime plan."""

    success: bool
    snapshot: RuntimeSnapshot
    diagnostics: list[Diagnostic] = field(default_factory=list)
    changed_addresses: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    # Transient verification input. Snapshot/store/API codecs never serialize it.
    operational_realization_observations: tuple[RealizationObservationDisclosure, ...] = ()
    materialization_attestation: MaterializationSubmission | None = None

    def __post_init__(self) -> None:
        validate_changed_addresses(self.changed_addresses)
        if self.materialization_attestation is not None and not isinstance(
            self.materialization_attestation, MaterializationSubmission
        ):
            raise TypeError("materialization attestation requires a typed SDL submission")
        if not isinstance(self.operational_realization_observations, tuple) or any(
            not isinstance(item, RealizationObservationDisclosure) for item in self.operational_realization_observations
        ):
            raise TypeError("operational realization observations must be a tuple of typed disclosures")


@dataclass(frozen=True)
class OperationReceipt:
    """Portable acknowledgment for an accepted control-plane operation."""

    operation_id: str
    domain: RuntimeDomain
    submitted_at: str
    accepted: bool
    context: OperationAdmissionContext
    schema_version: str = OPERATION_SCHEMA_VERSION
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _portable_operation_diagnostics(self.diagnostics))


@dataclass(frozen=True)
class OperationStatus:
    """Portable status for a submitted control-plane operation."""

    operation_id: str
    domain: RuntimeDomain
    state: OperationState
    submitted_at: str
    updated_at: str
    context: OperationAdmissionContext
    schema_version: str = OPERATION_SCHEMA_VERSION
    diagnostics: list[Diagnostic] = field(default_factory=list)
    changed_addresses: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        diagnostics = _portable_operation_diagnostics(self.diagnostics)
        if self.state in {
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.CANCELLED,
            OperationState.INDETERMINATE,
        }:
            diagnostics = operation_terminal_diagnostics(self.state, diagnostics)
        else:
            diagnostics = require_operation_terminal_diagnostics(self.state, diagnostics)
        object.__setattr__(self, "diagnostics", diagnostics)
        validate_changed_addresses(self.changed_addresses)


def _portable_operation_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    return [
        Diagnostic(
            code=payload["code"],
            domain=payload["domain"],
            address=payload["address"],
            message=payload["message"],
            severity=Severity(payload["severity"]),
        )
        for payload in (portable_diagnostic_payload(diagnostic) for diagnostic in diagnostics)
    ]


def validate_changed_addresses(addresses: list[str]) -> None:
    for address in addresses:
        require_compiled_address(address, field_name="changed address")
    if len(addresses) != len(set(addresses)):
        raise ValueError("changed addresses must be unique")


@dataclass(frozen=True)
class RuntimeSnapshotEnvelope:
    """Portable envelope around the current runtime snapshot."""

    schema_version: str = RUNTIME_SNAPSHOT_SCHEMA_VERSION
    snapshot: RuntimeSnapshot = field(default_factory=RuntimeSnapshot)


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
        "participant_control_evaluation_history": _history_update(
            updates,
            "participant_control_evaluation_history",
            snapshot.participant_control_evaluation_history,
        ),
        "mixed_composition_states": _mapping_update(
            updates, "mixed_composition_states", snapshot.mixed_composition_states
        ),
        "mixed_composition_history": _history_update(
            updates, "mixed_composition_history", snapshot.mixed_composition_history
        ),
        "information_state_history": _history_update(
            updates,
            "information_state_history",
            snapshot.information_state_history,
        ),
        "participant_outcome_history": _history_update(
            updates,
            "participant_outcome_history",
            snapshot.participant_outcome_history,
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
    "participant_control_evaluation_history",
    "mixed_composition_states",
    "mixed_composition_history",
    "information_state_history",
    "participant_outcome_history",
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
    if isinstance(raw if raw is not None else current, HistoryMap):
        return raw if raw is not None else current
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

    if key not in updates:
        return current
    raw = updates[key]
    if raw is None:
        return None
    if not isinstance(raw, TimeRuntimeStateModel):
        raise TypeError(f"{key} must be a TimeRuntimeStateModel")
    return raw


__all__ = [
    "ApplyResult",
    "OperationAdmissionContext",
    "OperationKind",
    "OperationReceipt",
    "OperationState",
    "OperationStatus",
    "RealizationObservationDisclosure",
    "RealizationProvenanceEntry",
    "RuntimeSnapshot",
    "RuntimeSnapshotEnvelope",
    "SnapshotEntry",
    "is_operation_transition_allowed",
    "operation_terminal_diagnostic",
    "operation_terminal_diagnostics",
    "operation_transition_diagnostic",
    "validate_changed_addresses",
]
