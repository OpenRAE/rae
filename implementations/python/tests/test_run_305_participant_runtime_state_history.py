"""RUN-305 participant runtime state and history integration tests."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import ParticipantBehaviorHistoryEventModel, schema_bundle
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from raes_runtime.participant_result_contracts import participant_runtime_state_contract_diagnostics
from starlette.testclient import TestClient

PARTICIPANT = "participant.alice"
EPISODE = "episode-1"
OTHER_EPISODE = "episode-2"
ACTION_INSTANCE = "action-1"
T0 = "2026-06-05T10:00:00Z"


def _security(target_name: str) -> ControlPlaneSecurityConfig:
    return ControlPlaneSecurityConfig(
        max_request_bytes=1_000_000,
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=target_name,
            ),
        },
    )


def _headers() -> dict[str, str]:
    return {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }


def _episode_result(*, episode_id: str = EPISODE) -> dict[str, object]:
    return {
        "state_schema_version": "participant-episode-state/v1",
        "participant_address": PARTICIPANT,
        "episode_id": episode_id,
        "sequence_number": 0,
        "status": "running",
        "terminal_reason": None,
        "initialized_at": T0,
        "updated_at": T0,
        "terminated_at": None,
        "last_control_action": "initialize",
        "previous_episode_id": None,
    }


def _episode_history_event(*, episode_id: str = EPISODE) -> dict[str, object]:
    return {
        "event_type": "episode_running",
        "timestamp": T0,
        "participant_address": PARTICIPANT,
        "episode_id": episode_id,
        "sequence_number": 0,
        "terminal_reason": None,
        "control_action": None,
        "details": {},
    }


def _behavior_event(
    *,
    participant_address: str = PARTICIPANT,
    episode_id: str = EPISODE,
    event_type: str = "action_attempted",
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "timestamp": T0,
        "participant_address": participant_address,
        "episode_id": episode_id,
        "action_instance_id": ACTION_INSTANCE,
        "details": {},
    }


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


def test_control_plane_api_snapshot_exposes_participant_behavior_history():
    target = create_stub_target()
    snapshot = RuntimeSnapshot(
        participant_episode_results={PARTICIPANT: _episode_result()},
        participant_episode_history={PARTICIPANT: [_episode_history_event()]},
        participant_behavior_history={PARTICIPANT: [_behavior_event()]},
    )
    control_plane = RuntimeControlPlane(target, initial_snapshot=snapshot)
    app = create_control_plane_app(control_plane, security=_security(target.name))

    with TestClient(app) as client:
        response = client.get("/snapshot", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    event = body["participant_behavior_history"][PARTICIPANT][0]
    assert event["event_type"] == "action_attempted"
    assert event["timestamp"] == T0
    assert event["participant_address"] == PARTICIPANT
    assert event["episode_id"] == EPISODE
    assert event["action_instance_id"] == ACTION_INSTANCE


def test_participant_runtime_state_diagnostics_reject_outer_key_mismatch():
    snapshot = RuntimeSnapshot(
        participant_behavior_history={
            PARTICIPANT: [_behavior_event(participant_address="participant.bob")],
        },
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert diagnostics
    assert all(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in diagnostics)
    assert any("does not match inner participant_address" in diagnostic.message for diagnostic in diagnostics)


def test_participant_runtime_state_diagnostics_reject_unknown_episode_when_episode_surface_exists():
    snapshot = RuntimeSnapshot(
        participant_episode_results={PARTICIPANT: _episode_result()},
        participant_episode_history={PARTICIPANT: [_episode_history_event()]},
        participant_behavior_history={
            PARTICIPANT: [_behavior_event(episode_id=OTHER_EPISODE)],
        },
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert diagnostics
    assert any("not present in participant episode state/history" in diagnostic.message for diagnostic in diagnostics)


def test_participant_runtime_state_diagnostics_reject_metadata_state_smuggling():
    snapshot = RuntimeSnapshot(
        metadata={
            "participant_behavior_history": {
                PARTICIPANT: [_behavior_event()],
            },
        },
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert diagnostics
    assert any("must not contain 'participant_behavior_history'" in diagnostic.message for diagnostic in diagnostics)


def test_backend_apply_path_rejects_invalid_participant_behavior_history():
    base_snapshot = RuntimeSnapshot()

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                participant_behavior_history={
                    PARTICIPANT: [
                        {
                            "event_type": "action_attempted",
                            "participant_address": PARTICIPANT,
                            "episode_id": EPISODE,
                            "action_instance_id": ACTION_INSTANCE,
                            "details": {},
                        }
                    ]
                },
            ),
            changed_addresses=[PARTICIPANT],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.participant.alice",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({PARTICIPANT})
        ),
    )

    assert result.success is False
    assert result.snapshot == base_snapshot
    assert any("missing required fields: timestamp" in diagnostic.message for diagnostic in result.diagnostics)


def test_backend_apply_path_rejects_participant_behavior_history_rewrite():
    original_event = _behavior_event()
    base_snapshot = RuntimeSnapshot(
        participant_behavior_history={
            PARTICIPANT: [original_event],
        },
    )
    rewritten_event = {**original_event, "timestamp": "2026-06-05T10:00:01Z"}

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                participant_behavior_history={
                    PARTICIPANT: [rewritten_event],
                },
            ),
            changed_addresses=[PARTICIPANT],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.participant.alice",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({PARTICIPANT})
        ),
    )

    assert result.success is False
    assert result.snapshot == base_snapshot
    assert any(
        "participant_behavior_history must be append-only" in diagnostic.message for diagnostic in result.diagnostics
    )


def test_backend_apply_path_rejects_in_place_participant_behavior_history_rewrite():
    original_event = _behavior_event()
    base_snapshot = RuntimeSnapshot(
        participant_behavior_history={
            PARTICIPANT: [dict(original_event)],
        },
    )

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        snapshot.participant_behavior_history[PARTICIPANT][0]["timestamp"] = "2026-06-05T10:00:01Z"
        return ApplyResult(
            success=True,
            snapshot=snapshot,
            changed_addresses=[PARTICIPANT],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.participant.alice",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({PARTICIPANT})
        ),
    )

    assert result.success is False
    assert base_snapshot.participant_behavior_history[PARTICIPANT] == [original_event]
    assert result.snapshot == base_snapshot
    assert any(
        "participant_behavior_history must be append-only" in diagnostic.message for diagnostic in result.diagnostics
    )


def test_backend_apply_path_rejects_participant_episode_history_removal():
    base_snapshot = RuntimeSnapshot(
        participant_episode_history={
            PARTICIPANT: [_episode_history_event()],
        },
    )

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                participant_episode_history={},
            ),
            changed_addresses=[PARTICIPANT],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.participant.alice",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({PARTICIPANT})
        ),
    )

    assert result.success is False
    assert result.snapshot == base_snapshot
    assert any(
        "participant_episode_history must be append-only" in diagnostic.message for diagnostic in result.diagnostics
    )


def test_participant_behavior_event_schema_and_model_reject_unknown_event_type():
    invalid_event = _behavior_event(event_type="fabricated")

    with pytest.raises(ValidationError):
        ParticipantBehaviorHistoryEventModel.model_validate(invalid_event)

    validator = Draft202012Validator(schema_bundle()["runtime-snapshot-v1"])
    assert list(validator.iter_errors(_snapshot_payload(invalid_event)))


def test_participant_behavior_event_schema_and_model_reject_boolean_realized_order():
    invalid_event = {
        **_behavior_event(),
        "realized_order": True,
    }

    with pytest.raises(ValidationError):
        ParticipantBehaviorHistoryEventModel.model_validate(invalid_event)

    validator = Draft202012Validator(schema_bundle()["runtime-snapshot-v1"])
    assert list(validator.iter_errors(_snapshot_payload(invalid_event)))
