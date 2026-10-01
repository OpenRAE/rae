"""Optional one-invocation backend protocol; RAE retains scenario and state authority."""

from __future__ import annotations

from collections.abc import Iterable
from inspect import signature
from typing import Protocol, cast

from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
)
from raes_contracts.manifest_authority import validate_backend_supported_contract_versions
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS


class BackendOperationProvider(Protocol):
    """Bounded calls on separately provisioned effect/control capacity.

    All responses echo the exact invocation binding and request commitment.
    Callers authenticate and authorize separately, resolve the command and
    requirements through their owning authorities, and consume the current
    one-use invocation claim before start. No method schedules scenario work,
    allocates a trial/retry, publishes a snapshot or commits a terminal state.
    A caller timeout cannot establish that any remote effects have stopped.
    """

    def operation_capabilities(self) -> BackendOperationCapabilitiesModel:
        """Return the installed declaration; it supplies no contextual willingness."""
        ...

    def check_operation(self, request: BackendOperationRequestModel) -> BackendOperationResponseModel:
        """Return admission/refusal without effects; recheck immediately before dispatch."""
        ...

    def start_operation(self, request: BackendOperationRequestModel) -> BackendOperationResponseModel:
        """Return acknowledgement; duplicate identity never starts another effect.

        A refusal establishes that this invocation did not start. Once effects
        are possible, report uncertainty/outcome evidence through observation.
        """
        ...

    def observe_operation(self, request: BackendOperationControlModel) -> BackendOperationResponseModel:
        """Return one progress, outcome, reconciliation or control-disposition record.

        Reads are bounded and independently authorized. An observation with
        effects of its own requires separate effect admission, not this method.
        """
        ...

    def cancel_operation(self, request: BackendOperationControlModel) -> BackendOperationResponseModel:
        """Return control disposition; acceptance is not cessation or rollback."""
        ...

    def reconcile_operation(self, request: BackendOperationControlModel) -> BackendOperationResponseModel:
        """Return read-only reconciliation evidence or an explicit control refusal."""
        ...


def require_operation_provider(provider: object, declared_contracts: Iterable[str]) -> BackendOperationProvider:
    """Validate opt-in declaration and installed call shapes without invoking code.

    This public protocol boundary cannot import the runtime's private registry
    checker. It provides the same signature binding for independent embedders;
    behavioral conformance and contextual admission remain separate checks.
    """

    declared = tuple(declared_contracts)
    validate_backend_supported_contract_versions(declared)
    if not set(BACKEND_OPERATION_CONTRACT_IDS) <= set(declared):
        raise ValueError("backend operation contracts are not declared")
    for name in (
        "operation_capabilities",
        "check_operation",
        "start_operation",
        "observe_operation",
        "cancel_operation",
        "reconcile_operation",
    ):
        method = getattr(provider, name, None)
        if not callable(method):
            raise ValueError("backend operation protocol is not installed")
        try:
            signature(method).bind(*(() if name == "operation_capabilities" else (object(),)))
        except (TypeError, ValueError):
            raise ValueError("installed backend operation method has incompatible call shape") from None
    return cast(BackendOperationProvider, provider)


__all__ = ["BackendOperationProvider", "require_operation_provider"]
