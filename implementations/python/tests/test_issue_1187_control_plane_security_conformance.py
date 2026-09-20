"""CP-9 adversarial configuration and provider-disclosure regressions."""

from __future__ import annotations

from dataclasses import asdict

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.plan_projection import evaluation_plan_model, orchestration_plan_model, provisioning_plan_model
from raes_contracts.planning import (
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    ProvisioningPlan,
    ProvisionOp,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from starlette.testclient import TestClient

pytestmark = pytest.mark.control_plane_conformance


def _identity(name: str = "operator") -> ControlPlaneIdentity:
    return ControlPlaneIdentity(identity=name, roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub")


@pytest.mark.parametrize(
    "settings",
    [
        {"identity_header": "Authorization"},
        {"verified_header": "AUTHORIZATION"},
        {"identity_header": "X-Identity", "verified_header": "x-identity"},
        {"identity_header": ""},
        {"verified_header": "bad\nheader"},
        {"bearer_tokens": {"": _identity()}},
        {"bearer_tokens": {"   ": _identity()}},
        {"bearer_tokens": {"token": _identity("")}},
        {"trusted_identities": {"": _identity()}},
        {"trusted_identities": {"proxy": _identity(" ")}},
    ],
)
def test_security_configuration_rejects_ambiguous_or_empty_identity(settings: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ControlPlaneSecurityConfig(**settings)


def test_empty_bearer_configuration_cannot_authenticate_an_empty_credential() -> None:
    # Construction is the admission boundary: an empty credential must never
    # become a usable configured principal in the HTTP adapter.
    with pytest.raises(ValueError):
        security = ControlPlaneSecurityConfig(bearer_tokens={"": _identity()})
        with TestClient(
            create_control_plane_app(RuntimeControlPlane(create_stub_target()), security=security)
        ) as client:
            response = client.get("/snapshot", headers={"authorization": "Bearer "})
            assert response.status_code == 401


@pytest.mark.parametrize("method", ["validate", "apply"])
def test_provider_failure_redacts_type_message_chain_and_durable_carriers(tmp_path, caplog, method: str) -> None:
    target = create_stub_target()
    secret_type = type("SyntheticProviderSecret1187", (RuntimeError,), {})

    def fail(*_args):
        try:
            raise OSError("synthetic-inner-secret-1187")
        except OSError as cause:
            raise secret_type("synthetic-provider-secret-1187") from cause

    setattr(target.provisioner, method, fail)
    store = LocalControlPlaneStore(tmp_path / "store")
    control_plane = RuntimeControlPlane(target, store=store)
    security = ControlPlaneSecurityConfig(bearer_tokens={"synthetic-token": _identity()})
    with TestClient(create_control_plane_app(control_plane, security=security)) as client:
        response = client.post(
            "/operations/provisioning",
            json=provisioning_plan_model(ProvisioningPlan()).model_dump(mode="json"),
            headers={"authorization": "Bearer synthetic-token"},
        )
        assert response.status_code == 200
        status = client.get(
            f"/operations/{response.json()['operation_id']}", headers={"authorization": "Bearer synthetic-token"}
        )
        assert status.status_code == 200
        assert status.json()["state"] == "failed"
        evidence = repr((response.json(), status.json(), store.load_records(), [asdict(e) for e in store.read_audit()]))
        assert "runtime.backend-call-failed" in evidence
        for secret in (secret_type.__name__, "synthetic-provider-secret-1187", "synthetic-inner-secret-1187"):
            assert secret not in evidence + caplog.text


@pytest.mark.parametrize("domain", ["provisioning", "orchestration", "evaluation"])
def test_planner_denial_preserves_forbidden_response_when_audit_fails(tmp_path, monkeypatch, caplog, domain) -> None:
    control_plane = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(tmp_path / "store"))
    security = ControlPlaneSecurityConfig(bearer_tokens={"synthetic-token": _identity()})

    def fail_audit(**_kwargs):
        raise OSError("synthetic-audit-secret-1187")

    monkeypatch.setattr(control_plane, "record_audit", fail_audit)
    # A valid nonempty portable plan has not been registered by the planner.
    model = {
        "provisioning": provisioning_plan_model(
            ProvisioningPlan(
                operations=[
                    ProvisionOp(
                        action=ChangeAction.CREATE, address="provision.network.lan", resource_type="network", payload={}
                    )
                ]
            )
        ),
        "orchestration": orchestration_plan_model(
            OrchestrationPlan(
                operations=[
                    OrchestrationOp(
                        action=ChangeAction.CREATE,
                        address="orchestration.workflow.test",
                        resource_type="workflow",
                        payload={},
                    )
                ]
            )
        ),
        "evaluation": evaluation_plan_model(
            EvaluationPlan(
                operations=[
                    EvaluationOp(
                        action=ChangeAction.CREATE,
                        address="evaluation.assertion.test",
                        resource_type="assertion",
                        payload={},
                    )
                ]
            )
        ),
    }[domain]
    with TestClient(
        create_control_plane_app(control_plane, security=security), raise_server_exceptions=False
    ) as client:
        response = client.post(
            f"/operations/{domain}",
            json=model.model_dump(mode="json"),
            headers={"authorization": "Bearer synthetic-token"},
        )
        assert response.status_code == 403
        assert response.json() == {"detail": f"{domain} plan is not planner-authorized"}
        assert control_plane._store.load_records() == {}
        assert "synthetic-audit-secret-1187" not in response.text + caplog.text
