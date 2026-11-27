"""P2 worker grants and operator controls share the existing sealed authority."""

import asyncio

import httpx
from raes_contracts.planning import ProvisioningPlan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from test_issue_1362_distributed_authority import Dispatcher, worker
from test_issue_1362_provider_execution import Evidence, Provider, target


def test_worker_grant_is_authenticated_scoped_and_one_use_and_stop_is_operator_only():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher)
    operator = ControlPlaneIdentity("operator-1362", frozenset({ControlPlaneRole.OPERATOR}), "stub")
    auditor = ControlPlaneIdentity("auditor-1362", frozenset({ControlPlaneRole.AUDITOR}), "stub")
    app = create_control_plane_app(
        plane,
        security=ControlPlaneSecurityConfig(
            bearer_tokens={
                "worker-token": worker(),
                "operator-token": operator,
                "auditor-token": auditor,
            }
        ),
    )
    receipt = plane.submit_provisioning(ProvisioningPlan())
    request = dispatcher.commands[0]
    payload = {
        "binding": request.binding.model_dump(mode="json"),
        "capabilities": provider.operation_capabilities().model_dump(mode="json"),
        "admission": provider.check_operation(request).model_dump(mode="json"),
    }

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/operations/{receipt.operation_id}/invocation/grant"
            assert (await client.post(path, json=payload)).status_code == 401
            assert (
                await client.post(path, json=payload, headers={"Authorization": "Bearer operator-token"})
            ).status_code == 404
            headers = {"Authorization": "Bearer worker-token"}
            granted = await client.post(path, json=payload, headers=headers)
            assert granted.status_code == 200, granted.text
            assert granted.json()["request"] == request.model_dump(mode="json")
            assert "no-store" in granted.headers["cache-control"]
            assert (await client.post(path, json=payload, headers=headers)).status_code == 409
            assert (await client.post("/execution/stop", headers=headers)).status_code == 403
            assert (
                await client.post("/execution/stop", headers={"Authorization": "Bearer auditor-token"})
            ).status_code == 403
            assert (
                await client.post("/execution/stop", headers={"Authorization": "Bearer operator-token"})
            ).status_code == 204
            assert provider.starts == 0

    try:
        asyncio.run(exercise())
    finally:
        plane.close()
