"""Current service authority for one remote invocation; engine tokens grant nothing."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic
from typing import Literal

from pydantic import ConfigDict
from raes_contracts.contracts import (
    BackendOperationBindingModel,
    BackendOperationCapabilitiesModel,
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    require_backend_execution_policy_admission,
)
from raes_contracts.contracts.backend_operation import OperationPositive
from raes_contracts.contracts.base import ContractModel
from raes_contracts.runtime_state import OperationState

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_actor_scope
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_supervised_execution import settle
from .control_plane_supervision import persist_invocation_update
from .operation_command_commitment import native_command_commitment
from .operation_control_budget import (
    ControlDeliveryGrant,
    admit_control_budget,
    forget_control_budget,
    remaining_control_budget,
)
from .operation_transcript_policy import append_control


class InvocationGrant(ContractModel):
    """Private owner RPC response. Only receipt of this live grant permits a call."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["raes-invocation-grant/v1"] = "raes-invocation-grant/v1"
    request: BackendOperationRequestModel
    remaining_budget_ms: OperationPositive


def authorize_worker(plane, identity, record=None, *, dispatch=False):
    configured = getattr(plane, "_distributed_execution", None)
    if (
        configured is None
        or not isinstance(identity, ControlPlaneIdentity)
        or ControlPlaneRole.BACKEND not in identity.roles
        or identity.target_name != plane._target.name
        or identity.identity != configured.worker_identity
    ):
        raise PermissionError("invocation service authority is forbidden")
    if record is not None:
        request = record.invocation.request if record.invocation is not None else None
        if (
            request is None
            or request.binding.worker_id != identity.identity
            or (request.binding.context.target_scope, request.binding.context.run_scope)
            != (plane._target_scope, plane._run_scope)
        ):
            raise PermissionError("invocation service authority is forbidden")
        if dispatch and (
            request.binding.owner_generation != plane._execution_generation
            or request.binding.deployment_id != plane._deployment_id
        ):
            raise ValueError("invocation owner generation is stale")


class RuntimeWorkerAuthorityMixin:
    @runtime_owned
    def _expire_backend_invocation(self, binding):
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            record = self._operations.get(binding.operation_id)
            if (
                record is not None
                and record.invocation.request.binding == binding
                and record.status.state
                in {
                    OperationState.ACCEPTED,
                    OperationState.RUNNING,
                }
            ):
                settle(
                    self,
                    record,
                    OperationState.INDETERMINATE if record.invocation.consumed else OperationState.CANCELLED,
                )

    @runtime_owned
    def get_backend_invocation(self, operation_id: str, *, identity) -> BackendOperationRequestModel:
        authorize_worker(self, identity)
        self._reload_derived_state()
        record = self._operations.get(operation_id)
        if record is None:
            raise KeyError("operation not found")
        authorize_worker(self, identity, record)
        return record.invocation.request

    @runtime_owned
    def claim_backend_invocation(
        self,
        binding: BackendOperationBindingModel,
        capabilities: BackendOperationCapabilitiesModel,
        admission: BackendOperationResponseModel,
        *,
        identity,
    ) -> InvocationGrant:
        binding = BackendOperationBindingModel.model_validate(binding.model_dump(mode="json"))
        capabilities = BackendOperationCapabilitiesModel.model_validate(capabilities.model_dump(mode="json"))
        admission = BackendOperationResponseModel.model_validate(admission.model_dump(mode="json"))
        authorize_worker(self, identity)
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            record = self._operations.get(binding.operation_id)
            if record is None:
                raise KeyError("operation not found")
            authorize_worker(self, identity, record, dispatch=True)
            if record.invocation.request.binding != binding:
                raise ValueError("invocation binding mismatch")
            if record.status.state is not OperationState.ACCEPTED or record.invocation.consumed:
                raise ValueError("invocation grant is unavailable or already consumed")
            if self._effect_admission_stopped or self._store.effect_admission_stopped():
                raise ValueError("effect admission is stopped")
            deadline = self._execution_deadlines.get(binding.operation_id)
            admitted = self._admitted_backend_requests.get(binding.operation_id)
            if deadline is None or admitted is None:
                raise ValueError("invocation clock or command continuity is unavailable")
            remaining = int((deadline - monotonic()) * 1000)
            if remaining <= 0:
                raise ValueError("invocation budget exhausted")
            native_request, _predecessor = admitted
            require_backend_execution_policy_admission(
                record.invocation.request,
                capabilities,
                admission,
                native_request.plan,
                resolved_native_plan_commitment=native_command_commitment(self, native_request.plan),
            )
            from .operation_provider_execution import accept_response

            record = accept_response(self, record, admission)
            running = replace(
                record,
                status=replace(record.status, state=OperationState.RUNNING, updated_at=_utc_now()),
                invocation=record.invocation.model_copy(update={"consumed": True}),
            )
            try:
                self._store.save_record(running)
            except BaseException:
                # This consumer received no grant. Uncertain commit facts must
                # remain unavailable, even if a later read discovers RUNNING.
                self._poison_runtime_durability()
                raise
            self._operations[binding.operation_id] = running
            remaining = int((deadline - monotonic()) * 1000)
            if remaining <= 0 or self._effect_admission_stopped:
                settle(self, running, OperationState.INDETERMINATE)
                raise ValueError("invocation budget or admission expired before grant delivery")
            return InvocationGrant(request=running.invocation.request, remaining_budget_ms=remaining)

    @runtime_owned
    def record_worker_observation(self, control: BackendOperationControlModel, *, identity):
        control = BackendOperationControlModel.model_validate(control.model_dump(mode="json"))
        authorize_worker(self, identity)
        actor, scopes = operation_actor_scope(identity)
        if control.action not in {"observe", "reconcile"} or (control.actor_id, control.authorization_scope) != (
            actor,
            scopes,
        ):
            raise PermissionError("worker observation authority is forbidden")
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            record = self._operations.get(control.binding.operation_id)
            if record is None:
                raise KeyError("operation not found")
            authorize_worker(self, identity, record)
            from raes_contracts.contracts import backend_operation_request_digest

            if (
                control.binding != record.invocation.request.binding
                or control.request_digest != backend_operation_request_digest(record.invocation.request)
            ):
                raise ValueError("worker observation binding mismatch")
            for prior in record.invocation.controls:
                if prior.control_id == control.control_id:
                    if prior != control:
                        raise ValueError("worker observation identity conflict")
                    raise ValueError("worker observation was already recorded")
            if control.budget.limit_ms > self._supervision.observation_ms:
                raise ValueError("worker observation budget is unsupported")
            invocation = append_control(record.invocation, control, automatic=True)
            admit_control_budget(self, control)
            try:
                persist_invocation_update(
                    self,
                    record,
                    invocation,
                    actor=actor,
                )
            except BaseException:
                forget_control_budget(self, control)
                raise
            return self.claim_worker_control(control.binding.operation_id, control.control_id, identity=identity)

    @runtime_owned
    def claim_worker_control(self, operation_id: str, control_id: str, *, identity):
        authorize_worker(self, identity)
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            record = self._operations.get(operation_id)
            if record is None:
                raise KeyError("operation not found")
            authorize_worker(self, identity, record)
            control = next((item for item in record.invocation.controls if item.control_id == control_id), None)
            if control is None:
                raise KeyError("control not found")
            if control_id in record.invocation.delivered_controls:
                raise ValueError("control delivery was already claimed")
            remaining_control_budget(self, control)
            persist_invocation_update(
                self,
                record,
                record.invocation.model_copy(
                    update={
                        "delivered_controls": (*record.invocation.delivered_controls, control_id),
                    }
                ),
                actor=control.actor_id,
            )
            grant = ControlDeliveryGrant(control=control, remaining_budget_ms=remaining_control_budget(self, control))
            forget_control_budget(self, control)
            return grant

    @runtime_owned
    def get_backend_operation_status(self, operation_id: str, *, identity):
        authorize_worker(self, identity)
        self._reload_derived_state()
        record = self._operations.get(operation_id)
        if record is None:
            raise KeyError("operation not found")
        authorize_worker(self, identity, record)
        return record.status

    @runtime_owned
    def publish_backend_response(self, response: BackendOperationResponseModel, *, identity):
        response = BackendOperationResponseModel.model_validate(response.model_dump(mode="json"))
        authorize_worker(self, identity)
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            record = self._operations.get(response.binding.operation_id)
            if record is None:
                raise KeyError("operation not found")
            authorize_worker(self, identity, record)
            from .operation_provider_execution import accept_response, validate_outcome

            control = next(
                (
                    item
                    for item in record.invocation.controls
                    if item.control_id == getattr(response.message, "control_id", None)
                ),
                None,
            )
            record = accept_response(self, record, response, control=control)
            if (
                response.message.kind == "acknowledgement"
                and response.message.disposition == "refused"
                and record.status.state is OperationState.RUNNING
            ):
                settle(self, record, OperationState.INDETERMINATE)
            if response.message.kind == "outcome" and record.status.state is OperationState.RUNNING:
                admitted = self._admitted_backend_requests.get(record.receipt.operation_id)
                if admitted is None:
                    settle(self, record, OperationState.INDETERMINATE)
                else:
                    native_request, predecessor = admitted
                    try:
                        result, release, payload = validate_outcome(self, record, response, native_request, predecessor)
                    except Exception:
                        settle(self, record, OperationState.INDETERMINATE)
                    else:
                        settle(
                            self,
                            record,
                            response.message.proposed_state,
                            result=result,
                            release_commitment=release,
                            result_payload=payload,
                        )
            return self._operations[record.receipt.operation_id].status

    @runtime_owned
    def mark_backend_indeterminate(self, binding: BackendOperationBindingModel, *, identity):
        authorize_worker(self, identity)
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            record = self._operations.get(binding.operation_id)
            if record is None or record.invocation.request.binding != binding:
                raise KeyError("operation not found")
            authorize_worker(self, identity, record)
            if record.status.state in {OperationState.ACCEPTED, OperationState.RUNNING}:
                settle(
                    self,
                    record,
                    OperationState.INDETERMINATE if record.invocation.consumed else OperationState.CANCELLED,
                )
            return self._operations[record.receipt.operation_id].status
