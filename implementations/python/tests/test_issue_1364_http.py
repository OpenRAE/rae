"""Reusable control uses bounded duplicate-preserving JSON ingress."""

import json

from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneSecurityConfig
from reusable_control_runtime_fixtures import PARTICIPANT, configured_plane, handoff, identity
from starlette.testclient import TestClient


def test_duplicate_application_coordinates_are_rejected_before_parsing_loses_them():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="first")
        payload = json.dumps(intent.model_dump(mode="json"))
        payload = payload.replace(
            '"expected_state_revision": 0', '"expected_state_revision": 99, "expected_state_revision": 0'
        )
        app = create_control_plane_app(
            plane, security=ControlPlaneSecurityConfig(bearer_tokens={"test-token": identity()})
        )
        with TestClient(app) as client:
            response = client.post(
                f"/participants/{PARTICIPANT}/control-occurrences",
                content=payload,
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/json",
                    "Idempotency-Key": "first",
                },
            )
            assert plane.snapshot.participant_control_history.get(PARTICIPANT, []) == []

        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"


def test_cancellation_readback_requires_current_participant_subject_access():
    from dataclasses import replace

    from test_issue_1364_cancellation import cancellation, proposal

    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        plane.record_participant_control(
            PARTICIPANT, proposal(plane, owner), identity=identity(), idempotency_key="propose"
        )
        receipt = plane.record_participant_control(
            PARTICIPANT, cancellation(plane, owner, "propose"), identity=identity(), idempotency_key="cancel"
        )
        app = create_control_plane_app(
            plane,
            security=ControlPlaneSecurityConfig(
                bearer_tokens={"bound": identity(), "unbound": replace(identity(), participant_control_subjects=())}
            ),
        )
        with TestClient(app) as client:
            path = f"/operations/{receipt.operation_id}/participant-cancellation"
            allowed = client.get(path, headers={"Authorization": "Bearer bound"})
            assert allowed.status_code == 200
            assert allowed.json()["cancellation_effect"] == "prevented"
            assert allowed.headers["cache-control"] == "no-store"
            denied = client.get(path, headers={"Authorization": "Bearer unbound"})
            assert denied.status_code == 404
