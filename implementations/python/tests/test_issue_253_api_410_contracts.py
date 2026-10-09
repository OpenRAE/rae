"""API-410 shared operational state and derived context contract verification (issue #253).

The published RUN-307 shared-state record and the API-408/SEM-214 context view are
driven through their public validation and retrieval paths: the models and
published schemas, the ACT-604 information-state join, and the control-plane
context route. Each case is a valid composition or a stale, mismatched,
unauthorized, or unsupported input. Nothing here shows that a backend can compute
a given operational view.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from participant_crossing_fixtures import PARTICIPANT as GOVERNED_PARTICIPANT
from pydantic import ValidationError
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance import validate_contract_payload
from raes_contracts.contracts import (
    ParticipantContextViewModel,
    ParticipantInformationStateRecordModel,
    ParticipantInformationStateSourceCoordinate,
    ParticipantInformationStateValidationContext,
    ParticipantSharedStateRecordModel,
    validate_participant_information_state_context,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from starlette.testclient import TestClient
from test_issue_1359_runtime_api_trust_boundary import _bearer, _governed_app

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSITION_DOC = REPO_ROOT / "docs" / "explain" / "reference" / "shared-state-context-composition.md"
COMPOSITION_VIEW_BLOCK = re.compile(r"<!-- api-410-composition-view:start -->\s*```json\s*(.*?)\s*```", re.DOTALL)
RUNTIME_FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "participant-runtime"
SHARED_STATE = "participant-shared-state-record-v1"
CONTEXT_VIEW = "participant-context-view-v1"
INFORMATION_STATE = "participant-information-state-record-v1"
PUBLISHED_SCHEMAS = {
    SHARED_STATE: REPO_ROOT / "contracts" / "schemas" / "participant-runtime" / f"{SHARED_STATE}.json",
    CONTEXT_VIEW: REPO_ROOT / "contracts" / "schemas" / "control-plane" / f"{CONTEXT_VIEW}.json",
}
PARTICIPANT = "participants.red.llm"
EPISODE = "ep-red-004"
STATE_ADDRESS = "hosts.web01.service.http"
VIEW_REF = "views.context.service-posture.v1"
REVISION_HEADER = "x-raes-snapshot-revision"
OTHER_PROJECTION = "projections.blue.context.v1"
OTHER_REDACTION = "redaction.blue-observation.v1"
DIGEST = "sha256:" + "c" * 64

# Each case changes one source of the joined composition: "state" is the shared-state
# record, "view" the context view, and "join" the information-state record citing both.
JOIN_REJECTIONS = {
    "state-after-cut": ("state", ("sequence_number",), 19, "after the exact sequence cut"),
    "superseded-revision": ("join", ("source_refs", 0, "ref"), "state-web01-http-rev7", "shared-state source identity"),
    "state-visibility": ("state", ("visibility_projection_basis",), OTHER_PROJECTION, "shared-state visibility"),
    "state-redaction": ("state", ("redaction_policy_ref",), OTHER_REDACTION, "shared-state redaction"),
    "view-visibility": ("view", ("visibility_projection_ref",), OTHER_PROJECTION, "context-view visibility"),
    "view-redaction": ("view", ("redaction_policy_ref",), OTHER_REDACTION, "context-view redaction"),
    "view-episode": ("view", ("episode_id",), "ep-red-005", "context-view source coordinate"),
    "state-cited-as-derived": ("join", ("source_refs", 0, "relation"), "derived", "not admitted"),
    "view-cited-as-state": ("join", ("source_refs", 1, "relation"), "shared_state_projection", "not admitted"),
}
VIEW_SOURCE_REJECTIONS = {
    "undeclared-input": (("transformation", "input_source_ids"), ["observation-red-86"], "reference source_layers"),
    "unlisted-ref": (("source_layers", 1, "ref"), "obs-red-86", "listed in derived_from_refs"),
    "duplicate-source-id": (("source_layers", 1, "source_id"), "shared-state-snapshot", "must be unique"),
}


def _shared_state_record() -> dict[str, Any]:
    path = RUNTIME_FIXTURES / SHARED_STATE / "valid" / "serialized-service-state-commit.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _composition_view() -> dict[str, Any]:
    match = COMPOSITION_VIEW_BLOCK.search(COMPOSITION_DOC.read_text(encoding="utf-8"))
    assert match is not None
    return json.loads(match.group(1))


def _information_state(record: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    path = RUNTIME_FIXTURES / INFORMATION_STATE / "valid" / "history-consistent-cut.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for strong_claim_field in (
        "occurrence_history_ref",
        "reconstruction_profile_ref",
        "reconstruction_algorithm_id",
        "reconstruction_algorithm_version",
        "reconstruction_proof_ref",
        "reconstructed_state_digest",
    ):
        payload.pop(strong_claim_field)
    payload.update(
        event_id="information-state-red-18",
        participant_address=PARTICIPANT,
        episode_id=EPISODE,
        sequence_number=18,
        actor_ref=PARTICIPANT,
        authorization_scope=f"participant:{PARTICIPANT}",
        information_state_ref="information-state.red.ep004.cut18",
        payload_ref="payloads.information-state.red.ep004.cut18",
        state_cut={
            "cut_kind": "sequence_prefix",
            "cut_ref": "cut.red.ep004.18",
            "history_domain": "participant_behavior_history",
            "order_model": "backend_serialized_order",
            "anchor_event_ref": "evt-red-18",
            "anchor_order": 18,
            "history_prefix_length": 19,
            "predecessor_event_refs": ["evt-red-17"],
        },
        memory_reset_authority_ref="episode-reset.red.ep004",
        audience_scope_ref="audiences.participant.red",
        visibility_projection_ref=view["visibility_projection_ref"],
        projection_version="projection.red.v1",
        projection_policy_revision="projection.red.v1",
        redaction_policy_ref=view["redaction_policy_ref"],
        redaction_policy_revision="redaction.shared-state.rev1",
        information_guarantee="observation_only",
        source_refs=[
            {"contract_id": SHARED_STATE, "ref": record["event_id"], "relation": "shared_state_projection"},
            {"contract_id": CONTEXT_VIEW, "ref": view["view_id"], "relation": "derived"},
        ],
    )
    return payload


def _join_payloads() -> dict[str, dict[str, Any]]:
    record, view = _shared_state_record(), _composition_view()
    return {"state": record, "view": view, "join": _information_state(record, view)}


def _join_context(payloads: dict[str, dict[str, Any]]) -> ParticipantInformationStateValidationContext:
    """Resolve each cited source as a trusted resolver would, at the record's own cut."""

    record = ParticipantInformationStateRecordModel.model_validate(payloads["join"])
    coordinate = ParticipantInformationStateSourceCoordinate(
        participant_address=record.participant_address,
        episode_id=record.episode_id,
        state_cut=record.state_cut,
        audience_scope_ref=record.audience_scope_ref,
        visibility_projection_ref=record.visibility_projection_ref,
        projection_policy_revision=record.projection_policy_revision,
        redaction_policy_ref=record.redaction_policy_ref,
        redaction_policy_revision=record.redaction_policy_revision,
    )
    resolved = {SHARED_STATE: payloads["state"], CONTEXT_VIEW: payloads["view"]}
    keys = [(source.contract_id, source.ref) for source in record.source_refs]
    return ParticipantInformationStateValidationContext(
        occurrence_histories={},
        resolved_sources={key: resolved[key[0]] for key in keys},
        source_coordinates=dict.fromkeys(keys, coordinate),
        proof_digests={},
    )


def _replace(payload: Any, path: tuple[str | int, ...], value: object) -> None:
    *parents, leaf = path
    for key in parents:
        payload = payload[key]
    payload[leaf] = value


def _schema_accepts(contract_id: str, payload: dict[str, Any]) -> bool:
    schema = json.loads(PUBLISHED_SCHEMAS[contract_id].read_text(encoding="utf-8"))
    return not list(Draft202012Validator(schema).iter_errors(payload))


def _model_accepts(payload: dict[str, Any]) -> bool:
    try:
        ParticipantSharedStateRecordModel.model_validate(payload)
    except ValidationError:
        return False
    return True


def _identity(name: str, role: ControlPlaneRole, target_name: str) -> ControlPlaneIdentity:
    return ControlPlaneIdentity(identity=name, roles=frozenset({role}), target_name=target_name)


def test_composition_example_is_a_valid_view_of_the_published_revision() -> None:
    record, view = _shared_state_record(), _composition_view()
    access = record["accesses"][0]

    model = ParticipantContextViewModel.model_validate(view)

    assert _schema_accepts(CONTEXT_VIEW, view)
    assert model.source_snapshot_ref == access["snapshot_ref"]
    assert f"{STATE_ADDRESS}@{record['revision']}" in model.derived_from_refs
    assert record["predecessor_revision_refs"] == [f"{STATE_ADDRESS}@{access['read_revision']}"]
    assert model.observation_point == record["logical_order_ref"]
    assert set(record["evidence_refs"]) <= set(model.evidence_refs)


def test_information_state_joins_the_shared_state_revision_and_the_derived_view() -> None:
    payloads = _join_payloads()
    context = _join_context(payloads)

    diagnostics = validate_contract_payload(
        INFORMATION_STATE,
        payloads["join"],
        information_state_context_resolver=lambda _record, _scope: context,
    )

    assert diagnostics == ()


@pytest.mark.parametrize(
    ("target", "path", "value", "error"), list(JOIN_REJECTIONS.values()), ids=list(JOIN_REJECTIONS)
)
def test_information_state_join_rejects_stale_mismatched_or_unsupported_sources(
    target: str,
    path: tuple[str | int, ...],
    value: object,
    error: str,
) -> None:
    payloads = _join_payloads()
    _replace(payloads[target], path, value)
    context = _join_context(payloads)

    with pytest.raises(ValueError, match=error):
        validate_participant_information_state_context(
            ParticipantInformationStateRecordModel.model_validate(payloads["join"]),
            reconstruction_profiles={},
            occurrence_histories=context.occurrence_histories,
            resolved_sources=context.resolved_sources,
            source_coordinates=context.source_coordinates,
            proof_digests=context.proof_digests,
        )


@pytest.mark.parametrize(
    ("access_kind", "markers", "accepted"),
    [
        ("read", {"read_revision": "rev7"}, True),
        ("read", {"write_revision": "rev8"}, False),
        ("write", {"write_digest": DIGEST}, True),
        ("write", {"read_digest": DIGEST}, False),
        ("read_write", {"read_revision": "rev7", "write_digest": DIGEST}, True),
        ("read_write", {"write_revision": "rev8"}, False),
    ],
)
def test_access_revision_markers_agree_across_model_and_published_schema(
    access_kind: str,
    markers: dict[str, str],
    accepted: bool,
) -> None:
    record = _shared_state_record()
    record["accesses"] = [
        {"state_address": STATE_ADDRESS, "access_kind": access_kind, "access_purpose": "commit", **markers}
    ]

    assert (_model_accepts(record), _schema_accepts(SHARED_STATE, record)) == (accepted, accepted)


@pytest.mark.parametrize(
    ("path", "value", "error"), list(VIEW_SOURCE_REJECTIONS.values()), ids=list(VIEW_SOURCE_REJECTIONS)
)
def test_view_rejects_derivation_sources_outside_its_declared_layers(
    path: tuple[str | int, ...],
    value: object,
    error: str,
) -> None:
    view = _composition_view()
    _replace(view, path, value)

    with pytest.raises(ValidationError, match=error):
        ParticipantContextViewModel.model_validate(view)


def test_runtime_view_names_the_snapshot_revision_that_holds_the_shared_state() -> None:
    record = _shared_state_record()
    target = create_stub_target()
    control_plane = RuntimeControlPlane(
        target,
        initial_snapshot=RuntimeSnapshot(
            shared_state_records={STATE_ADDRESS: record},
            shared_state_history={STATE_ADDRESS: [record]},
        ),
    )
    control_plane.initialize_participant_episode(PARTICIPANT, episode_id=EPISODE)
    security = ControlPlaneSecurityConfig(
        bearer_tokens={
            "auditor-token": _identity("auditor", ControlPlaneRole.AUDITOR, target.name),
            "backend-token": _identity("backend", ControlPlaneRole.BACKEND, target.name),
        }
    )
    path = f"/participants/{PARTICIPANT}/context"
    query = {"view_ref": VIEW_REF, "episode_id": EPISODE}
    reader = _bearer("auditor-token")

    with TestClient(create_control_plane_app(control_plane, security=security)) as client:
        first = client.get(path, params=query, headers=reader)
        snapshot = client.get("/snapshot", headers=reader)
        mutation = client.post(
            "/participants/participants.blue.rl/episodes/initialize", json={}, headers=_bearer("backend-token")
        )
        second = client.get(path, params=query, headers=reader)
        other_episode = client.get(path, params={**query, "episode_id": "ep-red-005"}, headers=reader)

    first_view = ParticipantContextViewModel.model_validate(first.json())
    second_view = ParticipantContextViewModel.model_validate(second.json())
    assert snapshot.headers[REVISION_HEADER] == first.headers[REVISION_HEADER]
    assert snapshot.json()["shared_state_records"][STATE_ADDRESS]["revision"] == record["revision"]
    assert first_view.source_snapshot_ref == f"runtime.snapshot.revision.{first.headers[REVISION_HEADER]}"
    assert mutation.status_code == 200
    assert int(second.headers[REVISION_HEADER]) > int(first.headers[REVISION_HEADER])
    assert second_view.source_snapshot_ref == f"runtime.snapshot.revision.{second.headers[REVISION_HEADER]}"
    assert other_episode.status_code == 404


@pytest.mark.parametrize(
    ("token", "status"),
    [("bound-token", 200), ("other-participant-token", 403), ("unbound-token", 403), ("ambiguous-token", 409)],
)
def test_governed_context_view_requires_exactly_one_audience_binding(token: str, status: int) -> None:
    app, control_plane = _governed_app()

    with TestClient(app) as client:
        response = client.get(
            f"/participants/{GOVERNED_PARTICIPANT}/context", params={"view_ref": VIEW_REF}, headers=_bearer(token)
        )
        crossings = control_plane.snapshot.participant_crossing_history.get(GOVERNED_PARTICIPANT, [])

    assert response.status_code == status
    assert bool(crossings) is (status == 200)


@pytest.mark.parametrize(
    ("options", "error"),
    [
        pytest.param({"audience_scope": "audience_neutral"}, "unexpected participant context options", id="audience"),
        pytest.param({"meaning_ref": "semantics.other.v1"}, "unexpected participant context options", id="meaning"),
        pytest.param({"derived_from_refs": ["snapshots.sim.tick88"]}, "must be a tuple of strings", id="list-sources"),
    ],
)
def test_runtime_context_projection_rejects_unsupported_options(options: dict[str, object], error: str) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    control_plane.initialize_participant_episode(PARTICIPANT, episode_id=EPISODE)

    with pytest.raises(TypeError, match=error):
        control_plane.get_participant_context_view(PARTICIPANT, view_ref=VIEW_REF, **options)
