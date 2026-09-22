"""ACT-614 temporal durability."""

from __future__ import annotations

import pytest
import yaml
from implementations.python.tests._act_614_temporal_fixtures import (
    _bound_deadline_payload,
    _bound_dwell_payload,
    _DwellEvidenceRuntime,
    _temporal_target,
    _TemporalEvidenceRuntime,
)
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _activity_policy_yaml,
    _scenario_yaml,
)
from implementations.python.tests.test_issue_899_participant_resource_budgets import _budget_policy_yaml
from raes.parser import parse_sdl
from raes_processor.compiler import compile_runtime_model
from raes_runtime.manager import RuntimeManager


def _validate_snapshot_envelope(payload: dict[str, object]) -> object:
    from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel

    return RuntimeSnapshotEnvelopeModel.model_validate(payload)


def test_history_view_returns_completed_temporal_assessments() -> None:
    from implementations.python.tests.test_runtime_control_plane_api import _test_security
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_api import create_control_plane_app
    from starlette.testclient import TestClient

    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert result.success
    participant, history = next(iter(result.snapshot.participant_behavior_history.items()))
    control = RuntimeControlPlane(target, initial_snapshot=result.snapshot)
    try:
        view = control.get_participant_history_view(participant, history[-1]["episode_id"])
        assert view is not None
        assert view.behavior_history[-1].temporal_assessments[0].status == "met"
        assert (
            view.model_dump(mode="json", exclude_none=True, exclude_defaults=True)["behavior_history"][-1][
                "temporal_assessments"
            ]
            == history[-1]["temporal_assessments"]
        )
        with TestClient(create_control_plane_app(control, security=_test_security(target.name))) as client:
            response = client.get(
                f"/participants/{participant}/episodes/{history[-1]['episode_id']}/history",
                headers={"x-raes-client-verified": "true", "x-raes-client-identity": "backend-service"},
            )
        assert response.status_code == 200
        assert response.json()["behavior_history"][-1]["temporal_assessments"][0]["status"] == "met"
    finally:
        control.close()


@pytest.mark.parametrize("kind", ["deadline", "dwell"])
def test_bound_temporal_evidence_survives_durable_snapshot_roundtrip(kind: str) -> None:
    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    payload, runtime = (
        (_bound_deadline_payload(), _TemporalEvidenceRuntime())
        if kind == "deadline"
        else (_bound_dwell_payload(), _DwellEvidenceRuntime())
    )
    scenario, target = _temporal_target(payload, runtime)
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    if kind == "dwell":
        result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    assert result.success
    restored = _snapshot_from_payload(_snapshot_payload(result.snapshot))
    assert restored.participant_behavior_history == result.snapshot.participant_behavior_history


@pytest.mark.parametrize("surface", ["store", "api"])
@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "missing",
        "scope",
        "bound",
        "clock",
        "native-proof",
        "extra-proof",
        "duplicate-proof",
        "attempt-context",
        "stripped-terminal",
        "truncated-history",
        "native-disposition",
    ],
)
def test_durable_restore_rejects_inconsistent_temporal_assessment(mutation: str, surface: str) -> None:
    from copy import deepcopy

    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert result.success
    payload = deepcopy(_snapshot_payload(result.snapshot))
    observation = next(iter(payload["participant_behavior_history"].values()))[-1]
    assessment = observation["temporal_assessments"][0]
    if mutation == "missing":
        observation.pop("temporal_assessments")
    elif mutation == "status":
        assessment["status"] = "missed"
    elif mutation == "scope":
        assessment["context"]["action_instance_id"] = "another"
    elif mutation == "bound":
        assessment["context"]["bound_end"]["tick"] = 999
    elif mutation == "native-proof":
        observation["action_result"]["temporal_evidence"] = []
    elif mutation in {"extra-proof", "duplicate-proof"}:
        proof = deepcopy(observation["action_result"]["temporal_evidence"][0])
        if mutation == "extra-proof":
            proof["context"]["participant_address"] = "participant.behavior.foreign"
        observation["action_result"]["temporal_evidence"].append(proof)
    elif mutation == "stripped-terminal":
        observation.pop("temporal_assessments")
        observation["temporal_contexts"] = []
    elif mutation == "truncated-history":
        next(iter(payload["participant_behavior_history"].values())).pop()
    elif mutation == "native-disposition":
        next(iter(payload["participant_behavior_history"].values()))[0]["admission_disposition"] = "rejected"
    elif mutation == "attempt-context":
        next(iter(payload["participant_behavior_history"].values()))[0]["temporal_contexts"][0]["shared_time"][
            "execution_generation"
        ] += 1
    else:
        assessment["context"]["clock_sequence"] = 999
    validator = _snapshot_from_payload if surface == "store" else _validate_snapshot_envelope
    with pytest.raises(ValueError, match="temporal"):
        validator(payload)


def test_pre_dispatch_rejection_survives_semantic_history_projection() -> None:
    from raes_processor.models.history_event import ParticipantBehaviorHistoryEvent

    payload = _bound_deadline_payload()
    payload["temporal_constraints"]["green-cadence"]["start"] = {"tick": 10}
    scenario, target = _temporal_target(payload)
    manager = RuntimeManager(target)
    assert manager.apply(manager.plan(scenario)).success
    result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    raw = next(iter(result.snapshot.participant_behavior_history.values()))[-1]
    projected = ParticipantBehaviorHistoryEvent.from_payload(raw).to_payload()
    assert projected["action_result"]["status"] == "rejected"
    assert projected["temporal_assessments"] == raw["temporal_assessments"]


def test_temporal_binding_changes_policy_identity_without_changing_legacy_identity() -> None:
    from raes_runtime.participant_scheduler_policy import _policy_digest

    payload = _bound_deadline_payload()
    before = compile_runtime_model(parse_sdl(yaml.safe_dump(payload)))
    payload["temporal_constraints"]["finish-by-five"]["end"]["tick"] = 6
    after = compile_runtime_model(parse_sdl(yaml.safe_dump(payload)))
    left = next(iter(before.behavior_specifications.values())).autonomous_execution
    right = next(iter(after.behavior_specifications.values())).autonomous_execution
    assert _policy_digest(left, before.time_model) != _policy_digest(right, after.time_model)


@pytest.mark.parametrize(
    ("source", "digest"),
    [
        (_scenario_yaml, "sha256:2fb5d1cbbde0d3c7554fac379e1f58fd39f6b74c98b0267f28fcd7b9a4cca9d8"),
        (_activity_policy_yaml, "sha256:a21ca455eaad03aa66c54f32a7feca856c680e24fd9d1a162fc2961cd9802dd6"),
        (_budget_policy_yaml, "sha256:134f735fe9608e97bc1f87b80298dc4a7193cbb7b88bea3069c3196529ab9c6b"),
    ],
)
def test_unbound_profiles_retain_pre_change_policy_identity(source, digest: str) -> None:
    from raes_runtime.participant_scheduler_policy import _policy_digest

    model = compile_runtime_model(parse_sdl(source()))
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    assert _policy_digest(policy, model.time_model) == digest


def test_semantic_history_projection_preserves_bound_context_evidence_and_assessment() -> None:
    from copy import deepcopy

    from raes_processor.models.history_event import ParticipantBehaviorHistoryEvent

    scenario, target = _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    raw = deepcopy(next(iter(result.snapshot.participant_behavior_history.values()))[-1])
    outcome = raw["action_result"]
    outcome["preconditions"] = [
        {
            "precondition_id": "portal-present",
            "precondition_class": "target",
            "status": "satisfied",
            **{
                key: outcome[key]
                for key in ("participant_address", "episode_id", "action_contract_address", "observation_point")
            },
            "support_refs": ["nodes.customer-portal"],
        }
    ]
    outcome["effects"] = [
        {
            "effect_id": "response",
            "effect_class": "observation_effect",
            "description": "Reference response recorded.",
            "evidence_refs": ["evidence:reference-response"],
        }
    ]
    outcome["resource_measurements"] = [
        {
            "budget_state_ref": "budget.tokens",
            "operation_id": outcome["action_instance_id"],
            "execution_generation": 0,
            "resource_kind": "inference_tokens",
            "unit": "tokens",
            "meter_profile_ref": "meter.tokens/v1",
            "measured": 7,
            "evidence_refs": ["evidence:meter"],
        }
    ]
    projected = ParticipantBehaviorHistoryEvent.from_payload(raw).to_payload()
    assert projected["temporal_contexts"][0]["shared_time"] == raw["temporal_contexts"][0]["shared_time"]
    assert projected["temporal_assessments"] == raw["temporal_assessments"]
    assert projected["action_result"]["temporal_evidence"] == outcome["temporal_evidence"]
    assert projected["action_result"]["resource_measurements"] == outcome["resource_measurements"]
