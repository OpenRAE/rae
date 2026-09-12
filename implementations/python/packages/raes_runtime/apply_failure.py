"""Apply failure synthesis and service rollback operations."""

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_calls import _call_backend_apply, _RealizationApplyContext
from .diagnostics import _failure_diagnostic, _has_error_diagnostic


def maybe_synthesize_failure(
    diagnostics: list[Diagnostic],
    *,
    result: ApplyResult,
    code: str,
    address: str,
    message: str,
) -> None:
    """Add a portable failure when a backend omitted an error diagnostic."""

    if not result.success and not _has_error_diagnostic(result.diagnostics):
        diagnostics.append(_failure_diagnostic(code, address, message))


def rollback_services(
    snapshot: RuntimeSnapshot,
    services: list[tuple[str, object, RuntimeDomain]],
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> ApplyResult:
    """Stop started services in order and preserve every rollback diagnostic."""

    working_snapshot = snapshot
    diagnostics: list[Diagnostic] = []
    changed_addresses: list[str] = []
    success = True
    for address, service, domain in services:
        stop_result = _call_backend_apply(
            service.stop,
            working_snapshot,
            address=address,
            snapshot=working_snapshot,
            realization=_RealizationApplyContext(stop_domain=domain),
            information_state_context_resolver=information_state_context_resolver,
        )
        diagnostics.extend(stop_result.diagnostics)
        changed_addresses.extend(stop_result.changed_addresses)
        working_snapshot = stop_result.snapshot
        if not stop_result.success:
            success = False
            maybe_synthesize_failure(
                diagnostics,
                result=stop_result,
                code="runtime.apply-rollback-failed",
                address=address,
                message=f"Rollback failed while stopping '{address}'.",
            )
    return ApplyResult(
        success=success,
        snapshot=working_snapshot,
        diagnostics=diagnostics,
        changed_addresses=changed_addresses,
    )


__all__ = ["maybe_synthesize_failure", "rollback_services"]
