"""RUN-308 concurrent participant execution integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import (
    ParticipantJointActionRecordModel,
    ParticipantTimeManagementContextModel,
    RuntimeSnapshotEnvelopeModel,
    schema_bundle,
)
from raes_contracts.participant_concurrency import (
    iter_participant_concurrency_snapshot_violations,
    iter_participant_concurrency_transition_violations,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from raes_runtime.participant_result_contracts import participant_runtime_state_contract_diagnostics

REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_ADDRESS = "hosts.web01.service.http"
PARTICIPANT_RED = "participants.red.llm"
PARTICIPANT_BLUE = "participants.blue.llm"
EPISODE = "episode-main"
T0 = "2026-06-20T08:00:00Z"


def _shared_state_record() -> dict[str, object]:
    fixture_path = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "participant-shared-state-record-v1"
        / "valid"
        / "serialized-service-state-commit.json"
    )
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _behavior_event(participant_address: str, action_instance_id: str, realized_order: int) -> dict[str, object]:
    return {
        "event_type": "action_attempted",
        "timestamp": T0,
        "participant_address": participant_address,
        "episode_id": EPISODE,
        "action_instance_id": action_instance_id,
        "action_contract_address": "participant.action-contract.scan",
        "actor_provenance": f"participant:{participant_address.rsplit('.', 1)[-1]}",
        "joint_action_set_id": "joint-red-blue-0001",
        "realized_order": realized_order,
        "interaction_class": "shared_state_change",
        "shared_state_refs": [STATE_ADDRESS],
        "details": {},
    }


def _base_envelope(*, event_id: str, schema_name: str, event_type: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "schema_name": schema_name,
        "schema_version": f"{schema_name}/v1",
        "event_type": event_type,
        "extension_policy": "forbid_unknown_fields",
        "participant_address": None,
        "episode_id": None,
        "sequence_number": None,
        "occurred_at": T0,
        "recorded_at": T0,
        "ingested_at": T0,
        "clock_authority": "clock.logical.runtime",
        "ordering_basis": "serialized_backend_order",
        "logical_order_ref": "order.joint-red-blue-0001",
        "actor_ref": "runtime.coordinator",
        "producer_ref": "backend.stub",
        "authorization_scope": "operators",
    }


def _time_context(**overrides: object) -> dict[str, object]:
    payload = {
        **_base_envelope(
            event_id="tm-red-blue-0001",
            schema_name="participant-time-management-context",
            event_type="time_management_context_recorded",
        ),
        "context_id": "tm-red-blue-0001",
        "mode": "backend_serialized",
        "claim_strength": "bounded",
        "basis": "serialized_backend_order",
        "clock_ref": "clock.logical.runtime",
        "backend_serialized": True,
    }
    payload.update(overrides)
    return payload


def _joint_action(**overrides: object) -> dict[str, object]:
    payload = {
        **_base_envelope(
            event_id="joint-red-blue-0001",
            schema_name="participant-joint-action-record",
            event_type="joint_action_recorded",
        ),
        "joint_action_set_id": "joint-red-blue-0001",
        "member_event_refs": ["scan-red-0001", "scan-blue-0001"],
        "access_sets": [
            {
                "member_event_ref": "scan-red-0001",
                "shared_state_write_refs": [STATE_ADDRESS],
            },
            {
                "member_event_ref": "scan-blue-0001",
                "shared_state_read_refs": [STATE_ADDRESS],
            },
        ],
        "conflict_class": "read_write",
        "conflict_policy": "serialize",
        "isolation_guarantee": "serializable",
        "atomicity_scope": "single_object",
        "realized_order": ["scan-red-0001", "scan-blue-0001"],
        "time_management_context_ref": "tm-red-blue-0001",
    }
    payload.update(overrides)
    return payload


def _snapshot_payload(**overrides: object) -> dict[str, object]:
    shared_state = _shared_state_record()
    payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {},
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {
            PARTICIPANT_RED: [_behavior_event(PARTICIPANT_RED, "scan-red-0001", 0)],
            PARTICIPANT_BLUE: [_behavior_event(PARTICIPANT_BLUE, "scan-blue-0001", 1)],
        },
        "shared_state_records": {STATE_ADDRESS: shared_state},
        "shared_state_history": {STATE_ADDRESS: [shared_state]},
        "joint_action_records": {"joint-red-blue-0001": _joint_action()},
        "time_management_contexts": {"tm-red-blue-0001": _time_context()},
        "metadata": {},
    }
    payload.update(overrides)
    return payload


def _concurrency_violation_messages(payload: dict[str, object]) -> list[str]:
    return [
        message
        for _address, message in iter_participant_concurrency_snapshot_violations(
            payload.get("joint_action_records"),
            payload.get("time_management_contexts"),
            participant_behavior_history=payload.get("participant_behavior_history"),
            shared_state_records=payload.get("shared_state_records"),
            shared_state_history=payload.get("shared_state_history"),
        )
    ]


def test_runtime_snapshot_publishes_joint_action_and_time_context_records() -> None:
    payload = _snapshot_payload()

    model = RuntimeSnapshotEnvelopeModel.model_validate(payload)
    assert model.joint_action_records["joint-red-blue-0001"].conflict_policy == "serialize"
    assert model.time_management_contexts["tm-red-blue-0001"].mode == "backend_serialized"

    validator = Draft202012Validator(schema_bundle()["runtime-snapshot-v1"])
    assert list(validator.iter_errors(payload)) == []


def test_joint_action_record_contract_rejects_unordered_conflicting_writes() -> None:
    payload = _joint_action(
        access_sets=[
            {"member_event_ref": "scan-red-0001", "shared_state_write_refs": [STATE_ADDRESS]},
            {"member_event_ref": "scan-blue-0001", "shared_state_write_refs": [STATE_ADDRESS]},
        ],
        conflict_class="none",
        conflict_policy="none",
        isolation_guarantee="none",
        realized_order=[],
        exact_concurrency_claim=True,
    )

    with pytest.raises(ValidationError, match="conflict_class"):
        ParticipantJointActionRecordModel.model_validate(payload)


def test_joint_action_record_contract_rejects_exact_claim_without_time_context() -> None:
    payload = _joint_action(
        exact_concurrency_claim=True,
        time_management_context_ref=None,
    )

    with pytest.raises(ValidationError, match="time_management_context_ref"):
        ParticipantJointActionRecordModel.model_validate(payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"member_event_refs": ["scan-red-0001", "scan-red-0001"]}, "member_event_refs must be unique"),
        (
            {"access_sets": [{"member_event_ref": "scan-red-0001"}]},
            "access_sets must cover member_event_refs",
        ),
        ({"realized_order": ["scan-red-0001", "scan-missing-0001"]}, "realized_order"),
        (
            {"unsupported_disclosure": True, "exact_concurrency_claim": True},
            "unsupported concurrency disclosure",
        ),
        (
            {"conflict_policy": "unsupported", "unsupported_disclosure": False},
            "unsupported conflict_policy",
        ),
        (
            {
                "conflict_policy": "retry",
                "isolation_guarantee": "serializable",
                "realized_order": [],
                "retry_limit": 1,
                "rollback_event_refs": ["scan-red-0001"],
            },
            "serializable joint action isolation",
        ),
        (
            {"conflict_policy": "serialize", "isolation_guarantee": "none", "realized_order": []},
            "serialize conflict_policy",
        ),
        (
            {
                "conflict_policy": "retry",
                "isolation_guarantee": "none",
                "realized_order": [],
                "retry_limit": None,
                "rollback_event_refs": [],
            },
            "retry conflict_policy",
        ),
        (
            {"conflict_policy": "none", "isolation_guarantee": "none", "realized_order": []},
            "none conflict_policy",
        ),
        (
            {
                "conflict_policy": "reject",
                "isolation_guarantee": "none",
                "atomicity_scope": "multi_object",
                "realized_order": [],
            },
            "multi_object conflicting joint actions",
        ),
        (
            {
                "conflict_class": "none",
                "conflict_policy": "reject",
                "isolation_guarantee": "none",
                "unsupported_disclosure": True,
            },
            "conflict_class cannot be none",
        ),
    ],
)
def test_joint_action_record_contract_rejects_concurrency_guardrails(
    overrides: dict[str, object],
    message: str,
) -> None:
    payload = _joint_action(**overrides)

    with pytest.raises(ValidationError, match=message):
        ParticipantJointActionRecordModel.model_validate(payload)


def test_joint_action_record_contract_accepts_unsupported_policy_disclosure() -> None:
    payload = _joint_action(
        conflict_policy="unsupported",
        unsupported_disclosure=True,
        exact_concurrency_claim=False,
    )

    model = ParticipantJointActionRecordModel.model_validate(payload)

    assert model.conflict_policy == "unsupported"


def test_time_management_context_contract_rejects_wall_clock_exact_claim() -> None:
    payload = _time_context(
        mode="display",
        claim_strength="exact",
        basis="wall_clock_only",
        clock_ref="clock.wall",
        backend_serialized=False,
    )

    with pytest.raises(ValidationError, match="wall_clock_only"):
        ParticipantTimeManagementContextModel.model_validate(payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"mode": "display", "claim_strength": "bounded", "basis": "logical_clock", "clock_ref": None},
            "clock_ref",
        ),
        ({"backend_serialized": False}, "backend_serialized mode"),
        (
            {
                "mode": "lookahead",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "backend_serialized": False,
            },
            "lookahead mode",
        ),
        (
            {
                "mode": "pacing",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "backend_serialized": False,
            },
            "pacing mode",
        ),
        (
            {
                "mode": "rollback",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "rollback_event_refs": [],
                "backend_serialized": False,
            },
            "rollback mode",
        ),
        (
            {
                "mode": "devs",
                "claim_strength": "display",
                "basis": "wall_clock_only",
                "clock_ref": None,
                "backend_serialized": False,
            },
            "devs and fmi modes",
        ),
        (
            {
                "mode": "unsupported",
                "claim_strength": "display",
                "basis": "wall_clock_only",
                "clock_ref": None,
                "backend_serialized": False,
            },
            "unsupported time-management mode",
        ),
        (
            {
                "mode": "display",
                "claim_strength": "exact",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "unsupported_disclosure": True,
                "backend_serialized": False,
            },
            "unsupported time-management disclosure",
        ),
    ],
)
def test_time_management_context_contract_rejects_mode_guardrails(
    overrides: dict[str, object],
    message: str,
) -> None:
    payload = _time_context(**overrides)

    with pytest.raises(ValidationError, match=message):
        ParticipantTimeManagementContextModel.model_validate(payload)


def test_participant_runtime_state_diagnostics_reject_unresolved_concurrency_refs() -> None:
    payload = _snapshot_payload(
        joint_action_records={
            "joint-red-blue-0001": _joint_action(
                member_event_refs=["scan-red-0001", "scan-missing-0001"],
                access_sets=[
                    {"member_event_ref": "scan-red-0001", "shared_state_write_refs": [STATE_ADDRESS]},
                    {"member_event_ref": "scan-missing-0001", "shared_state_read_refs": [STATE_ADDRESS]},
                ],
                realized_order=["scan-red-0001", "scan-missing-0001"],
            )
        }
    )
    snapshot = RuntimeSnapshot(
        participant_behavior_history=dict(payload["participant_behavior_history"]),
        shared_state_records=dict(payload["shared_state_records"]),
        shared_state_history=dict(payload["shared_state_history"]),
        joint_action_records=dict(payload["joint_action_records"]),
        time_management_contexts=dict(payload["time_management_contexts"]),
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert any("scan-missing-0001" in diagnostic.message for diagnostic in diagnostics)


def test_participant_runtime_state_diagnostics_reject_shared_state_refs_when_index_empty() -> None:
    payload = _snapshot_payload(
        shared_state_records={},
        shared_state_history={},
    )
    snapshot = RuntimeSnapshot(
        participant_behavior_history=dict(payload["participant_behavior_history"]),
        shared_state_records={},
        shared_state_history={},
        joint_action_records=dict(payload["joint_action_records"]),
        time_management_contexts=dict(payload["time_management_contexts"]),
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert any(f"{STATE_ADDRESS!r} does not resolve" in diagnostic.message for diagnostic in diagnostics)


def test_participant_runtime_state_diagnostics_reject_exact_claim_with_bounded_time_context() -> None:
    payload = _snapshot_payload(
        joint_action_records={
            "joint-red-blue-0001": _joint_action(
                exact_concurrency_claim=True,
            )
        }
    )
    snapshot = RuntimeSnapshot(
        participant_behavior_history=dict(payload["participant_behavior_history"]),
        shared_state_records=dict(payload["shared_state_records"]),
        shared_state_history=dict(payload["shared_state_history"]),
        joint_action_records=dict(payload["joint_action_records"]),
        time_management_contexts=dict(payload["time_management_contexts"]),
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert any("exact time-management context" in diagnostic.message for diagnostic in diagnostics)


def test_participant_runtime_state_diagnostics_reject_rollback_refs_when_history_empty() -> None:
    payload = _snapshot_payload(
        participant_behavior_history={},
        time_management_contexts={
            "tm-red-blue-0001": _time_context(
                mode="rollback",
                claim_strength="bounded",
                rollback_event_refs=["scan-red-0001"],
                backend_serialized=False,
            )
        },
    )
    snapshot = RuntimeSnapshot(
        participant_behavior_history={},
        shared_state_records=dict(payload["shared_state_records"]),
        shared_state_history=dict(payload["shared_state_history"]),
        joint_action_records={},
        time_management_contexts=dict(payload["time_management_contexts"]),
    )

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert any(
        "rollback_event_ref 'scan-red-0001' does not resolve" in diagnostic.message for diagnostic in diagnostics
    )


def test_participant_concurrency_snapshot_validator_rejects_malformed_maps() -> None:
    violations = list(
        iter_participant_concurrency_snapshot_violations(
            joint_action_records=[],
            time_management_contexts=[],
            participant_behavior_history=None,
            shared_state_records=None,
            shared_state_history=None,
        )
    )
    messages = [message for _address, message in violations]

    assert "joint_action_records must be a mapping" in messages
    assert "time_management_contexts must be a mapping" in messages


def test_participant_concurrency_snapshot_validator_rejects_malformed_records() -> None:
    payload = _snapshot_payload(
        joint_action_records={"": {}, "joint-red-blue-0001": "not-a-record"},
        time_management_contexts={"": {}, "tm-red-blue-0001": "not-a-context"},
    )

    messages = _concurrency_violation_messages(payload)

    assert "joint_action_records keys must be non-empty strings" in messages
    assert "joint action record must be a mapping" in messages
    assert "time_management_contexts keys must be non-empty strings" in messages
    assert "time management context must be a mapping" in messages


def test_participant_concurrency_snapshot_validator_rejects_malformed_joint_action_fields() -> None:
    payload = _snapshot_payload(
        joint_action_records={
            "joint-red-blue-0001": _joint_action(
                joint_action_set_id="joint-other-0001",
                member_event_refs=["scan-red-0001", ""],
                access_sets=[
                    {},
                    {
                        "member_event_ref": "scan-red-0001",
                        "shared_state_read_refs": "not-a-list",
                        "shared_state_write_refs": ["", "state.missing"],
                    },
                ],
                realized_order="not-a-list",
                conflict_class="none",
                conflict_policy="none",
                isolation_guarantee="none",
                time_management_context_ref="tm-missing-0001",
            ),
            "joint-missing-id": _joint_action(
                joint_action_set_id="",
                member_event_refs=["scan-red-0001", "scan-blue-0001"],
                access_sets=[],
                realized_order=["scan-red-0001", "scan-missing-0001"],
                conflict_class="none",
                conflict_policy="none",
                isolation_guarantee="none",
                time_management_context_ref=None,
                exact_concurrency_claim=True,
            ),
            "joint-bad-access": _joint_action(
                joint_action_set_id="joint-bad-access",
                member_event_refs=["scan-red-0001"],
                access_sets=["not-a-map"],
                realized_order=[],
                conflict_class="none",
                conflict_policy="none",
                isolation_guarantee="none",
                time_management_context_ref=None,
            ),
        }
    )

    messages = _concurrency_violation_messages(payload)

    assert any("does not match joint_action_set_id" in message for message in messages)
    assert "joint action record requires joint_action_set_id" in messages
    assert "joint action member_event_refs entries must be non-empty strings" in messages
    assert "joint action access_sets must be a non-empty list" in messages
    assert "joint action access set must be a mapping" in messages
    assert "joint action access set requires member_event_ref" in messages
    assert "shared_state_read_refs must be a list" in messages
    assert "shared_state_write_refs entries must be non-empty strings" in messages
    assert "shared_state_write_refs entry 'state.missing' does not resolve" in messages
    assert "joint action realized_order must be a list" in messages
    assert "joint action realized_order must be an exact permutation of member_event_refs" in messages
    assert "time_management_context_ref 'tm-missing-0001' does not resolve" in messages
    assert "exact concurrency claims require time_management_context_ref" in messages


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "unsupported_disclosure": True,
                "exact_concurrency_claim": True,
            },
            "unsupported concurrency disclosure",
        ),
        (
            {
                "conflict_policy": "unsupported",
                "unsupported_disclosure": False,
                "realized_order": [],
                "isolation_guarantee": "none",
            },
            "unsupported conflict_policy",
        ),
        (
            {
                "conflict_policy": "serialize",
                "realized_order": [],
                "isolation_guarantee": "none",
            },
            "serialize conflict_policy",
        ),
        (
            {
                "conflict_policy": "retry",
                "isolation_guarantee": "serializable",
                "realized_order": [],
                "retry_limit": 1,
                "rollback_event_refs": ["scan-red-0001"],
            },
            "serializable joint action isolation",
        ),
        (
            {
                "conflict_policy": "retry",
                "realized_order": [],
                "isolation_guarantee": "none",
                "retry_limit": None,
                "rollback_event_refs": [],
            },
            "retry conflict_policy",
        ),
        (
            {
                "conflict_policy": "none",
                "realized_order": [],
                "isolation_guarantee": "none",
            },
            "none conflict_policy",
        ),
        (
            {
                "conflict_policy": "reject",
                "realized_order": [],
                "isolation_guarantee": "none",
                "atomicity_scope": "multi_object",
            },
            "multi_object conflicting joint actions",
        ),
        (
            {
                "access_sets": [
                    {"member_event_ref": "scan-red-0001", "shared_state_write_refs": [STATE_ADDRESS]},
                    {"member_event_ref": "scan-blue-0001", "shared_state_write_refs": [STATE_ADDRESS]},
                ],
                "conflict_class": "read_write",
                "conflict_policy": "reject",
                "isolation_guarantee": "none",
            },
            "conflict_class must match",
        ),
        (
            {
                "conflict_class": "none",
                "conflict_policy": "reject",
                "isolation_guarantee": "none",
                "unsupported_disclosure": True,
            },
            "conflict_class cannot be none",
        ),
    ],
)
def test_participant_concurrency_snapshot_validator_rejects_conflict_guardrails(
    overrides: dict[str, object],
    message: str,
) -> None:
    payload = _snapshot_payload(joint_action_records={"joint-red-blue-0001": _joint_action(**overrides)})

    messages = _concurrency_violation_messages(payload)

    assert any(message in violation for violation in messages)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"context_id": ""}, "requires context_id"),
        ({"context_id": "tm-other-0001"}, "does not match context_id"),
        (
            {"mode": "display", "claim_strength": "bounded", "basis": "logical_clock", "clock_ref": None},
            "clock_ref",
        ),
        (
            {
                "mode": "display",
                "claim_strength": "exact",
                "basis": "wall_clock_only",
                "clock_ref": "clock.wall",
                "backend_serialized": False,
            },
            "wall_clock_only time basis",
        ),
        ({"backend_serialized": False}, "backend_serialized mode"),
        (
            {
                "mode": "lookahead",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "backend_serialized": False,
            },
            "lookahead mode",
        ),
        (
            {
                "mode": "pacing",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "backend_serialized": False,
            },
            "pacing mode",
        ),
        (
            {
                "mode": "rollback",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "rollback_event_refs": [],
                "backend_serialized": False,
            },
            "rollback mode",
        ),
        (
            {
                "mode": "devs",
                "claim_strength": "display",
                "basis": "wall_clock_only",
                "clock_ref": None,
                "backend_serialized": False,
            },
            "devs and fmi modes",
        ),
        (
            {
                "mode": "unsupported",
                "claim_strength": "display",
                "basis": "wall_clock_only",
                "clock_ref": None,
                "backend_serialized": False,
            },
            "unsupported time-management mode",
        ),
        (
            {
                "mode": "display",
                "claim_strength": "exact",
                "basis": "logical_clock",
                "clock_ref": "clock.logical.runtime",
                "unsupported_disclosure": True,
                "backend_serialized": False,
            },
            "unsupported time-management disclosure",
        ),
    ],
)
def test_participant_concurrency_snapshot_validator_rejects_time_context_guardrails(
    overrides: dict[str, object],
    message: str,
) -> None:
    payload = _snapshot_payload(time_management_contexts={"tm-red-blue-0001": _time_context(**overrides)})

    messages = _concurrency_violation_messages(payload)

    assert any(message in violation for violation in messages)


def test_backend_apply_rejects_rewriting_joint_action_records() -> None:
    payload = _snapshot_payload()
    base_snapshot = RuntimeSnapshot(
        participant_behavior_history=dict(payload["participant_behavior_history"]),
        shared_state_records=dict(payload["shared_state_records"]),
        shared_state_history=dict(payload["shared_state_history"]),
        joint_action_records=dict(payload["joint_action_records"]),
        time_management_contexts=dict(payload["time_management_contexts"]),
    )

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                joint_action_records={},
                time_management_contexts=dict(snapshot.time_management_contexts),
            ),
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.concurrent-participants",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
    )

    assert result.success is False
    assert any("joint_action_records must be append-only" in item.message for item in result.diagnostics)


def test_backend_apply_accounts_for_participant_addresses_not_disclosure_record_ids() -> None:
    payload = _snapshot_payload()
    candidate = RuntimeSnapshot(**{key: value for key, value in payload.items() if key != "schema_version"})
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate, changed_addresses=[PARTICIPANT_RED, PARTICIPANT_BLUE, STATE_ADDRESS]),
        previous,
        address="runtime.control-plane.concurrent-participants",
        snapshot=previous,
        realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
    )
    assert result.success, result.diagnostics
    assert result.snapshot.joint_action_records == candidate.joint_action_records


def test_participant_concurrency_transition_validator_rejects_rewriting_records() -> None:
    assert (
        list(
            iter_participant_concurrency_transition_violations(
                {"": {}},
                {},
                [],
                {},
            )
        )
        == []
    )

    violations = list(
        iter_participant_concurrency_transition_violations(
            {"joint-red-blue-0001": _joint_action()},
            {"joint-red-blue-0001": _joint_action(conflict_policy="reject")},
            {"tm-red-blue-0001": _time_context()},
            {
                "tm-red-blue-0001": _time_context(
                    mode="display",
                    claim_strength="display",
                    basis="wall_clock_only",
                    backend_serialized=False,
                )
            },
        )
    )
    messages = [message for _address, message in violations]

    assert "joint_action_records must be append-only; record 'joint-red-blue-0001' changed" in messages
    assert "time_management_contexts must be append-only; record 'tm-red-blue-0001' changed" in messages


def test_joint_action_and_time_context_model_round_trip() -> None:
    joint_action = ParticipantJointActionRecordModel.model_validate(_joint_action())
    time_context = ParticipantTimeManagementContextModel.model_validate(_time_context())

    assert joint_action.model_dump(mode="json")["conflict_class"] == "read_write"
    assert time_context.model_dump(mode="json")["claim_strength"] == "bounded"
