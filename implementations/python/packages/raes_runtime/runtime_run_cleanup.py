"""Durable teardown uses the same native stop and delete boundaries as destroy."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from raes_contracts.planning import RuntimeDomain

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .runtime_module_step import advance_step

if TYPE_CHECKING:
    from raes_contracts.runtime_state import ApplyResult

    from .runtime_run_context import RuntimeRunContext


def advance_destroy(run: RuntimeRunContext, execution_id: str, identity: object | None) -> str:
    if run._clock_driver_stop_refusal() is not None:
        return "indeterminate"
    for phase, domain in enumerate((RuntimeDomain.ORCHESTRATION, RuntimeDomain.EVALUATION, RuntimeDomain.PROVISIONING)):
        dispatch = partial(_dispatch_destroy, run, domain, identity=identity)
        state = advance_step(run, execution_id=execution_id, phase=phase, dispatch=dispatch)
        if state != "succeeded":
            return state
    return "succeeded"


def _dispatch_destroy(
    run: RuntimeRunContext, domain: RuntimeDomain, key: str, *, identity: object | None
) -> ApplyResult | None:
    snapshot = run.snapshot
    if domain is RuntimeDomain.PROVISIONING:
        method = run._target.provisioner.apply
        args = (run._destroy_delete_plan(snapshot), snapshot)
        realization = _RealizationApplyContext()
    else:
        service = run._target.orchestrator if domain is RuntimeDomain.ORCHESTRATION else run._target.evaluator
        if service is None:
            return None
        method, args = service.stop, (snapshot,)
        realization = _RealizationApplyContext(stop_domain=domain)
    return run._interaction_backend_call(
        method,
        *args,
        address=f"runtime.destroy.{domain.value}",
        snapshot=snapshot,
        realization=realization,
        idempotency_key=key,
        identity=identity,
        call=_BackendCallContext(information_state_context_resolver=run._information_state_context_resolver),
    )
