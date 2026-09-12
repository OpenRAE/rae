"""RUN-307 shared operational state model tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance import _semantic_diagnostics
from raes_contracts.contracts import ParticipantSharedStateRecordModel, schema_bundle
from raes_contracts.participant_shared_state import (
    iter_participant_shared_state_history_transition_violations,
    iter_participant_shared_state_snapshot_violations,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from starlette.testclient import TestClient

PARTICIPANT = "participants.red.llm"
EPISODE = "ep-red-004"
ACTION_INSTANCE = "scan-0001"
STATE_ADDRESS = "hosts.web01.service.http"
T0 = "2026-05-26T10:50:00Z"


def _fixture_record(**overrides: object) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_path = (
        repo_root
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "participant-shared-state-record-v1"
        / "valid"
        / "serialized-service-state-commit.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload.update(overrides)
    return payload


def _record_for(state_address: str, **overrides: object) -> dict[str, object]:
    record = _fixture_record(state_address=state_address)
    for access in record["accesses"]:
        access["state_address"] = state_address
    record.update(overrides)
    return record


def _state_update_event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "state_transition_recorded",
        "timestamp": T0,
        "participant_address": PARTICIPANT,
        "episode_id": EPISODE,
        "action_instance_id": ACTION_INSTANCE,
        "state_transition_kind": "shared_state_updated",
        "post_state_digest": "sha256:known",
        "lifecycle_phase": "state_update_commit",
        "phase_realization": "runtime_mediated",
        "shared_state_refs": [STATE_ADDRESS],
        "details": {},
    }
    payload.update(overrides)
    return payload


def _snapshot_payload(
    *,
    shared_state_records: dict[str, dict[str, object]] | None = None,
    shared_state_history: dict[str, list[dict[str, object]]] | None = None,
    participant_behavior_history: dict[str, list[dict[str, object]]] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "runtime-snapshot/v1",
        "entries": {},
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": participant_behavior_history or {},
        "shared_state_records": shared_state_records or {},
        "shared_state_history": shared_state_history or {},
        "metadata": metadata or {},
    }


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


def test_runtime_snapshot_exposes_shared_state_records_and_history() -> None:
    record = _fixture_record()
    snapshot = RuntimeSnapshot(
        shared_state_records={STATE_ADDRESS: record},
        shared_state_history={STATE_ADDRESS: [record]},
    )
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target, initial_snapshot=snapshot)
    app = create_control_plane_app(control_plane, security=_security(target.name))

    with TestClient(app) as client:
        response = client.get("/snapshot", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["shared_state_records"][STATE_ADDRESS]["revision"] == "rev8"
    assert body["shared_state_history"][STATE_ADDRESS][0]["state_address"] == STATE_ADDRESS

    validator = Draft202012Validator(schema_bundle()["runtime-snapshot-v1"])
    assert list(validator.iter_errors(body)) == []


def test_shared_state_record_requires_revision_or_digest() -> None:
    invalid = _fixture_record(revision=None, digest=None)

    with pytest.raises(ValidationError, match="revision or digest"):
        ParticipantSharedStateRecordModel.model_validate(invalid)

    validator = Draft202012Validator(schema_bundle()["participant-shared-state-record-v1"])
    assert list(validator.iter_errors(invalid))


def test_runtime_snapshot_semantics_reject_unresolved_shared_state_ref() -> None:
    diagnostics = _semantic_diagnostics(
        "runtime-snapshot-v1",
        _snapshot_payload(
            participant_behavior_history={PARTICIPANT: [_state_update_event()]},
        ),
    )

    assert any("shared_state_refs" in item.message and STATE_ADDRESS in item.message for item in diagnostics)


def test_shared_state_semantics_reject_invalid_container_shapes() -> None:
    assert list(iter_participant_shared_state_snapshot_violations({}, {})) == []

    violations = list(iter_participant_shared_state_snapshot_violations([], [], metadata=[]))
    messages = [message for _, message in violations]

    assert "RuntimeSnapshot.metadata must be a mapping" in messages
    assert "shared_state_records must be a mapping" in messages
    assert "shared_state_history must be a mapping" in messages


def test_shared_state_semantics_reject_invalid_record_shapes_and_accesses() -> None:
    records: dict[object, object] = {
        "": _record_for(STATE_ADDRESS),
        "not.mapping": "invalid",
        "missing.scope": _record_for("missing.scope", state_scope=None),
        "outer.key": _record_for("inner.key"),
        "no.version": _record_for("no.version", revision=None, digest=None),
        "bad.accesses": _record_for("bad.accesses", accesses="invalid"),
        "access.not.mapping": _record_for("access.not.mapping", accesses=["invalid"]),
        "access.no.address": _record_for(
            "access.no.address",
            accesses=[{"access_kind": "read", "read_revision": "rev1"}],
        ),
        "access.mismatch": _record_for(
            "access.mismatch",
            accesses=[{"state_address": "other.address", "access_kind": "read", "read_revision": "rev1"}],
        ),
        "access.bad.kind": _record_for(
            "access.bad.kind",
            accesses=[{"state_address": "access.bad.kind", "access_kind": "observe"}],
        ),
        "access.no.read": _record_for(
            "access.no.read",
            accesses=[{"state_address": "access.no.read", "access_kind": "read"}],
        ),
        "access.no.write": _record_for(
            "access.no.write",
            accesses=[{"state_address": "access.no.write", "access_kind": "write"}],
        ),
    }

    messages = [
        message
        for _, message in iter_participant_shared_state_snapshot_violations(
            records,
            {},
        )
    ]

    expected_messages = [
        "shared_state_records keys must be non-empty strings",
        "shared state record must be a mapping",
        "shared state record is missing required fields: state_scope",
        "shared state record outer key 'outer.key' does not match state_address 'inner.key'",
        "shared state record requires revision or digest",
        "shared state record accesses must be a list",
        "shared state access must be a mapping",
        "shared state access state_address must be a non-empty string",
        "shared state access state_address 'other.address' does not match record state_address",
        "shared state access_kind 'observe' is not supported",
        "shared state read access requires read_revision or read_digest",
        "shared state write access requires write_revision or write_digest",
    ]
    for expected in expected_messages:
        assert expected in messages


def test_shared_state_semantics_reject_invalid_history_shapes() -> None:
    history: dict[object, object] = {
        "": [_record_for(STATE_ADDRESS)],
        "not.list": "invalid",
        "bad.record": ["invalid"],
    }

    messages = [
        message
        for _, message in iter_participant_shared_state_snapshot_violations(
            {},
            history,
        )
    ]

    assert "shared_state_history keys must be non-empty strings" in messages
    assert "shared_state_history entries must be lists" in messages
    assert "shared state history record must be a mapping" in messages


def test_shared_state_history_transition_rejects_removed_or_shrunk_history() -> None:
    original = _fixture_record()
    second = _fixture_record(revision="rev9")

    removed = list(iter_participant_shared_state_history_transition_violations({STATE_ADDRESS: [original]}, {}))
    shrunk = list(
        iter_participant_shared_state_history_transition_violations(
            {STATE_ADDRESS: [original, second]},
            {STATE_ADDRESS: [original]},
        )
    )

    assert any("history was removed" in message for _, message in removed)
    assert any("history shrank from 2 to 1 records" in message for _, message in shrunk)


def test_backend_apply_rejects_shared_state_in_metadata() -> None:
    base_snapshot = RuntimeSnapshot()
    record = _fixture_record()

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                metadata={"shared_state_records": {STATE_ADDRESS: record}},
            ),
            changed_addresses=[STATE_ADDRESS],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.shared-state",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({STATE_ADDRESS})
        ),
    )

    assert result.success is False
    assert any(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in result.diagnostics)


def test_backend_apply_rejects_shared_state_history_rewrite() -> None:
    original = _fixture_record()
    rewritten = _fixture_record(revision="rev9")
    base_snapshot = RuntimeSnapshot(
        shared_state_records={STATE_ADDRESS: original},
        shared_state_history={STATE_ADDRESS: [original]},
    )

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                shared_state_records={STATE_ADDRESS: rewritten},
                shared_state_history={STATE_ADDRESS: [rewritten]},
            ),
            changed_addresses=[STATE_ADDRESS],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.control-plane.shared-state",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({STATE_ADDRESS})
        ),
    )

    assert result.success is False
    assert any("shared_state_history must be append-only" in item.message for item in result.diagnostics)
