"""Destroy-phase helpers for the runtime manager's teardown sequence."""

from __future__ import annotations

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.planner import snapshot_delete_order

from .backend_calls import _BackendCallContext, _call_backend_apply
from .backend_realization_authority import _RealizationApplyContext


class _DestroyPhaseMixin:
    """Teardown steps the runtime manager performs before deleting resources."""

    def _clock_driver_stop_refusal(self) -> ApplyResult | None:
        """Refuse destroy while the participant clock driver is still active."""

        if self._stop_participant_clock_driver():
            return None
        return ApplyResult(
            success=False,
            snapshot=self._snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-clock-driver-stop-timeout",
                    domain="participant",
                    address="runtime.destroy",
                    message="Destroy did not start because the participant clock driver is still active.",
                )
            ],
        )

    def _stop_service_phase(
        self,
        service: object | None,
        snapshot: RuntimeSnapshot,
        *,
        address: str,
        domain: RuntimeDomain,
    ) -> ApplyResult | None:
        """Stop one destroy-phase service, or return None when it is not configured."""

        if service is None:
            return None
        return _call_backend_apply(
            service.stop,
            snapshot,
            address=address,
            snapshot=snapshot,
            realization=_RealizationApplyContext(stop_domain=domain),
            call=_BackendCallContext(
                information_state_context_resolver=self._information_state_context_resolver,
            ),
        )

    def _destroy_delete_plan(self, snapshot: RuntimeSnapshot) -> ProvisioningPlan:
        """Build the plan that deletes every live provisioning entry in order."""

        entries = snapshot.for_domain(RuntimeDomain.PROVISIONING)
        return ProvisioningPlan(
            resources={},
            operations=[
                ProvisionOp(
                    action=ChangeAction.DELETE,
                    address=address,
                    resource_type=entries[address].resource_type,
                    payload=entries[address].payload,
                    ordering_dependencies=entries[address].ordering_dependencies,
                    refresh_dependencies=entries[address].refresh_dependencies,
                )
                for address in snapshot_delete_order(entries)
            ],
            realization_envelope=snapshot.realization_envelope,
        )
