"""Opt-in backend-owned joint selection, separate from mutation and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_core import to_jsonable_python

from raes_contracts.contracts.plan_projection import runtime_plan_digest

from ..canonical import canonical_json_digest, jsonable_fallback
from ..diagnostics import Diagnostic
from ..realization_structure import validate_realization_value
from ..runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

if TYPE_CHECKING:
    from ..planning import ProvisioningPlan, ProvisionOp
    from ..runtime_state import RuntimeSnapshot


def preparation_snapshot_digest(snapshot: RuntimeSnapshot) -> str:
    """Bind the immediate portable predecessor, not a backend mutable alias."""

    if not validate_realization_value(snapshot, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("preparation predecessor exceeds the admitted portable bounds")
    payload = to_jsonable_python(snapshot, fallback=jsonable_fallback)
    if not validate_realization_value(payload, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
        raise ValueError("preparation predecessor exceeds the admitted portable bounds")
    return canonical_json_digest(payload)


@dataclass(frozen=True)
class RealizationPreparation:
    """One backend-supported joint completion; never an observation of delivery."""

    request_digest: str
    predecessor_digest: str
    operations: tuple[ProvisionOp, ...]
    success: bool = True
    diagnostics: tuple[Diagnostic, ...] = ()

    @classmethod
    def for_request(
        cls,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
        *,
        operations: tuple[ProvisionOp, ...],
        success: bool = True,
        diagnostics: tuple[Diagnostic, ...] = (),
    ) -> RealizationPreparation:
        return cls(runtime_plan_digest(plan), preparation_snapshot_digest(snapshot), operations, success, diagnostics)


__all__ = [
    "RealizationPreparation",
    "preparation_snapshot_digest",
]
