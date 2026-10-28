"""Bounded authenticated worker client for the existing P2 state authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
from pydantic import JsonValue, SecretStr
from raes_contracts.contracts import BackendOperationControlModel, BackendOperationRequestModel, OperationStatusModel

from .control_plane_operation_context import operation_actor_scope
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole, _require_principal_shape
from .operation_control_budget import ControlDeliveryGrant
from .operation_execution_adapter import LocalExecutionAdapter, require_budget_ms
from .operation_worker_authority import InvocationGrant

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationCapabilitiesModel, BackendOperationResponseModel

    from .operation_temporal import EngineOperationReference


@dataclass(frozen=True, kw_only=True)
class RemoteAuthorityConfiguration:
    base_url: str
    identity: ControlPlaneIdentity
    bearer_token: SecretStr = field(repr=False)
    rpc_budget_ms: int = 2000
    max_response_bytes: int = 1_000_000
    allow_insecure_loopback: bool = False

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        if url.username or url.password or url.query or url.fragment or not url.hostname:
            raise ValueError("worker authority URL is invalid")
        if type(self.allow_insecure_loopback) is not bool:
            raise ValueError("loopback option must be a bool")
        if url.scheme != "https":
            _require_insecure_loopback(url.scheme, url.hostname, self.allow_insecure_loopback)
        self._require_worker_credential()
        require_budget_ms(self.rpc_budget_ms)
        if type(self.max_response_bytes) is not int or not 1 <= self.max_response_bytes <= 1_000_000:
            raise ValueError("worker authority response bound is invalid")

    def _require_worker_credential(self) -> None:
        if not isinstance(self.bearer_token, SecretStr) or not self.bearer_token.get_secret_value():
            raise ValueError("worker authority requires a protected credential")
        _require_principal_shape(self.identity)
        if ControlPlaneRole.BACKEND not in self.identity.roles or self.identity.target_name is None:
            raise ValueError("worker authority requires a target-bound backend identity")


def _require_insecure_loopback(scheme: str, hostname: str, allowed: bool) -> None:
    try:
        loopback = ip_address(hostname).is_loopback
    except ValueError:
        loopback = False
    if scheme != "http" or not allowed or not loopback:
        raise ValueError("worker authority requires HTTPS")


class RemoteOperationAuthority:
    """Instantiate separately for effect and control workers; no shared pool."""

    def __init__(
        self, configuration: RemoteAuthorityConfiguration, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.configuration = configuration
        self._client = httpx.Client(
            base_url=configuration.base_url.rstrip("/") + "/",
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=configuration.rpc_budget_ms / 1000,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        )
        self._executor = LocalExecutionAdapter(control_capacity=2)

    def _rpc(self, method: str, path: str, payload: JsonValue = None) -> JsonValue:
        def invoke() -> JsonValue:
            with self._client.stream(
                method,
                path,
                json=payload,
                headers={
                    "Authorization": "Bearer " + self.configuration.bearer_token.get_secret_value(),
                },
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError("worker authority request was refused or unavailable")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ValueError("worker authority content encoding is unsupported")
                content = bytearray()
                for chunk in response.iter_raw():
                    if len(content) + len(chunk) > self.configuration.max_response_bytes:
                        raise ValueError("worker authority response exceeds its bound")
                    content.extend(chunk)
                import json

                return json.loads(content)

        try:
            return self._executor.call("control", invoke, timeout_ms=self.configuration.rpc_budget_ms)
        except Exception:
            raise RuntimeError("worker authority response could not be established") from None

    def advance_runtime(self, reference):
        """Reconcile a durable state cut; no fresh attempt is implied by redelivery."""
        from .runtime_sequence_reference import RuntimeSequenceReference

        reference = RuntimeSequenceReference.model_validate(reference.model_dump(mode="json"))
        if reference.worker_id != self.configuration.identity.identity:
            raise PermissionError("runtime worker reference is forbidden")
        if self.configuration.rpc_budget_ms >= reference.activity_budget_ms:
            raise ValueError("runtime activity budget must exceed its bounded authority call")
        return self._rpc("POST", "runtime/progress", reference.model_dump(mode="json"))

    def _path(self, reference: EngineOperationReference, suffix: str = "") -> str:
        if reference.worker_id != self.configuration.identity.identity:
            raise PermissionError("worker reference is forbidden")
        return f"operations/{quote(reference.operation_id, safe='')}/invocation{suffix}"

    def get_request(self, reference: EngineOperationReference) -> BackendOperationRequestModel:
        request = BackendOperationRequestModel.model_validate(self._rpc("GET", self._path(reference)))
        reference.require_request(request)
        return request

    def claim(
        self,
        reference: EngineOperationReference,
        capabilities: BackendOperationCapabilitiesModel,
        admission: BackendOperationResponseModel,
    ) -> InvocationGrant:
        request = self.get_request(reference)
        return InvocationGrant.model_validate(
            self._rpc(
                "POST",
                self._path(reference, "/grant"),
                {
                    "binding": request.binding.model_dump(mode="json"),
                    "capabilities": capabilities.model_dump(mode="json"),
                    "admission": admission.model_dump(mode="json"),
                },
            )
        )

    def observation(self, reference: EngineOperationReference) -> ControlDeliveryGrant:
        request = self.get_request(reference)
        actor, scopes = operation_actor_scope(self.configuration.identity)
        identifier = str(uuid4())
        budget = min(reference.control_budget_ms, self.configuration.rpc_budget_ms)
        control = BackendOperationControlModel(
            binding=request.binding,
            request_digest=reference.request_digest,
            control_id=identifier,
            actor_id=actor,
            authorization_scope=scopes,
            action="observe",
            budget={
                "origin_id": f"control:{identifier}",
                "started_at": datetime.now(UTC).isoformat(),
                "limit_ms": budget,
                "remaining_ms": budget,
            },
        )
        return ControlDeliveryGrant.model_validate(
            self._rpc("POST", self._path(reference, "/observations"), control.model_dump(mode="json"))
        )

    def get_control(self, reference: EngineOperationReference, control_id: str) -> ControlDeliveryGrant:
        return ControlDeliveryGrant.model_validate(
            self._rpc("POST", self._path(reference, "/controls/" + quote(control_id, safe="")))
        )

    def publish(self, reference: EngineOperationReference, response: BackendOperationResponseModel) -> str:
        return OperationStatusModel.model_validate(
            self._rpc("POST", self._path(reference, "/responses"), response.model_dump(mode="json"))
        ).state.value

    def indeterminate(self, reference: EngineOperationReference) -> str:
        request = self.get_request(reference)
        return OperationStatusModel.model_validate(
            self._rpc("POST", self._path(reference, "/indeterminate"), request.binding.model_dump(mode="json"))
        ).state.value

    def close(self, *, timeout_ms: int = 2000) -> bool:
        if not self._executor.drain(timeout_ms=timeout_ms):
            return False
        self._client.close()
        return self._executor.close(timeout_ms=timeout_ms)
