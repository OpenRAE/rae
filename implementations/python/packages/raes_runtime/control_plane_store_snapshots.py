"""Portable runtime-snapshot serialization for control-plane stores."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from raes_contracts.account_credentials import (
    account_placement_has_credential_bindings,
    value_free_account_placement_payload,
)
from raes_contracts.artifact_requirements import ArtifactSatisfactionDisclosureModel
from raes_contracts.contracts import RealizationEnvelopeIdentityModel
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.domain_profiles import DomainProfileBindingModel
from raes_contracts.participant_autonomous_state import require_participant_autonomous_runtime_snapshot
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    ExplicitnessClass,
    ExplicitnessProvenance,
    RealizationProvenanceEntry,
    RuntimeSnapshot,
    RuntimeSnapshotEnvelope,
    SnapshotEntry,
)

from .control_plane_store_observations import realization_observation_from_payload


def _require_complete_runtime_snapshot_fields(values: dict[str, Any]) -> None:
    """Keep the hand-written durable codec exhaustive as the snapshot evolves."""

    expected = {field.name for field in fields(RuntimeSnapshot)}
    actual = set(values)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        unexpected = ", ".join(sorted(actual - expected)) or "none"
        raise RuntimeError(f"runtime snapshot durable codec field mismatch: missing={missing}; unexpected={unexpected}")


def _realization_provenance_payload(snapshot: RuntimeSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "address": entry.address,
            "field_path": entry.field_path,
            "domain": entry.domain,
            "requirement_kind": entry.requirement_kind,
            "explicitness": entry.explicitness.value,
            "provenance": entry.provenance.value,
            "governing_scope": entry.governing_scope,
            "artifact_satisfaction": (
                entry.artifact_satisfaction.model_dump(mode="json") if entry.artifact_satisfaction is not None else None
            ),
        }
        for entry in snapshot.realization_provenance
    ]


def _realization_observations_payload(snapshot: RuntimeSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "address": entry.address,
            "field_path": entry.field_path,
            "domain": entry.domain,
            "requirement_kind": entry.requirement_kind,
            "verification_scope": entry.verification_scope.value,
            "observation_strength": entry.observation_strength.value,
            **(
                {
                    "observed_value": entry.observed_value,
                    "operating_system": (
                        {
                            "family": entry.operating_system.family,
                            "distribution": entry.operating_system.distribution,
                            "version": entry.operating_system.version,
                        }
                        if entry.operating_system is not None
                        else None
                    ),
                    "operation_id": entry.operation_id,
                    "envelope_digest": entry.envelope_digest,
                    "configuration_digest": entry.configuration_digest,
                    "observer_version": entry.observer_version,
                    "sequence": entry.sequence,
                    "binding_verified": entry.binding_verified,
                }
                if entry.requirement_kind in {"compute-substrate", "operating-system"}
                else {}
            ),
        }
        for entry in snapshot.realization_observations
    ]


def _snapshot_payload(snapshot: RuntimeSnapshot) -> dict[str, Any]:
    require_participant_autonomous_runtime_snapshot(snapshot)
    snapshot_fields: dict[str, Any] = {
        "entries": {
            address: {
                "address": entry.address,
                "domain": RuntimeDomain(entry.domain).value,
                "resource_type": entry.resource_type,
                "payload": dict(entry.payload),
                "ordering_dependencies": list(entry.ordering_dependencies),
                "refresh_dependencies": list(entry.refresh_dependencies),
                "status": entry.status,
                **(
                    {"profile_bindings": [binding.model_dump(mode="json") for binding in entry.profile_bindings]}
                    if entry.profile_bindings
                    else {}
                ),
            }
            for address, entry in snapshot.entries.items()
        },
        "orchestration_results": dict(snapshot.orchestration_results),
        "orchestration_history": {address: list(events) for address, events in snapshot.orchestration_history.items()},
        "evaluation_results": dict(snapshot.evaluation_results),
        "evaluation_history": {address: list(events) for address, events in snapshot.evaluation_history.items()},
        "proposition_truth_results": dict(snapshot.proposition_truth_results),
        "participant_episode_results": dict(snapshot.participant_episode_results),
        "participant_episode_history": {
            participant_address: list(events)
            for participant_address, events in snapshot.participant_episode_history.items()
        },
        "participant_episode_closure_records": {
            participant_address: list(records)
            for participant_address, records in snapshot.participant_episode_closure_records.items()
        },
        "participant_behavior_history": {
            participant_address: list(events)
            for participant_address, events in snapshot.participant_behavior_history.items()
        },
        "participant_control_history": {
            participant_address: list(events)
            for participant_address, events in snapshot.participant_control_history.items()
        },
        "participant_crossing_history": {
            participant_address: list(events)
            for participant_address, events in snapshot.participant_crossing_history.items()
        },
        "information_state_history": {
            participant_address: list(records)
            for participant_address, records in snapshot.information_state_history.items()
        },
        "participant_autonomous_execution_states": dict(snapshot.participant_autonomous_execution_states),
        "participant_execution_services": dict(snapshot.participant_execution_services),
        "participant_resource_budget_states": dict(snapshot.participant_resource_budget_states),
        "participant_resource_pool_states": dict(snapshot.participant_resource_pool_states),
        "participant_resource_budget_events": dict(snapshot.participant_resource_budget_events),
        "shared_state_records": dict(snapshot.shared_state_records),
        "shared_state_history": {
            state_address: list(records) for state_address, records in snapshot.shared_state_history.items()
        },
        "joint_action_records": dict(snapshot.joint_action_records),
        "time_management_contexts": dict(snapshot.time_management_contexts),
        "time_model_state": (
            snapshot.time_model_state.model_dump(mode="json") if snapshot.time_model_state is not None else None
        ),
        "realization_provenance": _realization_provenance_payload(snapshot),
        "realization_observations": _realization_observations_payload(snapshot),
        "realization_envelope": (
            snapshot.realization_envelope.model_dump(mode="json") if snapshot.realization_envelope is not None else None
        ),
        "metadata": dict(snapshot.metadata),
    }
    _require_complete_runtime_snapshot_fields(snapshot_fields)
    payload = {
        "schema_version": RuntimeSnapshotEnvelope().schema_version,
        **snapshot_fields,
    }
    for entry in payload["entries"].values():
        if entry["resource_type"] != "account-placement":
            continue
        entry_payload = entry["payload"]
        if account_placement_has_credential_bindings(entry_payload):
            entry["payload"] = value_free_account_placement_payload(entry_payload)
    return payload


def _snapshot_entries_from_payload(payload: dict[str, Any]) -> dict[str, SnapshotEntry]:
    entries_payload = payload.get("entries", {})
    return {
        address: SnapshotEntry(
            address=str(entry.get("address", address)),
            domain=RuntimeDomain(str(entry.get("domain", "provisioning"))),
            resource_type=str(entry.get("resource_type", "")),
            payload=dict(entry.get("payload", {})),
            ordering_dependencies=tuple(entry.get("ordering_dependencies", ())),
            refresh_dependencies=tuple(entry.get("refresh_dependencies", ())),
            status=str(entry.get("status", "ready")),
            profile_bindings=tuple(
                DomainProfileBindingModel.model_validate(binding) for binding in entry.get("profile_bindings", ())
            ),
        )
        for address, entry in entries_payload.items()
        if isinstance(entry, dict)
    }


def _realization_provenance_from_payload(payload: dict[str, Any]) -> tuple[RealizationProvenanceEntry, ...]:
    return tuple(
        RealizationProvenanceEntry(
            address=str(item.get("address", "")),
            field_path=str(item.get("field_path", "")),
            domain=str(item.get("domain", "")),
            requirement_kind=str(item.get("requirement_kind", "")),
            explicitness=ExplicitnessClass(str(item.get("explicitness", ExplicitnessClass.EXACT.value))),
            provenance=ExplicitnessProvenance(
                str(item.get("provenance", ExplicitnessProvenance.AUTHOR_DECLARED.value))
            ),
            governing_scope=(str(item["governing_scope"]) if item.get("governing_scope") is not None else None),
            artifact_satisfaction=(
                ArtifactSatisfactionDisclosureModel.model_validate(item["artifact_satisfaction"])
                if item.get("artifact_satisfaction") is not None
                else None
            ),
        )
        for item in payload.get("realization_provenance", [])
        if isinstance(item, dict)
    )


def _snapshot_from_payload(payload: dict[str, Any]) -> RuntimeSnapshot:
    snapshot_fields: dict[str, Any] = {
        "entries": _snapshot_entries_from_payload(payload),
        "orchestration_results": dict(payload.get("orchestration_results", {})),
        "orchestration_history": {
            address: list(events) for address, events in payload.get("orchestration_history", {}).items()
        },
        "evaluation_results": dict(payload.get("evaluation_results", {})),
        "evaluation_history": {
            address: list(events) for address, events in payload.get("evaluation_history", {}).items()
        },
        "proposition_truth_results": dict(payload.get("proposition_truth_results", {})),
        "participant_episode_results": dict(payload.get("participant_episode_results", {})),
        "participant_episode_history": {
            participant_address: list(events)
            for participant_address, events in payload.get("participant_episode_history", {}).items()
        },
        "participant_episode_closure_records": {
            participant_address: list(records)
            for participant_address, records in payload.get("participant_episode_closure_records", {}).items()
        },
        "participant_behavior_history": {
            participant_address: list(events)
            for participant_address, events in payload.get("participant_behavior_history", {}).items()
        },
        "participant_control_history": {
            participant_address: list(events)
            for participant_address, events in payload.get("participant_control_history", {}).items()
        },
        "participant_crossing_history": {
            participant_address: list(events)
            for participant_address, events in payload.get("participant_crossing_history", {}).items()
        },
        "information_state_history": {
            participant_address: list(records)
            for participant_address, records in payload.get("information_state_history", {}).items()
        },
        "participant_autonomous_execution_states": dict(payload.get("participant_autonomous_execution_states", {})),
        "participant_execution_services": dict(payload.get("participant_execution_services", {})),
        "participant_resource_budget_states": dict(payload.get("participant_resource_budget_states", {})),
        "participant_resource_pool_states": dict(payload.get("participant_resource_pool_states", {})),
        "participant_resource_budget_events": dict(payload.get("participant_resource_budget_events", {})),
        "shared_state_records": dict(payload.get("shared_state_records", {})),
        "shared_state_history": {
            state_address: list(records) for state_address, records in payload.get("shared_state_history", {}).items()
        },
        "joint_action_records": dict(payload.get("joint_action_records", {})),
        "time_management_contexts": dict(payload.get("time_management_contexts", {})),
        "time_model_state": (
            TimeRuntimeStateModel.model_validate(payload["time_model_state"])
            if payload.get("time_model_state") is not None
            else None
        ),
        "realization_provenance": _realization_provenance_from_payload(payload),
        "realization_observations": tuple(
            realization_observation_from_payload(item)
            for item in payload.get("realization_observations", [])
            if isinstance(item, dict)
        ),
        "realization_envelope": (
            RealizationEnvelopeIdentityModel.model_validate(payload["realization_envelope"])
            if payload.get("realization_envelope") is not None
            else None
        ),
        "metadata": dict(payload.get("metadata", {})),
    }
    _require_complete_runtime_snapshot_fields(snapshot_fields)
    snapshot = RuntimeSnapshot(**snapshot_fields)
    require_participant_autonomous_runtime_snapshot(snapshot)
    return snapshot


__all__ = ("_snapshot_from_payload", "_snapshot_payload")
