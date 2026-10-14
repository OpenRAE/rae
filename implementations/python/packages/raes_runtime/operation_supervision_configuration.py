"""Apparatus bounds, independent of authored scenario time and retry policy."""

from dataclasses import dataclass, fields
from typing import Protocol

from raes_contracts.contracts import BackendOperationRequestModel, BackendOperationResponseModel
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .operation_execution_adapter import require_budget_ms


class OperationEvidenceResolver(Protocol):
    """A trusted, scoped artifact boundary; backend assertions are not proofs.

    The embedder authenticates and resolves the content-bound evidence under
    its owning native contracts. The runtime still validates the result and
    request bindings against its isolated admitted predecessor.
    """

    def validate_effects(
        self, request: BackendOperationRequestModel, response: BackendOperationResponseModel
    ) -> bool: ...

    def resolve_result(
        self,
        request: BackendOperationRequestModel,
        response: BackendOperationResponseModel,
        predecessor: RuntimeSnapshot,
    ) -> ApplyResult: ...


@dataclass(frozen=True, kw_only=True)
class OperationSupervisionConfiguration:
    admission_ms: int = 2000
    execution_ms: int = 30000
    observation_ms: int = 2000
    commit_ms: int = 2000
    drain_ms: int = 2000
    effect_capacity: int = 1
    control_capacity: int = 2
    store_capacity: int = 4

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name.endswith("_ms"):
                require_budget_ms(value)
            elif type(value) is not int or not 1 <= value <= 64:
                raise ValueError("execution capacity must be a strict integer between 1 and 64")
