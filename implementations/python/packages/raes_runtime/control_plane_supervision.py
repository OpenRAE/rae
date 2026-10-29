"""Independently authorized supervision at the existing scoped state writer."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from raes_contracts.contracts import BackendOperationControlModel, backend_operation_request_digest
from raes_contracts.runtime_state import OperationState

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_actor_scope
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .control_plane_store_bounded import bounded_store_commit
from .operation_control_budget import admit_control_budget, forget_control_budget, remaining_control_budget
from .operation_transcript_policy import append_control
from .runtime_operation_routing import run_operation

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationResponseModel

    from .control_plane import RuntimeControlPlane
    from .operation_invocation_ledger import InvocationLedger


_OPERATION_NOT_FOUND = "operation not found"


def authorize_supervisor(
    plane: RuntimeControlPlane, identity: ControlPlaneIdentity | None, parent: ControlPlaneOperationRecord | None = None
) -> None:
    if identity is None:
        # P0/P1's existing trusted-embedder boundary.
        return
    allowed = (
        isinstance(identity, ControlPlaneIdentity)
        and ControlPlaneRole.OPERATOR in identity.roles
        and identity.target_name == plane._target.name
    )
    if parent is not None:
        _, scopes = operation_actor_scope(identity)
        subjects = {
            scope for scope in parent.status.context.authorization_scope if scope.startswith("participant-control:")
        }
        allowed = (
            allowed
            and subjects <= set(scopes)
            and (parent.status.context.target_scope, parent.status.context.run_scope)
            == (plane._target_scope, plane._run_scope)
        )
    if not allowed:
        raise PermissionError("supervision is forbidden")


@bounded_store_commit
def persist_invocation_update(
    plane: RuntimeControlPlane,
    expected: ControlPlaneOperationRecord,
    invocation: InvocationLedger,
    *,
    actor: str | None = None,
) -> ControlPlaneOperationRecord:
    record = cast(ControlPlaneOperationRecord, replace(expected, invocation=invocation))
    event = AuditEvent(
        timestamp=_utc_now(),
        action="operation_supervision",
        identity=actor or expected.status.context.actor_id,
        allowed=True,
        target=expected.status.context.target_scope,
        operation_id=expected.receipt.operation_id,
        details={"count": 1},
    )
    try:
        committed = plane._store.commit_invocation_transition(expected, record, audit_event=event)
    except BaseException as error:
        plane._resynchronize_after_store_error(
            error,
            operation_id=record.receipt.operation_id,
            expected_audit=event,
            require_terminal_cut=False,
        )
        raise
    plane._publish_committed_state(committed)
    return record


class RuntimeSupervisionMixin:
    @runtime_owned
    def stop_admission(self, *, identity: ControlPlaneIdentity | None = None) -> None:
        authorize_supervisor(self, identity)
        actor, _ = operation_actor_scope(identity)
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._store.stop_effect_admission(
                AuditEvent(
                    timestamp=_utc_now(),
                    action="stop_effect_admission",
                    identity=actor,
                    allowed=True,
                    target=self._target_scope,
                )
            )
            self._effect_admission_stopped = True

    @run_operation
    @runtime_owned
    def cancel_operation(
        self, operation_id: str, *, control_id: str, identity: ControlPlaneIdentity | None = None
    ) -> BackendOperationControlModel:
        return self.supervise_operation(operation_id, action="cancel", control_id=control_id, identity=identity)

    @run_operation
    @runtime_owned
    def supervise_operation(
        self,
        operation_id: str,
        *,
        action: str,
        control_id: str,
        identity: ControlPlaneIdentity | None = None,
        _automatic_observation: bool = False,
    ) -> BackendOperationControlModel:
        if _automatic_observation and (identity is not None or action != "observe"):
            raise PermissionError("automatic observation requires core authority")
        authorize_supervisor(self, identity)
        actor, scopes = operation_actor_scope(identity)
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            parent = self._operations.get(operation_id)
            if parent is None:
                raise KeyError(_OPERATION_NOT_FOUND)
            authorize_supervisor(self, identity, parent)
            if parent.invocation is None:
                raise ValueError("historical operation has no supervised invocation binding")
            for existing in parent.invocation.controls:
                if existing.control_id == control_id:
                    if (existing.actor_id, existing.authorization_scope, existing.action) != (actor, scopes, action):
                        raise ValueError("control identity conflict")
                    return existing
            control = BackendOperationControlModel(
                binding=parent.invocation.request.binding,
                request_digest=backend_operation_request_digest(parent.invocation.request),
                control_id=control_id,
                actor_id=actor,
                authorization_scope=scopes,
                action=action,
                budget={
                    "origin_id": f"control:{uuid4()}",
                    "started_at": _utc_now(),
                    "limit_ms": self._supervision.observation_ms,
                    "remaining_ms": self._supervision.observation_ms,
                },
            )
            return self._record_supervisor_control(parent, control, automatic=_automatic_observation)

    @runtime_owned
    def submit_operation_control(
        self, control: BackendOperationControlModel, *, identity: ControlPlaneIdentity | None = None
    ) -> BackendOperationControlModel:
        control = BackendOperationControlModel.model_validate(control.model_dump(mode="json"))
        authorize_supervisor(self, identity)
        if (control.actor_id, control.authorization_scope) != operation_actor_scope(identity):
            raise PermissionError("control actor is forbidden")
        with self._mutation_authority.supervision():
            self._assert_runtime_owner()
            self._reload_derived_state()
            parent = self._operations.get(control.binding.operation_id)
            if parent is None or parent.invocation is None:
                raise KeyError(_OPERATION_NOT_FOUND)
            authorize_supervisor(self, identity, parent)
            if (
                control.binding != parent.invocation.request.binding
                or control.request_digest != backend_operation_request_digest(parent.invocation.request)
            ):
                raise ValueError("control binding mismatch")
            for existing in parent.invocation.controls:
                if existing.control_id == control.control_id:
                    if existing != control:
                        raise ValueError("control identity conflict")
                    return existing
            if control.budget.limit_ms > self._supervision.observation_ms:
                raise ValueError("control budget is unsupported")
            return self._record_supervisor_control(parent, control)

    def _record_supervisor_control(
        self, parent: ControlPlaneOperationRecord, control: BackendOperationControlModel, *, automatic: bool = False
    ) -> BackendOperationControlModel:
        actor, action = control.actor_id, control.action
        invocation = append_control(parent.invocation, control, automatic=automatic)
        admit_control_budget(self, control)
        try:
            parent = persist_invocation_update(
                self,
                parent,
                invocation,
                actor=actor,
            )
        except BaseException:
            forget_control_budget(self, control)
            raise
        if action == "cancel" and parent.status.state is OperationState.ACCEPTED and not parent.invocation.consumed:
            from .control_plane_supervised_execution import settle

            settle(self, parent, OperationState.CANCELLED)
        # Native providers expose no interruption guarantee. This receipt
        # records intent only; an executing native call remains uncertain.
        if not parent.invocation.native and parent.invocation.consumed and parent.invocation.reserved:
            if self._distributed_execution is None:
                from .operation_provider_control import deliver_control

                deliver_control(self, parent, control)
            else:
                with self._mutation_authority.external_call():
                    self._execution_adapter.call(
                        "control",
                        self._distributed_execution.deliver_control,
                        parent.invocation.request,
                        control,
                        timeout_ms=min(remaining_control_budget(self, control), self._supervision.observation_ms),
                    )
        return control

    @run_operation
    @runtime_owned
    def get_control_response(
        self, operation_id: str, control_id: str, *, identity: ControlPlaneIdentity | None = None
    ) -> BackendOperationResponseModel | None:
        authorize_supervisor(self, identity)
        with self._operation_lock:
            self._reload_derived_state()
            parent = self._operations.get(operation_id)
        if parent is None or parent.invocation is None:
            raise KeyError(_OPERATION_NOT_FOUND)
        authorize_supervisor(self, identity, parent)
        for response in reversed(parent.invocation.responses):
            if getattr(response.message, "control_id", None) == control_id:
                return response
        return None


__all__ = ("RuntimeSupervisionMixin", "authorize_supervisor", "persist_invocation_update")
