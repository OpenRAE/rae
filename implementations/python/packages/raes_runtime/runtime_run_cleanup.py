"""Durable teardown uses the same native stop and delete boundaries as destroy."""

from raes_contracts.planning import RuntimeDomain

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .runtime_module_step import advance_step


def advance_destroy(run, execution_id, identity):
    if run._clock_driver_stop_refusal() is not None:
        return "indeterminate"
    for phase, domain in enumerate((RuntimeDomain.ORCHESTRATION, RuntimeDomain.EVALUATION, RuntimeDomain.PROVISIONING)):

        def dispatch(key, domain=domain):
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

        state = advance_step(run, execution_id=execution_id, phase=phase, dispatch=dispatch)
        if state != "succeeded":
            return state
    return "succeeded"
