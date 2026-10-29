"""Public portable ``runtime-snapshot-v1`` projection of a runtime snapshot.

The control-plane API publishes this projection. Conformance validates the same
projection, so the two surfaces cannot drift (issue #1667).
"""

from __future__ import annotations

from typing import Any

from raes_contracts.account_credentials import (
    account_placement_has_credential_bindings,
    value_free_account_placement_payload,
)
from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel
from raes_contracts.runtime_state import RuntimeSnapshotEnvelope

from raes_runtime.control_plane_store_payloads import _realization_observations_payload


def runtime_snapshot_contract_payload(envelope: RuntimeSnapshotEnvelope) -> dict[str, Any]:
    """Project the value-free published payload before contract validation.

    Conformance validates this payload to report malformed realization carriers
    through its diagnostic envelope instead of raising during serialization.
    """

    snapshot = envelope.snapshot
    payload = {
        "materialization_attestations": [
            record.model_dump(mode="json") for record in snapshot.materialization_attestations
        ],
        "schema_version": envelope.schema_version,
        "entries": {
            address: {
                "address": entry.address,
                "domain": entry.domain.value,
                "resource_type": entry.resource_type,
                "payload": dict(entry.payload),
                "ordering_dependencies": list(entry.ordering_dependencies),
                "refresh_dependencies": list(entry.refresh_dependencies),
                "status": entry.status,
            }
            for address, entry in snapshot.entries.items()
        },
        "orchestration_results": dict(snapshot.orchestration_results),
        "orchestration_history": dict(snapshot.orchestration_history),
        "evaluation_results": dict(snapshot.evaluation_results),
        "evaluation_history": dict(snapshot.evaluation_history),
        "proposition_truth_results": dict(snapshot.proposition_truth_results),
        "participant_episode_results": dict(snapshot.participant_episode_results),
        "participant_episode_history": dict(snapshot.participant_episode_history),
        "participant_behavior_history": dict(snapshot.participant_behavior_history),
        "participant_control_history": dict(snapshot.participant_control_history),
        "participant_crossing_history": dict(snapshot.participant_crossing_history),
        "participant_control_evaluation_history": dict(snapshot.participant_control_evaluation_history),
        "information_state_history": dict(snapshot.information_state_history),
        "participant_autonomous_execution_states": dict(snapshot.participant_autonomous_execution_states),
        "participant_execution_services": dict(snapshot.participant_execution_services),
        "participant_resource_budget_states": dict(snapshot.participant_resource_budget_states),
        "participant_resource_pool_states": dict(snapshot.participant_resource_pool_states),
        "participant_resource_budget_events": dict(snapshot.participant_resource_budget_events),
        "shared_state_records": dict(snapshot.shared_state_records),
        "shared_state_history": dict(snapshot.shared_state_history),
        "joint_action_records": dict(snapshot.joint_action_records),
        "time_management_contexts": dict(snapshot.time_management_contexts),
        "time_model_state": (
            snapshot.time_model_state.model_dump(mode="json") if snapshot.time_model_state is not None else None
        ),
        "realization_provenance": [
            {
                "address": entry.address,
                "field_path": entry.field_path,
                "domain": entry.domain,
                "requirement_kind": entry.requirement_kind,
                "explicitness": entry.explicitness.value,
                "provenance": entry.provenance.value,
                "governing_scope": entry.governing_scope,
                **(
                    {"artifact_satisfaction": entry.artifact_satisfaction.model_dump(mode="json")}
                    if entry.artifact_satisfaction is not None
                    else {}
                ),
            }
            for entry in snapshot.realization_provenance
        ],
        "realization_observations": _realization_observations_payload(snapshot),
        "realization_envelope": (
            snapshot.realization_envelope.model_dump(mode="json") if snapshot.realization_envelope is not None else None
        ),
        "metadata": dict(snapshot.metadata),
    }
    for entry in payload["entries"].values():
        if entry["resource_type"] != "account-placement":
            continue
        entry_payload = entry["payload"]
        if account_placement_has_credential_bindings(entry_payload):
            entry["payload"] = value_free_account_placement_payload(entry_payload)
    return payload


def runtime_snapshot_contract_model(envelope: RuntimeSnapshotEnvelope) -> RuntimeSnapshotEnvelopeModel:
    """Project a runtime snapshot to its value-free ``runtime-snapshot-v1`` contract model."""

    return RuntimeSnapshotEnvelopeModel.model_validate(runtime_snapshot_contract_payload(envelope))


__all__ = ["runtime_snapshot_contract_model", "runtime_snapshot_contract_payload"]
