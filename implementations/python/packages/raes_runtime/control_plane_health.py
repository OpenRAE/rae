"""Value-free liveness and readiness projection for the control plane."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from raes_contracts.errors import RaesError
from raes_contracts.operational_logging import get_logger

from .control_plane_recovery import unresolved_indeterminate_operation_ids_from_records
from .control_plane_store import RuntimeAdmittedControlPlaneStore

_LOGGER = get_logger(__name__)


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
        requires_lease = isinstance(getattr(store, "raw_store", store), RuntimeAdmittedControlPlaneStore)

        with control_plane._operation_lock:
            records = dict(control_plane._operations)
        if unresolved_indeterminate_operation_ids_from_records(
            records,
            target_scope=control_plane._target_scope,
            run_scope=control_plane._run_scope,
        ):
            reasons.append("recovery-required")

    if requires_lease and not _lease_available(control_plane, lease):
        reasons.append("lease-unavailable")
    if getattr(control_plane, "_effect_admission_stopped", False):
        reasons.append("effect-admission-stopped")
    deduplicated = tuple(dict.fromkeys(reasons))
    status = ControlPlaneHealthStatus.READY if not deduplicated else ControlPlaneHealthStatus.UNREADY
    return ControlPlaneHealth(status=status, reasons=deduplicated)


def _lease_available(control_plane: object, lease: object | None) -> bool:
    """Confirm the runtime lease; a probe reports any failure as unready."""

    if lease is None:
        return False
    try:
        control_plane._assert_runtime_owner()
    except RaesError:
        # A closed runtime, a lost lease or an exhausted check budget is an expected unready state.
        return False
    except Exception:
        # Isolation of the store lease check: readiness reports it without failing the probe.
        _LOGGER.exception("control-plane readiness could not confirm the runtime lease")
        return False
    return True


__all__ = (
    "ControlPlaneHealth",
    "ControlPlaneHealthStatus",
    "control_plane_liveness",
    "control_plane_readiness",
)
