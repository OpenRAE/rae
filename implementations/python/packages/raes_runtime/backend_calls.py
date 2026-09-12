from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, is_dataclass

from pydantic import BaseModel
from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_account_credentials import (
    plan_arguments_have_account_credentials,
    value_free_backend_diagnostics,
)
from .backend_apply_results import _finalize_backend_apply
from .backend_call_contracts import (
    _materialize_diagnostics,
)
from .backend_input_contracts import backend_input_violation
from .backend_preparation import prepare_backend_invocation
from .backend_realization_authority import (
    _apply_authority_diagnostics,
    _bind_submitted_plan,
    _RealizationApplyContext,
)
from .backend_result_diagnostics import (
    _backend_call_failed,
    _backend_contract_invalid,
    _failed_apply_result,
)


@dataclass(frozen=True)
class _BackendCallContext:
    """Per-invocation identity and host services one backend apply may receive."""

    operation_id: str | None = None
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None
    service_dependencies: tuple[object, ...] = ()


def _call_backend_diagnostics(
    method: Callable[..., object],
    *args: object,
    address: str,
) -> list[Diagnostic]:
    if invalid := backend_input_violation(args):
        return [_backend_contract_invalid(address, invalid)]
    try:
        result = method(*(_isolated_argument(argument) for argument in args))
    except Exception as exc:
        diagnostics = [_backend_call_failed(address, exc)]
    else:
        diagnostics, invalid_message = _materialize_diagnostics(result, address)
        if invalid_message is not None:
            diagnostics = [_backend_contract_invalid(address, invalid_message)]
    if plan_arguments_have_account_credentials(args):
        diagnostics = value_free_backend_diagnostics(diagnostics)
    return diagnostics


def _prepared_backend_result(
    method: Callable[..., object],
    args: tuple[object, ...],
    *,
    address: str,
    snapshot: RuntimeSnapshot,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    call: _BackendCallContext,
) -> ApplyResult:
    """Prepare the invocation, invoke it, and retain the preparation diagnostics."""

    args, realization, diagnostics = prepare_backend_invocation(method, args, baseline_snapshot, realization)
    if args is None:
        return ApplyResult(False, baseline_snapshot, diagnostics=diagnostics)
    result = _invoke_backend_apply(
        method,
        args,
        address=address,
        snapshot=snapshot,
        baseline_snapshot=baseline_snapshot,
        realization=deepcopy(realization),
        call=call,
    )
    result.diagnostics = [*diagnostics, *result.diagnostics]
    return result


def _call_backend_apply(
    method: Callable[..., object],
    *args: object,
    address: str,
    snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext | None = None,
    call: _BackendCallContext | None = None,
) -> ApplyResult:
    realization_context = realization or _RealizationApplyContext()
    call_context = call or _BackendCallContext()
    invalid = backend_input_violation(
        (*args, snapshot), authority=realization_context, service_dependencies=call_context.service_dependencies
    )
    if invalid:
        return _failed_apply_result(snapshot, _backend_contract_invalid(address, invalid))
    args, realization_context = _bind_submitted_plan(args, realization_context, call_context.operation_id)
    baseline_snapshot = deepcopy(snapshot)
    authority_diagnostics = _apply_authority_diagnostics(realization_context, address)
    if authority_diagnostics:
        return ApplyResult(success=False, snapshot=baseline_snapshot, diagnostics=authority_diagnostics)
    return _prepared_backend_result(
        method,
        args,
        address=address,
        snapshot=snapshot,
        baseline_snapshot=baseline_snapshot,
        realization=realization_context,
        call=call_context,
    )


def _invoke_backend_apply(
    method: Callable[..., object],
    args: tuple[object, ...],
    *,
    address: str,
    snapshot: RuntimeSnapshot,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    call: _BackendCallContext,
) -> ApplyResult:
    backend_snapshot = deepcopy(snapshot)
    backend_args = tuple(
        backend_snapshot if arg is snapshot else _isolated_argument(arg, call.service_dependencies) for arg in args
    )
    try:
        result = method(*backend_args)
    except (TypeError, ValueError):
        return _failed_apply_result(
            baseline_snapshot,
            _backend_contract_invalid(address, "Backend could not construct a valid apply result."),
        )
    except Exception as exc:
        return _failed_apply_result(baseline_snapshot, _backend_call_failed(address, exc))
    return _validated_backend_result(
        result,
        address=address,
        baseline_snapshot=baseline_snapshot,
        realization=realization,
        call=call,
    )


def _validated_backend_result(
    result: object,
    *,
    address: str,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    call: _BackendCallContext,
) -> ApplyResult:
    """Finalize a backend result, refusing anything that cannot be validated."""

    try:
        return _finalize_backend_apply(
            result,
            address=address,
            baseline_snapshot=baseline_snapshot,
            realization=realization,
            information_state_context_resolver=call.information_state_context_resolver,
        )
    except Exception:
        return _failed_apply_result(
            baseline_snapshot,
            _backend_contract_invalid(address, "Backend returned an apply result that could not be validated."),
        )


def _isolated_argument(argument: object, service_dependencies: tuple[object, ...] = ()) -> object:
    """Isolate value carriers, retaining injected service dependency identity."""

    if any(argument is service for service in service_dependencies):
        return argument
    if is_dataclass(argument) or isinstance(argument, (BaseModel, dict, list, tuple)):
        return deepcopy(argument)
    return argument
