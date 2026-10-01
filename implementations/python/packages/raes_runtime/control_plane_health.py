"""Value-free liveness and readiness projection for the control plane."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .control_plane_recovery import unresolved_indeterminate_operation_ids_from_records
from .control_plane_store import RuntimeAdmittedControlPlaneStore


class ControlPlaneHealthStatus(str, Enum):
    """Closed status vocabulary for public health probes."""

    LIVE = "live"
    READY = "ready"
    UNREADY = "unready"


@dataclass(frozen=True)
class ControlPlaneHealth:
    """Bounded health result containing no runtime or operator values."""

    status: ControlPlaneHealthStatus
    reasons: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {"status": self.status.value, "reasons": list(self.reasons)}


def control_plane_liveness() -> ControlPlaneHealth:
    """Report only that the health handler can respond."""

    return ControlPlaneHealth(ControlPlaneHealthStatus.LIVE)


def control_plane_readiness(control_plane: object) -> ControlPlaneHealth:
    """Project readiness from existing lifecycle and recovery state."""

    reasons: list[str] = []
    condition = control_plane._lifecycle_condition
    with condition:
        if not control_plane._runtime_ready:
            reasons.append("startup-incomplete")
        if control_plane._durability_poisoned:
            reasons.append("durability-poisoned")
        if control_plane._closing:
            reasons.append("draining")
        if control_plane._closed:
            reasons.append("closed")
        store = control_plane._store
        lease = control_plane._runtime_lease
        if isinstance(store, RuntimeAdmittedControlPlaneStore):
            try:
                if lease is None:
                    raise RuntimeError
                lease.assert_owner()
            except Exception:
                reasons.append("lease-unavailable")

        with control_plane._operation_lock:
            records = dict(control_plane._operations)
        if unresolved_indeterminate_operation_ids_from_records(
            records,
            target_scope=control_plane._target_scope,
            run_scope=control_plane._run_scope,
        ):
            reasons.append("recovery-required")

        deduplicated = tuple(dict.fromkeys(reasons))
        status = ControlPlaneHealthStatus.READY if not deduplicated else ControlPlaneHealthStatus.UNREADY
        return ControlPlaneHealth(status=status, reasons=deduplicated)


__all__ = (
    "ControlPlaneHealth",
    "ControlPlaneHealthStatus",
    "control_plane_liveness",
    "control_plane_readiness",
)
