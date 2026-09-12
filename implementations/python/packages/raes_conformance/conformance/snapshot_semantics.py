"""Runtime-snapshot semantic diagnostics for conformance."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raes_contracts.contracts import (
    ParticipantInformationStateContextResolver,
    RuntimeSnapshotEnvelopeModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_autonomous_state import (
    iter_participant_autonomous_runtime_snapshot_violations,
    iter_participant_autonomous_state_snapshot_violations,
)
from raes_contracts.participant_concurrency import iter_participant_concurrency_snapshot_violations
from raes_contracts.participant_episode import iter_participant_episode_snapshot_violations
from raes_contracts.participant_episode_closure import iter_participant_episode_closure_violations
from raes_contracts.participant_information_state_history import (
    iter_participant_information_state_snapshot_violations,
)
from raes_contracts.participant_shared_state import iter_participant_shared_state_snapshot_violations
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_observation import ObservedOperatingSystemIdentity
from raes_contracts.runtime_state import RealizationObservationDisclosure, RuntimeSnapshot, SnapshotEntry
from raes_processor.models import (
    ParticipantActionContractRuntime,
    ParticipantHistoryAddressScope,
    ParticipantObservationBoundaryRuntime,
    iter_participant_behavior_history_violations,
    iter_participant_behavior_joint_action_violations,
)
from raes_runtime.result_contracts import (
    evaluation_result_contract_diagnostics,
    workflow_result_contract_diagnostics,
)

from raes_conformance.conformance.diagnostics import _SEMANTIC_INVALID_DIAGNOSTIC_CODE, _diagnostic


def _snapshot_entries(validated: RuntimeSnapshotEnvelopeModel) -> dict[str, SnapshotEntry]:
    return {
        address: SnapshotEntry(
            address=entry.address,
            domain=RuntimeDomain(entry.domain),
            resource_type=entry.resource_type,
            payload=dict(entry.payload),
            ordering_dependencies=tuple(entry.ordering_dependencies),
            refresh_dependencies=tuple(entry.refresh_dependencies),
            status=entry.status,
        )
        for address, entry in validated.entries.items()
    }


def _realization_disclosures(
    validated: RuntimeSnapshotEnvelopeModel,
) -> tuple[RealizationObservationDisclosure, ...]:
    return tuple(
        RealizationObservationDisclosure(
            address=entry.address,
            field_path=entry.field_path,
            domain=entry.domain,
            requirement_kind=entry.requirement_kind,
            verification_scope=entry.verification_scope,
            observation_strength=entry.observation_strength,
            observed_value=entry.observed_value,
            operating_system=(
                ObservedOperatingSystemIdentity(
                    family=entry.operating_system.family,
                    distribution=entry.operating_system.distribution,
                    version=entry.operating_system.version,
                )
                if entry.operating_system is not None
                else None
            ),
            operation_id=entry.operation_id,
            envelope_digest=entry.envelope_digest,
            configuration_digest=entry.configuration_digest,
            observer_version=entry.observer_version,
            sequence=entry.sequence,
            binding_verified=entry.binding_verified,
        )
        for entry in validated.realization_observations
    )


def _snapshot_from_envelope(payload: dict[str, Any]) -> RuntimeSnapshot:
    validated = RuntimeSnapshotEnvelopeModel.model_validate(payload)
    return RuntimeSnapshot(
        entries=_snapshot_entries(validated),
        orchestration_results={
            address: result.model_dump(mode="json") for address, result in validated.orchestration_results.items()
        },
        orchestration_history={
            address: [event.model_dump(mode="json") for event in history]
            for address, history in validated.orchestration_history.items()
        },
        evaluation_results={
            address: result.model_dump(mode="json") for address, result in validated.evaluation_results.items()
        },
        evaluation_history={
            address: [event.model_dump(mode="json") for event in history]
            for address, history in validated.evaluation_history.items()
        },
        participant_episode_results={
            participant_address: result.model_dump(mode="json")
            for participant_address, result in validated.participant_episode_results.items()
        },
        participant_episode_history={
            participant_address: [event.model_dump(mode="json") for event in history]
            for participant_address, history in validated.participant_episode_history.items()
        },
        participant_episode_closure_records={
            participant_address: [dict(record) for record in records]
            for participant_address, records in validated.participant_episode_closure_records.items()
        },
        participant_behavior_history={
            participant_address: [event.model_dump(mode="json") for event in history]
            for participant_address, history in validated.participant_behavior_history.items()
        },
        information_state_history={
            participant_address: [record.model_dump(mode="json") for record in history]
            for participant_address, history in validated.information_state_history.items()
        },
        participant_autonomous_execution_states={
            state_address: state.model_dump(mode="json")
            for state_address, state in validated.participant_autonomous_execution_states.items()
        },
        participant_execution_services={
            scope: state.model_dump(mode="json") for scope, state in validated.participant_execution_services.items()
        },
        participant_resource_budget_states={
            state_ref: state.model_dump(mode="json")
            for state_ref, state in validated.participant_resource_budget_states.items()
        },
        participant_resource_pool_states={
            pool_state_ref: state.model_dump(mode="json")
            for pool_state_ref, state in validated.participant_resource_pool_states.items()
        },
        participant_resource_budget_events={
            event_id: event.model_dump(mode="json")
            for event_id, event in validated.participant_resource_budget_events.items()
        },
        shared_state_records={
            state_address: record.model_dump(mode="json")
            for state_address, record in validated.shared_state_records.items()
        },
        shared_state_history={
            state_address: [record.model_dump(mode="json") for record in records]
            for state_address, records in validated.shared_state_history.items()
        },
        joint_action_records={
            record_id: record.model_dump(mode="json") for record_id, record in validated.joint_action_records.items()
        },
        time_management_contexts={
            context_id: context.model_dump(mode="json")
            for context_id, context in validated.time_management_contexts.items()
        },
        time_model_state=validated.time_model_state,
        realization_observations=_realization_disclosures(validated),
        metadata=dict(validated.metadata),
    )


def _participant_episode_snapshot_diagnostics(
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    """Surface participant-episode snapshot invariants as conformance diagnostics.

    Delegates to ``iter_participant_episode_snapshot_violations`` so the
    conformance path and the manager apply path share one source of truth
    for every RUN-311 invariant, and wraps each violation in a
    ``conformance.semantic-invalid`` diagnostic.
    """

    return [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_episode_snapshot_violations(
            snapshot.participant_episode_results,
            snapshot.participant_episode_history,
        )
    ]


def _participant_episode_closure_snapshot_diagnostics(
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    return [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_episode_closure_violations(
            snapshot.participant_episode_closure_records,
            snapshot.participant_episode_history,
        )
    ]


def _participant_behavior_snapshot_references(
    snapshot: RuntimeSnapshot,
) -> tuple[
    set[str],
    dict[str, ParticipantActionContractRuntime],
    set[str],
    dict[str, ParticipantObservationBoundaryRuntime],
    dict[str, set[str]],
    dict[str, set[str]],
]:
    action_contract_addresses: set[str] = set()
    action_contracts: dict[str, ParticipantActionContractRuntime] = {}
    observation_boundary_addresses: set[str] = set()
    observation_boundaries: dict[str, ParticipantObservationBoundaryRuntime] = {}
    participant_action_addresses: dict[str, set[str]] = {}
    participant_observation_boundary_addresses: dict[str, set[str]] = {}
    for entry_address, entry in snapshot.entries.items():
        for candidate in {entry_address, entry.address}:
            if candidate.startswith("participant.action-contract."):
                action_contract_addresses.add(candidate)
                action_contracts[candidate] = ParticipantActionContractRuntime(
                    address=candidate,
                    name=str(entry.payload.get("name", "")),
                    action_name=str(entry.payload.get("action_name", "")),
                    semantic_version=str(entry.payload.get("semantic_version", "")),
                    lifecycle_state=str(entry.payload.get("lifecycle_state", "")),
                    behavioral_granularity=str(entry.payload.get("behavioral_granularity", "")),
                    precondition_classes=tuple(str(item) for item in entry.payload.get("precondition_classes", ())),
                    effect_classes=tuple(str(item) for item in entry.payload.get("effect_classes", ())),
                    failure_classes=tuple(str(item) for item in entry.payload.get("failure_classes", ())),
                    backend_failure_mappings=tuple(
                        dict(item)
                        for item in entry.payload.get("backend_failure_mappings", ())
                        if isinstance(item, Mapping)
                    ),
                    interaction_classes=tuple(str(item) for item in entry.payload.get("interaction_classes", ())),
                    shared_state_refs=tuple(str(item) for item in entry.payload.get("shared_state_refs", ())),
                    spec=(
                        dict(entry.payload.get("spec", {}))
                        if isinstance(entry.payload.get("spec", {}), Mapping)
                        else {}
                    ),
                )
            elif candidate.startswith("participant.observation-boundary."):
                observation_boundary_addresses.add(candidate)
                observation_boundaries[candidate] = ParticipantObservationBoundaryRuntime(
                    address=candidate,
                    name=str(entry.payload.get("name", "")),
                    boundary_name=str(entry.payload.get("boundary_name", "")),
                    projection_basis=str(entry.payload.get("projection_basis", "")),
                    hidden_refs=tuple(str(ref) for ref in entry.payload.get("hidden_refs", ())),
                    observable_refs=tuple(str(ref) for ref in entry.payload.get("observable_refs", ())),
                    evidence_refs=tuple(str(ref) for ref in entry.payload.get("evidence_refs", ())),
                    disclosed_refs=tuple(str(ref) for ref in entry.payload.get("disclosed_refs", ())),
                    evidence_only_refs=tuple(str(ref) for ref in entry.payload.get("evidence_only_refs", ())),
                    discovered_refs=tuple(str(ref) for ref in entry.payload.get("discovered_refs", ())),
                    inferred_refs=tuple(str(ref) for ref in entry.payload.get("inferred_refs", ())),
                    concealed_refs=tuple(str(ref) for ref in entry.payload.get("concealed_refs", ())),
                    deceptive_refs=tuple(str(ref) for ref in entry.payload.get("deceptive_refs", ())),
                    view_transitions=tuple(dict(item) for item in entry.payload.get("view_transitions", ())),
                    view_relation_timeline=tuple(
                        dict(item) for item in entry.payload.get("view_relation_timeline", ())
                    ),
                    realized_view_disclosure=str(entry.payload.get("realized_view_disclosure", "")),
                    spec=dict(entry.payload.get("spec", {})),
                )
            elif candidate.startswith("participant.behavior."):
                participant_action_addresses[candidate] = {
                    str(address)
                    for address in entry.payload.get("action_contract_addresses", ())
                    if isinstance(address, str) and address
                }
                participant_observation_boundary_addresses[candidate] = {
                    str(address)
                    for address in entry.payload.get("observation_boundary_addresses", ())
                    if isinstance(address, str) and address
                }
    return (
        action_contract_addresses,
        action_contracts,
        observation_boundary_addresses,
        observation_boundaries,
        participant_action_addresses,
        participant_observation_boundary_addresses,
    )


def _participant_history_observation_boundary_addresses(history: object) -> set[str]:
    if not isinstance(history, list):
        return set()
    addresses: set[str] = set()
    for event in history:
        if not isinstance(event, Mapping):
            continue
        address = event.get("observation_boundary_address")
        if isinstance(address, str) and address:
            addresses.add(address)
    return addresses


def _participant_behavior_history_diagnostics(
    root_address: str,
    payload: object,
    *,
    address_scope: ParticipantHistoryAddressScope | None = None,
    action_contracts: dict[str, ParticipantActionContractRuntime] | None = None,
    observation_boundaries: dict[str, ParticipantObservationBoundaryRuntime] | None = None,
    participant_episode_history: object | None = None,
    expected_participant_address: str | None = None,
) -> list[Diagnostic]:
    history_key = "runtime.snapshot.participant-behavior-history"
    if address_scope is None:
        address_scope = ParticipantHistoryAddressScope(
            action_contract_addresses=None,
            observation_boundary_addresses=None,
        )
    diagnostics: list[Diagnostic] = []
    for address, message in iter_participant_behavior_history_violations(
        payload,
        action_contracts=action_contracts,
        observation_boundaries=observation_boundaries,
        participant_episode_history=participant_episode_history,
        expected_participant_address=expected_participant_address,
        address_scope=address_scope,
    ):
        if address.startswith(history_key):
            diagnostic_address = root_address + address.removeprefix(history_key)
        else:
            diagnostic_address = f"{root_address}.{address}"
        diagnostics.append(_diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, diagnostic_address, message))
    return diagnostics


def _participant_behavior_binding_diagnostics(
    participant_address: str,
    history: object,
    *,
    has_participant_action_binding: bool,
    has_participant_boundary_binding: bool,
) -> list[Diagnostic]:
    if not isinstance(history, list) or not history:
        return []
    if has_participant_action_binding and has_participant_boundary_binding:
        return []
    return [
        _diagnostic(
            _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
            f"runtime.snapshot.participant-behavior-history.{participant_address}",
            (
                "participant behavior history requires a participant.behavior snapshot entry "
                "with action_contract_addresses and observation_boundary_addresses"
            ),
        )
    ]


def _participant_behavior_snapshot_diagnostics(
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    (
        action_contract_addresses,
        action_contracts,
        observation_boundary_addresses,
        observation_boundaries,
        participant_action_addresses,
        participant_observation_boundary_addresses,
    ) = _participant_behavior_snapshot_references(snapshot)
    for participant_address, history in snapshot.participant_behavior_history.items():
        has_participant_action_binding = participant_address in participant_action_addresses
        has_participant_boundary_binding = participant_address in participant_observation_boundary_addresses
        diagnostics.extend(
            _participant_behavior_binding_diagnostics(
                participant_address,
                history,
                has_participant_action_binding=has_participant_action_binding,
                has_participant_boundary_binding=has_participant_boundary_binding,
            )
        )
        participant_boundary_addresses = participant_observation_boundary_addresses.get(participant_address)
        if participant_boundary_addresses is None:
            participant_boundary_addresses = _participant_history_observation_boundary_addresses(history)
        participant_known_boundary_addresses = (
            participant_boundary_addresses if has_participant_boundary_binding else observation_boundary_addresses
        )
        participant_boundaries = {
            address: observation_boundaries[address]
            for address in sorted(participant_boundary_addresses)
            if address in observation_boundaries
        }
        diagnostics.extend(
            _participant_behavior_history_diagnostics(
                f"runtime.snapshot.participant-behavior-history.{participant_address}",
                history,
                address_scope=ParticipantHistoryAddressScope(
                    action_contract_addresses=(
                        participant_action_addresses[participant_address]
                        if has_participant_action_binding
                        else action_contract_addresses
                    ),
                    observation_boundary_addresses=participant_known_boundary_addresses,
                ),
                action_contracts=action_contracts,
                observation_boundaries=participant_boundaries,
                participant_episode_history=snapshot.participant_episode_history.get(participant_address),
                expected_participant_address=participant_address,
            )
        )
    for address, message in iter_participant_behavior_joint_action_violations(snapshot.participant_behavior_history):
        diagnostics.append(
            _diagnostic(
                _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
                f"runtime.snapshot.participant-behavior-history.{address}",
                message,
            )
        )
    return diagnostics


def _shared_state_snapshot_diagnostics(snapshot: RuntimeSnapshot) -> list[Diagnostic]:
    return [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_shared_state_snapshot_violations(
            snapshot.shared_state_records,
            snapshot.shared_state_history,
            participant_behavior_history=snapshot.participant_behavior_history,
            metadata=snapshot.metadata,
        )
    ]


def _participant_concurrency_snapshot_diagnostics(snapshot: RuntimeSnapshot) -> list[Diagnostic]:
    return [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_concurrency_snapshot_violations(
            snapshot.joint_action_records,
            snapshot.time_management_contexts,
            participant_behavior_history=snapshot.participant_behavior_history,
            shared_state_records=snapshot.shared_state_records,
            shared_state_history=snapshot.shared_state_history,
        )
    ]


def _participant_information_state_snapshot_diagnostics(
    snapshot: RuntimeSnapshot,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> list[Diagnostic]:
    return [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_information_state_snapshot_violations(
            snapshot.information_state_history,
            information_state_context_resolver=information_state_context_resolver,
            context_scope=snapshot,
        )
    ]


def _participant_autonomous_state_snapshot_diagnostics(
    states: object,
) -> list[Diagnostic]:
    return [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_autonomous_state_snapshot_violations(states)
    ]


def _runtime_snapshot_semantic_diagnostics(
    payload: object,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> list[Diagnostic]:
    validated = RuntimeSnapshotEnvelopeModel.model_validate(payload)
    autonomous_states = {
        state_address: state.model_dump(mode="json")
        for state_address, state in validated.participant_autonomous_execution_states.items()
    }
    autonomous_diagnostics = _participant_autonomous_state_snapshot_diagnostics(autonomous_states)
    if autonomous_diagnostics:
        return autonomous_diagnostics
    snapshot = _snapshot_from_envelope(validated.model_dump(mode="json"))
    autonomous_diagnostics = [
        _diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message)
        for address, message in iter_participant_autonomous_runtime_snapshot_violations(snapshot)
    ]
    if autonomous_diagnostics:
        return autonomous_diagnostics
    return [
        *workflow_result_contract_diagnostics(snapshot),
        *evaluation_result_contract_diagnostics(snapshot),
        *_participant_episode_snapshot_diagnostics(snapshot),
        *_participant_episode_closure_snapshot_diagnostics(snapshot),
        *_participant_behavior_snapshot_diagnostics(snapshot),
        *_shared_state_snapshot_diagnostics(snapshot),
        *_participant_concurrency_snapshot_diagnostics(snapshot),
        *_participant_information_state_snapshot_diagnostics(
            snapshot,
            information_state_context_resolver,
        ),
        *autonomous_diagnostics,
    ]
