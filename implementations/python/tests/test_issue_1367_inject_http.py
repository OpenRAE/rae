"""Authenticated, bounded trigger ingress and separately authorized world readback."""

import json

import pytest
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from starlette.testclient import TestClient
from test_issue_1367_inject_execution import configured_plane


def served(tmp_path):
    plane, backend, request = configured_plane(tmp_path)

    def identity(name, role):
        return ControlPlaneIdentity(name, frozenset({role}), "stub")

    app = create_control_plane_app(
        plane,
        security=ControlPlaneSecurityConfig(
            bearer_tokens={
                "operator-token": identity("operator", ControlPlaneRole.OPERATOR),
                "other-token": identity("other", ControlPlaneRole.OPERATOR),
                "auditor-token": identity("auditor", ControlPlaneRole.AUDITOR),
            }
        ),
    )
    return TestClient(app), backend, request.model_dump(mode="json")


def bearer(token="operator-token"):  # noqa: S107 -- synthetic transport fixture.
    return {"Authorization": "Bearer " + token}


def test_public_trigger_and_readback_are_actor_scoped_and_retry_does_not_refire(tmp_path):
    client, backend, body = served(tmp_path)
    with client:
        assert client.post("/injects/trigger", json=body).status_code == 401
        assert client.post("/injects/trigger", json=body, headers=bearer("auditor-token")).status_code == 403
        accepted = client.post("/injects/trigger", json=body, headers=bearer())
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["accepted"]
        operation_id = accepted.json()["operation_id"]
        assert backend.path.read_bytes() == backend.content
        assert client.post("/injects/trigger", json=body, headers=bearer()).json() == accepted.json()
        assert backend.starts == 1
        for suffix in ("inject-occurrence", "inject-outcome", "inject-correlation", "inject-result"):
            path = f"/operations/{operation_id}/{suffix}"
            readback = client.get(path, headers=bearer())
            assert readback.status_code == 200, readback.text
            assert readback.headers["cache-control"] == "no-store"
            assert client.get(path, headers=bearer("other-token")).status_code == 404
            assert client.get(f"/operations/unknown/{suffix}", headers=bearer("other-token")).status_code == 404
        path = f"/operations/{operation_id}/inject-artifacts/world-result"
        artifact = client.get(path, headers=bearer())
        assert artifact.status_code == 200 and artifact.content == backend.content
        assert artifact.headers["cache-control"] == "no-store"
        assert artifact.headers["x-content-type-options"] == "nosniff"
        assert client.get(path, headers=bearer("other-token")).status_code == 404


@pytest.mark.parametrize("malformed", ["duplicate", "nonfinite", "depth", "extra"])
def test_ambiguous_or_unbounded_input_is_refused_before_claim_or_effect(tmp_path, malformed):
    client, backend, body = served(tmp_path)
    encoded = json.dumps(body)
    if malformed == "duplicate":
        encoded = '{"request_key":"conflicting-key",' + encoded[1:]
    elif malformed == "nonfinite":
        encoded = '{"untrusted":NaN,' + encoded[1:]
    elif malformed == "depth":
        encoded = '{"untrusted":' + "[" * 40 + "0" + "]" * 40 + "}"
    else:
        encoded = '{"untrusted":"sensitive-input",' + encoded[1:]
    with client:
        denied = client.post(
            "/injects/trigger", content=encoded, headers={**bearer(), "content-type": "application/json"}
        )
        assert denied.status_code == 422
        assert denied.headers["cache-control"] == "no-store"
        assert "sensitive-input" not in denied.text
        assert backend.starts == 0
        assert not backend.path.exists()


def test_http_retry_header_cannot_create_an_independent_claim(tmp_path):
    client, backend, body = served(tmp_path)
    with client:
        response = client.post("/injects/trigger", json=body, headers={**bearer(), "idempotency-key": "another-key"})
        assert response.status_code == 409
        assert backend.starts == 0


def test_authentication_precedes_malformed_body_details_and_byte_bound_is_enforced(tmp_path):
    client, backend, body = served(tmp_path)
    with client:
        assert client.post("/injects/trigger", content="not-json").status_code == 401
        response = client.post("/injects/trigger", content=" " * (256 * 1024 + 1), headers=bearer())
        assert response.status_code == 413
        assert backend.starts == 0
