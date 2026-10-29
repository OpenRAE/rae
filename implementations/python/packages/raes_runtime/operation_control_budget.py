"""One control allowance; wire commitments never become renewed dispatch time."""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Literal

from pydantic import ConfigDict
from raes_contracts.contracts import BackendOperationControlModel
from raes_contracts.contracts.backend_operation import OperationPositive
from raes_contracts.contracts.base import ContractModel
from raes_contracts.errors import ConflictError, InvalidInputError

from .errors import RuntimeBudgetExhaustedError

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane


class ControlDeliveryGrant(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["raes-control-grant/v1"] = "raes-control-grant/v1"
    control: BackendOperationControlModel
    remaining_budget_ms: OperationPositive


def control_key(control: BackendOperationControlModel) -> tuple[str, str]:
    return control.binding.operation_id, control.control_id


def admit_control_budget(plane: RuntimeControlPlane, control: BackendOperationControlModel) -> None:
    now = monotonic()
    plane._control_deadlines = {key: deadline for key, deadline in plane._control_deadlines.items() if deadline > now}
    if control_key(control) in plane._control_deadlines:
        raise ConflictError("control budget cannot be renewed")
    if len(plane._control_deadlines) >= 256:
        raise ConflictError("control clock capacity unavailable")
    try:
        started = datetime.fromisoformat(control.budget.started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        # The control contract also admits a lowercase "z" and a leap second, which this clock does not read.
        raise InvalidInputError("control budget start time is unsupported") from exc
    elapsed = (datetime.now(UTC) - started).total_seconds()
    if elapsed < 0:
        raise ConflictError("control clock continuity is unavailable")
    remaining = min(control.budget.remaining_ms, control.budget.limit_ms - ceil(elapsed * 1000))
    if remaining <= 0:
        raise RuntimeBudgetExhaustedError("control budget exhausted before admission")
    plane._control_deadlines[control_key(control)] = now + remaining / 1000


def remaining_control_budget(plane: RuntimeControlPlane, control: BackendOperationControlModel) -> int:
    deadline = plane._control_deadlines.get(control_key(control))
    if deadline is None:
        raise ConflictError("control clock continuity is unavailable")
    remaining = int((deadline - monotonic()) * 1000)
    if remaining <= 0:
        raise RuntimeBudgetExhaustedError("control delivery budget exhausted")
    return remaining


def forget_control_budget(plane: RuntimeControlPlane, control: BackendOperationControlModel) -> None:
    plane._control_deadlines.pop(control_key(control), None)
