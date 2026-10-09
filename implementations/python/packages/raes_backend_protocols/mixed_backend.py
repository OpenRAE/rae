"""Optional mixed-backend bridge, time-coordinator and stage-reader protocols.

RAE retains admission, authored order, terminal publication and recovery.
These protocols let an installed service report correlated stage evidence for
one admitted edge or native handoff through the shared backend operation
protocol. Method presence never establishes capability, conformance or
authority, and declaring the contracts is not effective support.
"""

from __future__ import annotations

from collections.abc import Iterable
from inspect import signature
from typing import Literal, Protocol

from raes_contracts.contracts import (
    BackendOperationControlModel,
    BackendOperationRequestModel,
    MixedBackendExecutionBindingModel,
    MixedBackendStageReportModel,
)
from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.manifest_authority import validate_backend_supported_contract_versions
from raes_contracts.versions import MIXED_BACKEND_CONTRACT_IDS

from .operation_supervision import BackendOperationProvider, require_operation_provider

MixedBackendServiceRole = Literal["bridge", "coordinator", "reader"]


class MixedBackendBridge(BackendOperationProvider, Protocol):
    """Installed edge bridge or native transfer service for exactly one admitted binding.

    The shared operation methods admit, start, observe, cancel and reconcile one
    invocation whose request commits to :meth:`execution_binding`. Starting
    invokes the destination provider at most once, and a duplicate identity
    starts nothing. Stage reports are evidence proposals: a reader must validate
    them, and only RAE may commit the operation, composition history and
    terminal state.
    """

    def execution_binding(self) -> MixedBackendExecutionBindingModel:
        """Return the installed binding declaration; it supplies no contextual willingness."""
        ...

    def stage_reports(self, control: BackendOperationControlModel) -> tuple[MixedBackendStageReportModel, ...]:
        """Return bounded execution or handoff stage reports for an independently authorized read."""
        ...


class MixedTimeCoordinator(Protocol):
    """Grant a governed order over the bound clocks before an invocation starts."""

    def grant(
        self,
        request: BackendOperationRequestModel,
        time_state: TimeRuntimeStateModel,
    ) -> MixedBackendStageReportModel:
        """Return one time-grant report at the coordinates of ``time_state``; it advances no clock."""
        ...


class MixedStageReader(Protocol):
    """Read back destination delivery, participant observation or native owner state."""

    def read_stage(self, control: BackendOperationControlModel) -> MixedBackendStageReportModel:
        """Return one stage report that names this reader as its producer; the read has no effects."""
        ...


_ROLE_METHODS = {
    "bridge": (("execution_binding", 0), ("stage_reports", 1)),
    "coordinator": (("grant", 2),),
    "reader": (("read_stage", 1),),
}


def require_mixed_backend_service(
    service: object,
    role: MixedBackendServiceRole,
    declared_contracts: Iterable[str],
) -> None:
    """Validate the opt-in declaration and installed call shapes without invoking code.

    A bridge must also install the shared operation protocol. Behavioral
    conformance, the trusted profile join and contextual admission remain
    separate checks.
    """

    declared = tuple(declared_contracts)
    validate_backend_supported_contract_versions(declared)
    if not set(MIXED_BACKEND_CONTRACT_IDS) <= set(declared):
        raise ValueError("mixed backend contracts are not declared")
    if role == "bridge":
        require_operation_provider(service, declared)
    for name, arity in _ROLE_METHODS[role]:
        method = getattr(service, name, None)
        if not callable(method):
            raise ValueError("mixed backend service protocol is not installed")
        try:
            signature(method).bind(*(object(),) * arity)
        except (TypeError, ValueError):
            raise ValueError("installed mixed backend method has incompatible call shape") from None


__all__ = [
    "MixedBackendBridge",
    "MixedBackendServiceRole",
    "MixedStageReader",
    "MixedTimeCoordinator",
    "require_mixed_backend_service",
]
