"""RUN-306 participant decision/execution lifecycle tests."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import ParticipantBehaviorHistoryEventModel
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import (
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEvent,
    ParticipantLifecycleOperationState,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
)
from raes_runtime.participant_result_contracts import participant_runtime_state_contract_diagnostics
from raes_schemas import schema_bundle

PARTICIPANT = "participant.red"
EPISODE = "episode-1"
ACTION_INSTANCE = "scan-0001"
ACTION_ADDRESS = "participant.action-contract.scan"
OBSERVATION_ADDRESS = "participant.observation-boundary.red-view"
T0 = "2026-06-06T08:00:00Z"


def _action_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "action_attempted",
        "timestamp": T0,
        "participant_address": PARTICIPANT,
        "episode_id": EPISODE,
        "action_instance_id": ACTION_INSTANCE,
        "action_contract_address": ACTION_ADDRESS,
        "actor_provenance": "participant:red",
        "details": {},
    }
    payload.update(overrides)
    return payload


def _state_update_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "state_transition_recorded",
        "timestamp": T0,
        "participant_address": PARTICIPANT,
        "episode_id": EPISODE,
        "action_instance_id": ACTION_INSTANCE,
        "action_contract_address": ACTION_ADDRESS,
        "state_transition_kind": "participant_knowledge_expanded",
        "post_state_digest": "sha256:known",
        "details": {},
    }
    payload.update(overrides)
    return payload


def _observation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "observation_emitted",
        "timestamp": T0,
        "participant_address": PARTICIPANT,
        "episode_id": EPISODE,
        "action_instance_id": ACTION_INSTANCE,
        "action_contract_address": ACTION_ADDRESS,
        "observation_boundary_address": OBSERVATION_ADDRESS,
        "observation_status": "terminal",
        "post_state_digest": "sha256:known",
        "details": {},
    }
    payload.update(overrides)
    return payload


def _snapshot_payload(event: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "runtime-snapshot/v1",
        "entries": {},
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {PARTICIPANT: [event]},
        "metadata": {},
    }


def test_lifecycle_execution_attempt_round_trips_and_schema_accepts_envelope() -> None:
    payload = _action_payload(
        lifecycle_phase="execution_attempt",
        phase_realization="runtime_mediated",
        operation_ref="runtime.operation.scan-0001",
        operation_state="running",
    )

    model = ParticipantBehaviorHistoryEventModel.model_validate(payload)
    assert model.model_dump(mode="json")["lifecycle_phase"] == "execution_attempt"

    validator = Draft202012Validator(schema_bundle()["runtime-snapshot-v1"])
    assert list(validator.iter_errors(_snapshot_payload(payload))) == []

    event = ParticipantBehaviorHistoryEvent.from_payload(payload)
    assert event.lifecycle_phase == ParticipantRuntimeLifecyclePhase.EXECUTION_ATTEMPT
    assert event.phase_realization == ParticipantPhaseRealization.RUNTIME_MEDIATED
    assert event.operation_state == ParticipantLifecycleOperationState.RUNNING
    assert ParticipantBehaviorHistoryEvent.from_payload(event.to_payload()) == event


@pytest.mark.parametrize(
    "phase_realization",
    [
        "observed",
        "runtime_mediated",
        "externally_supplied",
        "opaque",
        "unknown",
        "not_applicable",
        "unsupported",
    ],
)
def test_lifecycle_phase_realization_values_are_not_collapsed(phase_realization: str) -> None:
    payload = _action_payload(
        lifecycle_phase="intent_or_proposal",
        phase_realization=phase_realization,
    )

    event = ParticipantBehaviorHistoryEvent.from_payload(payload)

    assert event.lifecycle_phase == ParticipantRuntimeLifecyclePhase.INTENT_OR_PROPOSAL
    assert event.phase_realization.value == phase_realization
    model = ParticipantBehaviorHistoryEventModel.model_validate(payload)
    assert model.model_dump(mode="json")["phase_realization"] == phase_realization


def test_selection_admission_records_use_separate_disposition_vocabulary() -> None:
    payload = _action_payload(
        lifecycle_phase="selection_or_admission",
        phase_realization="externally_supplied",
        admission_disposition="admitted",
    )

    event = ParticipantBehaviorHistoryEvent.from_payload(payload)

    assert event.admission_disposition == ParticipantAdmissionDisposition.ADMITTED
    assert event.to_payload()["admission_disposition"] == "admitted"


def test_admission_disposition_is_only_valid_for_selection_or_admission() -> None:
    payload = _action_payload(
        lifecycle_phase="execution_attempt",
        phase_realization="observed",
        admission_disposition="admitted",
    )

    with pytest.raises(
        ValueError,
        match="admission_disposition requires lifecycle_phase selection_or_admission",
    ):
        ParticipantBehaviorHistoryEvent.from_payload(payload)
    with pytest.raises(
        ValidationError,
        match="admission_disposition requires lifecycle_phase selection_or_admission",
    ):
        ParticipantBehaviorHistoryEventModel.model_validate(payload)

    diagnostics = participant_runtime_state_contract_diagnostics(
        RuntimeSnapshot(participant_behavior_history={PARTICIPANT: [payload]})
    )
    assert any(
        "admission_disposition requires lifecycle_phase selection_or_admission" in item.message for item in diagnostics
    )


def test_operation_state_is_only_valid_for_execution_attempt() -> None:
    payload = _action_payload(
        lifecycle_phase="selection_or_admission",
        phase_realization="observed",
        admission_disposition="admitted",
        operation_ref="runtime.operation.scan-0001",
        operation_state="running",
    )

    with pytest.raises(
        ValueError,
        match="operation_state requires lifecycle_phase execution_attempt",
    ):
        ParticipantBehaviorHistoryEvent.from_payload(payload)
    with pytest.raises(
        ValidationError,
        match="operation_state requires lifecycle_phase execution_attempt",
    ):
        ParticipantBehaviorHistoryEventModel.model_validate(payload)

    diagnostics = participant_runtime_state_contract_diagnostics(
        RuntimeSnapshot(participant_behavior_history={PARTICIPANT: [payload]})
    )
    assert any("operation_state requires lifecycle_phase execution_attempt" in item.message for item in diagnostics)


def test_lifecycle_phase_must_match_behavior_event_type() -> None:
    invalid_state_update = _state_update_payload(
        lifecycle_phase="observation_emission",
        phase_realization="observed",
    )
    with pytest.raises(
        ValueError,
        match="state_transition_recorded lifecycle_phase must be state_update_commit",
    ):
        ParticipantBehaviorHistoryEvent.from_payload(invalid_state_update)

    invalid_observation = _observation_payload(
        lifecycle_phase="state_update_commit",
        phase_realization="observed",
    )
    with pytest.raises(
        ValueError,
        match="observation_emitted lifecycle_phase must be observation_emission",
    ):
        ParticipantBehaviorHistoryEvent.from_payload(invalid_observation)

    valid_observation = ParticipantBehaviorHistoryEvent.from_payload(
        _observation_payload(
            lifecycle_phase="observation_emission",
            phase_realization="observed",
        )
    )
    assert valid_observation.observation_status == ParticipantObservationStatus.TERMINAL


def test_schema_rejects_unknown_lifecycle_vocabulary() -> None:
    payload = _action_payload(
        lifecycle_phase="opaque",
        phase_realization="observed",
    )

    with pytest.raises(ValidationError):
        ParticipantBehaviorHistoryEventModel.model_validate(payload)

    validator = Draft202012Validator(schema_bundle()["runtime-snapshot-v1"])
    assert list(validator.iter_errors(_snapshot_payload(payload)))
