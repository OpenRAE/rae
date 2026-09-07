"""Native/guest realization subsystem for the libvirt scenario-evidence producer.

Only the ``native-live`` / ``guest-certified`` evidence-source modes exercise this
module: it realizes the bounded VM/network substrate through the native libvirt
driver, captures the challenge-bound guest report (guest-certified only), and
verifies teardown/residue on every path. Split from ``libvirt_evidence_run`` to keep
each module under the ADR-015 source-size cap; the producer calls
``_default_native_driver_factory`` and ``_run_native_mode`` from here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from raes_backend_libvirt.techvault_native import TechVaultNativeLibvirtDriver
from raes_contracts.runtime_state import OperationStatus
from raes_runtime.control_plane import RuntimeControlPlane

from raes_operations._evidence_run_types import EvidenceCheck, ExecutionPlan, LibvirtEvidenceRunConfig
from raes_operations._techvault_cleanup import cleanup_native_snapshot


def _run_native_mode(
    mode: str,
    execution_plan: ExecutionPlan,
    control_plane: RuntimeControlPlane,
    native_driver: TechVaultNativeLibvirtDriver,
    driver_factory: Callable[[], TechVaultNativeLibvirtDriver] | None,
    checks: list[EvidenceCheck],
) -> tuple[Mapping[str, Any] | None, bool | None, tuple[str, ...], Mapping[str, Any] | None]:
    """Realize the native substrate, capture any guest report, and clean up in a finally-path.

    Native-proof boundary: only the default production driver/transport (no injected
    factory) yields a certifying guest artifact; injected fakes are marked
    non-certifying so their evidence can never be published as a real certification.
    """
    native_snapshot: Mapping[str, Any] | None = None
    guest_observed: Mapping[str, Any] | None = None
    unrealized: tuple[str, ...] = ()
    try:
        native_snapshot, realize_check, unrealized, operation_id = _realize_native_substrate(
            execution_plan, control_plane, native_driver
        )
        checks.append(realize_check)
        if native_snapshot is not None and mode == "guest-certified":
            guest_observed = _guest_observed_report(native_driver, operation_id, certifying=driver_factory is None)
    finally:
        native_cleanup_verified = _append_cleanup_check(native_driver, native_snapshot, checks)
    return native_snapshot, native_cleanup_verified, unrealized, guest_observed


def _append_cleanup_check(
    native_driver: TechVaultNativeLibvirtDriver, native_snapshot: Mapping[str, Any] | None, checks: list[EvidenceCheck]
) -> bool | None:
    """Cleanup runs after every attempt; residue on a failed/unrealized run is reported."""
    if native_snapshot is not None:
        verified, diagnostics = _verify_native_cleanup(native_driver, native_snapshot)
        checks.append(EvidenceCheck("native_substrate_cleanup", verified, diagnostics))
        return verified
    residue_ok, residue_diagnostics = _sweep_residue(native_driver)
    if not residue_ok:
        checks.append(EvidenceCheck("native_substrate_residue", False, residue_diagnostics))
    return None


def _default_native_driver_factory(
    project_dir: Path, run_id: str, settings: LibvirtEvidenceRunConfig, mode: str
) -> Callable[[], TechVaultNativeLibvirtDriver]:
    """Build the default native libvirt driver factory for an operator-run native mode.

    The driver connects to a real libvirt daemon at realize time; ``guest-certified``
    selects the guest-observing driver. In CI/tests a fake driver_factory is injected
    instead, so this is never exercised without a daemon.
    """
    state_dir = project_dir / "runs" / run_id / "scenario-evidence" / "libvirt"

    def factory() -> TechVaultNativeLibvirtDriver:
        if mode == "guest-certified":
            from raes_backend_libvirt.guest_certified_driver import GuestCertifiedLibvirtDriver

            return GuestCertifiedLibvirtDriver(
                state_dir=state_dir,
                connection_uri=settings.connection_uri,
                name_prefix="raes-evidence",
            )
        return TechVaultNativeLibvirtDriver(
            state_dir=state_dir,
            connection_uri=settings.connection_uri,
            name_prefix="raes-evidence",
        )

    return factory


def _guest_observed_report(
    native_driver: TechVaultNativeLibvirtDriver, operation_id: str | None, *, certifying: bool
) -> Mapping[str, Any] | None:
    """Assemble the operation-joined, challenge-bound guest report from the driver.

    The control-plane operation id and observation timestamp are joined here, at the
    operations boundary, rather than inside the backend driver. ``certifying`` records
    whether the governed production driver was used; an injected fake driver yields a
    non-certifying report that is externally distinguishable from a real proof.
    """
    observations = getattr(native_driver, "last_guest_observations", ())
    if not observations:
        return None
    facts = getattr(native_driver, "last_guest_facts", {})
    binding = getattr(native_driver, "last_guest_binding", {})
    correlations = binding.get("correlations", {}) if isinstance(binding, Mapping) else {}
    domains = [
        {
            "address": address,
            "correlation": correlations.get(address),
            "architecture": fact.get("architecture"),
            "vcpus": fact.get("vcpus"),
            "memory_mib": fact.get("memory_mib"),
            "network": list(fact.get("interfaces", ())),
            "content": list(fact.get("content", ())),
            "accounts": list(fact.get("accounts", ())),
            "services": list(fact.get("services", ())),
        }
        for address, fact in sorted(facts.items())
        if isinstance(fact, Mapping)
    ]
    return {
        # The raw control-plane operation id is a UUID and never portable identity;
        # bind a redacted digest instead so the guest report joins the operation
        # without leaking the UUID (the redaction gate forbids raw UUIDs).
        "operation_ref": _operation_ref(operation_id),
        "observed_at": datetime.now(UTC).isoformat(),
        "certifying": certifying,
        "probe_policy": binding.get("probe_policy") if isinstance(binding, Mapping) else None,
        "memory_tolerance_mib": binding.get("memory_tolerance_mib") if isinstance(binding, Mapping) else None,
        "challenge": binding.get("challenge") if isinstance(binding, Mapping) else None,
        "domains": domains,
    }


def _operation_ref(operation_id: str | None) -> str | None:
    if not operation_id:
        return None
    return "sha256:" + hashlib.sha256(operation_id.encode("utf-8")).hexdigest()


def _verify_native_cleanup(
    native_driver: TechVaultNativeLibvirtDriver, native_snapshot: Mapping[str, Any]
) -> tuple[bool, tuple[str, ...]]:
    """Tear down a realized substrate and verify native + guest-probe cleanup."""

    verified, diagnostics = cleanup_native_snapshot(native_driver, native_snapshot)
    if verified and getattr(native_driver, "last_guest_binding", {}):
        return False, (*diagnostics, "guest probe artifacts were not fully cleaned")
    return verified, diagnostics


def _sweep_residue(native_driver: TechVaultNativeLibvirtDriver) -> tuple[bool, tuple[str, ...]]:
    """Best-effort finally-path sweep after a failed/unrealized attempt.

    The driver rolls back on failure, so the common case leaves no residue. Any
    remaining realized address, non-empty snapshot, or residual guest binding is a
    leak and is reported so the run cannot pass.
    """
    clean = (
        not native_driver.realized_addresses()
        and native_driver.last_snapshot == {}
        and not getattr(native_driver, "last_guest_binding", {})
    )
    if clean:
        return True, ()
    residual = tuple(sorted(native_driver.realized_addresses()))
    result = native_driver.destroy(networks=residual, domains=residual)
    ok = (
        not result.diagnostics
        and not native_driver.realized_addresses()
        and native_driver.last_snapshot == {}
        and not getattr(native_driver, "last_guest_binding", {})
    )
    if ok:
        return True, ()
    diagnostics = tuple(f"{item.code} at {item.address}" for item in result.diagnostics)
    return False, diagnostics or ("residual native or guest state remains after a failed attempt",)


def _realize_native_substrate(
    execution_plan: ExecutionPlan,
    control_plane: RuntimeControlPlane,
    native_driver: TechVaultNativeLibvirtDriver | None,
) -> tuple[Mapping[str, Any] | None, EvidenceCheck, tuple[str, ...], str | None]:
    """Realize the libvirt provisioning substrate (VMs + networks) for the scenario.

    Native modes pass only when the runtime operation succeeds and the fresh driver
    report contains independently daemon-observed domains bound to the selected
    realization-envelope/configuration identity. A domain handle or planned matrix
    alone is never sufficient. Returns the control-plane operation id so the evidence
    producer can join it at this boundary.
    """
    result: tuple[Mapping[str, Any] | None, EvidenceCheck, tuple[str, ...], str | None]
    if native_driver is None:
        result = None, EvidenceCheck("native_substrate_realization", False, ("no native driver",)), (), None
    else:
        planning_failures = _dedupe(
            f"{diagnostic.code}: {diagnostic.message}"
            for diagnostic in execution_plan.diagnostics
            if diagnostic.is_error
        )
        result = _realize_planned_native_substrate(
            execution_plan,
            control_plane,
            native_driver,
            planning_failures,
        )
    return result


def _realize_planned_native_substrate(
    execution_plan: ExecutionPlan,
    control_plane: RuntimeControlPlane,
    native_driver: TechVaultNativeLibvirtDriver,
    planning_failures: tuple[str, ...],
) -> tuple[Mapping[str, Any] | None, EvidenceCheck, tuple[str, ...], str | None]:
    if planning_failures:
        result = (
            None,
            EvidenceCheck("native_substrate_realization", False, ("composite planning rejected native realization",)),
            planning_failures,
            None,
        )
    else:
        try:
            control_plane.register_planner_produced_plan(execution_plan)
            receipt = control_plane.submit_provisioning(execution_plan.provisioning)
            operation_id = str(receipt.operation_id)
            status = control_plane.get_operation(receipt.operation_id)
        except Exception:
            result = (
                None,
                EvidenceCheck("native_substrate_realization", False, ("native realization failed",)),
                (),
                None,
            )
        else:
            result = _native_realization_result(execution_plan, native_driver, status, operation_id)
    return result


def _native_realization_result(
    execution_plan: ExecutionPlan,
    native_driver: TechVaultNativeLibvirtDriver,
    status: OperationStatus | None,
    operation_id: str,
) -> tuple[Mapping[str, Any] | None, EvidenceCheck, tuple[str, ...], str]:
    unrealized = _dedupe(
        f"{d.code}: {d.message}"
        for source in (execution_plan.diagnostics, () if status is None else status.diagnostics)
        for d in source
        if d.is_error
    )
    snapshot = native_driver.last_snapshot
    operation_succeeded = status is not None and status.state.value == "succeeded"
    realized = operation_succeeded and _snapshot_has_daemon_observations(snapshot)
    check = EvidenceCheck(
        "native_substrate_realization",
        realized,
        ()
        if realized
        else ("libvirt backend realized no native substrate for this scenario; capabilities disclosed as unrealized",),
    )
    return (snapshot if realized else None), check, unrealized, operation_id


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return tuple(seen)


def _snapshot_has_daemon_observations(snapshot: Mapping[str, Any] | None) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    domains = snapshot.get("domains", ())
    binding = snapshot.get("binding")
    return (
        snapshot.get("source") == "daemon-observed"
        and isinstance(domains, list | tuple)
        and len(domains) > 0
        and isinstance(binding, Mapping)
    )
