"""Strict authenticated ingress for optional participant inject composition."""

import json

import pytest
from participant_inject_runtime_fixtures import caller, configured_plane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneSecurityConfig
from starlette.testclient import TestClient


def test_http_delivers_governed_content_and_retries_without_world_dispatch(tmp_path):
    plane, backend, _, request = configured_plane(tmp_path)
    from dataclasses import replace

    app = create_control_plane_app(
        plane,
        security=ControlPlaneSecurityConfig(
            bearer_tokens={"test-token": caller(), "other-token": replace(caller(), identity="other")}
        ),
    )
    with TestClient(app) as client:
        body = request.model_dump(mode="json")
        assert client.post("/injects/deliver", json=body).status_code == 401
        headers = {"Authorization": "Bearer test-token"}
        first = client.post("/injects/deliver", json=body, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["delivery"]["content"] == "Approved briefing result"
        assert first.headers["cache-control"] == "no-store"
        assert client.post("/injects/deliver", json=body, headers=headers).json() == first.json()
        operation_id = first.json()["operation_id"]
        path = f"/operations/{operation_id}/inject-delivery"
        assert client.get(path, headers=headers).json() == first.json()["delivery"]
        assert client.get(path, headers={"Authorization": "Bearer other-token"}).status_code == 404
        assert (
            client.get(
                "/operations/unknown/inject-delivery", headers={"Authorization": "Bearer other-token"}
            ).status_code
            == 404
        )
        capture = client.get(f"/operations/{request.world_operation_id}/inject-capture", headers=headers)
        assert capture.status_code == 200
        assert capture.json()["status"] == "succeeded"
        assert backend.starts == 1


@pytest.mark.parametrize("malformed", ["duplicate", "extra", "nonfinite", "coerced"])
def test_delivery_json_refuses_ambiguous_inputs_without_disclosure(tmp_path, malformed):
    plane, backend, _, request = configured_plane(tmp_path)
    app = create_control_plane_app(plane, security=ControlPlaneSecurityConfig(bearer_tokens={"test-token": caller()}))
    body = request.model_dump(mode="json")
    encoded = json.dumps(body)
    if malformed == "duplicate":
        encoded = '{"request_key":"other",' + encoded[1:]
    elif malformed == "coerced":
        body["expected_snapshot_revision"] = True
        encoded = json.dumps(body)
    else:
        encoded = '{"untrusted":' + ("NaN" if malformed == "nonfinite" else '"private-value"') + "," + encoded[1:]
    with TestClient(app) as client:
        refused = client.post(
            "/injects/deliver",
            content=encoded,
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
        )
        assert refused.status_code == 422
        assert "private-value" not in refused.text
        assert backend.starts == 1


def test_named_p2_delivery_uses_a_durable_p1_core_and_current_audience_authority(tmp_path):
    from raes_runtime.control_plane_profiles import ControlPlaneProfile
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    plane, backend, _, request = configured_plane(
        tmp_path, store=LocalControlPlaneStore(tmp_path / "ledger"), profile=ControlPlaneProfile.P1
    )
    app = create_control_plane_app(
        plane,
        profile=ControlPlaneProfile.P2,
        security=ControlPlaneSecurityConfig(
            bearer_tokens={"test-token": caller(), "no-audience-token": caller(audience=False)}
        ),
    )
    with TestClient(app) as client:
        body = request.model_dump(mode="json")
        denied = client.post("/injects/deliver", json=body, headers={"Authorization": "Bearer no-audience-token"})
        assert denied.status_code == 403
        allowed = client.post("/injects/deliver", json=body, headers={"Authorization": "Bearer test-token"})
        assert allowed.status_code == 200, allowed.text
        assert backend.starts == 1
