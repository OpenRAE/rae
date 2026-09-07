"""Native RAES/libvirt live validation for TechVault scenarios."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from raes.parser import parse_sdl_file
from raes_backend_libvirt.target import create_libvirt_target
from raes_backend_libvirt.techvault_native import TechVaultNativeLibvirtDriver, expected_surface
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

from raes_operations._evidence_run_validation import redaction_violations
from raes_operations._techvault_cleanup import cleanup_native_snapshot
from raes_operations.run_artifacts import (
    atomic_write_json_artifact,
    is_valid_run_id_label,
    portable_artifact_ref,
    run_artifact_path,
)

_LIVE_SCHEMA = "raes.libvirt.techvault-native-live-gate/v1"
_SHA256_RE = re.compile(r"sha256:[a-f0-9]{64}")


@dataclass(frozen=True)
class LiveCheck:
    """One RAES/libvirt TechVault live check."""

    name: str
    passed: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class TechVaultLiveReport:
    """Rendered outcome for the native RAES/libvirt TechVault live gate."""

    scenario: str
    output_dir: str
    run_id: str
    checks: tuple[LiveCheck, ...]
    manifest_path: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def render(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"RAES/libvirt native TechVault live gate -- scenario={self.scenario} run_id={self.run_id}: {status}"]
        for check in self.checks:
            marker = "ok" if check.passed else "FAIL"
            lines.append(f"  [{marker}] {check.name}")
            for diagnostic in check.diagnostics:
                lines.append(f"        - {diagnostic}")
        if self.manifest_path:
            lines.append(f"  manifest: {self.manifest_path}")
        return "\n".join(lines)


@dataclass(frozen=True)
class TechVaultLiveConfig:
    """Runtime controls for the native RAES/libvirt TechVault live gate."""

    connection_uri: str = "qemu:///system"


def validate_techvault_live(
    *,
    scenario_path: Path,
    project_dir: Path,
    run_id: str,
    config: TechVaultLiveConfig | None = None,
    driver_factory: Callable[[], TechVaultNativeLibvirtDriver] | None = None,
) -> TechVaultLiveReport:
    """Boot and validate a TechVault SDL through native RAES/libvirt."""

    settings = config or TechVaultLiveConfig()
    output_dir = project_dir
    checks: list[LiveCheck] = []
    manifest_path: str | None = None
    run_id_check = _check_run_id(run_id)
    checks.append(run_id_check)
    if run_id_check.passed:
        run_dir = output_dir / "runs" / run_id / "live-gate"
        driver = (
            driver_factory()
            if driver_factory
            else TechVaultNativeLibvirtDriver(
                state_dir=run_dir / "libvirt",
                connection_uri=settings.connection_uri,
                name_prefix="raes-techvault",
            )
        )
        target = create_libvirt_target(driver=driver, name_prefix="raes-techvault")
        scenario, plan_check = _plan_scenario(target, scenario_path)
        del scenario
        checks.append(plan_check)
        snapshot: Mapping[str, object] = {}
        if plan_check.passed:
            boot_check = _apply_plan(target, scenario_path, driver)
            checks.append(boot_check)
            snapshot = driver.last_snapshot
            if boot_check.passed:
                checks.append(_substrate_independence_check(snapshot))
                checks.append(_surface_check(snapshot))
                cleanup_ok, cleanup_diagnostics = cleanup_native_snapshot(driver, snapshot)
                checks.append(LiveCheck("verified_native_cleanup", cleanup_ok, cleanup_diagnostics))
        manifest_path = _write_manifest(
            output_dir,
            run_id,
            scenario_path,
            snapshot,
            checks,
        )
        checks.append(
            LiveCheck(
                "run_archive_manifest",
                manifest_path is not None,
                () if manifest_path else ("manifest write failed",),
            )
        )
    return TechVaultLiveReport(str(scenario_path), str(output_dir), run_id, tuple(checks), manifest_path)


def _check_run_id(run_id: str) -> LiveCheck:
    if is_valid_run_id_label(run_id):
        return LiveCheck("run_id_input", True)
    return LiveCheck("run_id_input", False, ("run id must be a safe filesystem label",))


def _plan_scenario(target: object, scenario_path: Path) -> tuple[object | None, LiveCheck]:
    try:
        scenario = parse_sdl_file(scenario_path)
        execution_plan = RuntimeManager(target).plan(scenario)
    except Exception:
        return None, LiveCheck("planning", False, ("scenario planning failed",))
    diagnostics = tuple(f"{diag.code}: {diag.message}" for diag in execution_plan.diagnostics if diag.is_error)
    if diagnostics:
        return scenario, LiveCheck("planning", False, diagnostics)
    return scenario, LiveCheck("planning", True)


def _apply_plan(target: object, scenario_path: Path, driver: TechVaultNativeLibvirtDriver) -> LiveCheck:
    passed = False
    diagnostics: tuple[str, ...] = ()
    try:
        scenario = parse_sdl_file(scenario_path)
        execution_plan = RuntimeManager(target).plan(scenario)
        control_plane = RuntimeControlPlane(target, initial_snapshot=execution_plan.base_snapshot)
        control_plane.register_planner_produced_plan(execution_plan)
        receipt = control_plane.submit_provisioning(execution_plan.provisioning)
        status = control_plane.get_operation(receipt.operation_id)
    except Exception:
        diagnostics = ("provisioning failed",)
    else:
        if status is None:
            diagnostics = ("control plane did not record provisioning status",)
        else:
            diagnostics = tuple(f"{diag.code}: {diag.message}" for diag in status.diagnostics if diag.is_error)
            if status.state.value != "succeeded" or diagnostics:
                diagnostics = diagnostics or (f"provisioning state={status.state.value}",)
            elif not _domains(driver.last_snapshot):
                diagnostics = ("native libvirt driver returned no domain snapshot",)
            else:
                passed = True
    return LiveCheck("raes_libvirt_native_boot", passed, diagnostics)


def _substrate_independence_check(snapshot: Mapping[str, Any]) -> LiveCheck:
    substrate = snapshot.get("substrate")
    if substrate == "libvirt-qemu-initramfs" and not snapshot.get("containers"):
        return LiveCheck("independent_libvirt_substrate", True)
    return LiveCheck(
        "independent_libvirt_substrate",
        False,
        (f"unexpected substrate/snapshot shape: substrate={substrate!r}",),
    )


def _surface_check(snapshot: Mapping[str, Any]) -> LiveCheck:
    surface = expected_surface(snapshot)
    domains = surface["domains"]
    networks = surface["networks"]
    diagnostics: list[str] = []
    if not domains:
        diagnostics.append("no native domains realized")
    if not networks:
        diagnostics.append("no native networks realized")
    return LiveCheck("model_derived_native_surface", not diagnostics, tuple(diagnostics))


def _write_manifest(
    output_dir: Path,
    run_id: str,
    scenario_path: Path,
    snapshot: Mapping[str, object],
    checks: Sequence[LiveCheck],
) -> str | None:
    target = run_artifact_path(output_dir, run_id, "live-gate", "manifest.json")
    native_succeeded = any(check.name == "raes_libvirt_native_boot" and check.passed for check in checks)
    observed_snapshot = snapshot if native_succeeded else {}
    native_surface = expected_surface(observed_snapshot)
    cleanup_check = next((check for check in checks if check.name == "verified_native_cleanup"), None)
    cleanup_status = _live_cleanup_status(native_succeeded, cleanup_check)
    payload = {
        "schema": _LIVE_SCHEMA,
        "scenario": {
            "path": portable_artifact_ref(scenario_path),
            "name": scenario_path.name.split(".")[0],
        },
        "run_id": run_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        "cleanup_policy": "current-operation-owned-resources-only",
        "cleanup": {"source": "driver-reported", "status": cleanup_status},
        "realization_binding": observed_snapshot.get("binding"),
        "realization_facts": {
            "authored": {
                "source": "authored",
                "scenario_ref": portable_artifact_ref(scenario_path),
            },
            "planned": {
                "source": "planned",
                "status": "accepted"
                if any(check.name == "planning" and check.passed for check in checks)
                else "failed",
            },
            "driver_reported": {
                "source": "driver-reported",
                "status": "succeeded" if native_succeeded else "failed",
            },
            "daemon_observed": {
                "source": "daemon-observed",
                "domains": list(native_surface["domains"]),
                "networks": list(native_surface["networks"]),
            },
            "guest_observed": {
                "source": "guest-observed",
                "status": "not-observed",
            },
        },
        "validation": {
            "ok": all(check.passed for check in checks),
            "checks": [
                {"name": check.name, "ok": check.passed, "diagnostics": list(check.diagnostics)} for check in checks
            ],
        },
    }
    if validate_techvault_live_manifest(payload):
        return None
    try:
        atomic_write_json_artifact(target, payload)
    except OSError:
        return None
    return str(target)


def _live_cleanup_status(native_succeeded: bool, cleanup_check: LiveCheck | None) -> str:
    if not native_succeeded:
        return "not-required"
    return "verified" if cleanup_check is not None and cleanup_check.passed else "failed"


def validate_techvault_live_manifest(payload: Mapping[str, object]) -> list[str]:
    """Validate source separation and redaction before a live manifest is written."""

    violations = _validate_live_manifest_metadata(payload)
    violations.extend(_validate_live_scenario(payload))
    violations.extend(_validate_live_realization_facts(payload))
    violations.extend(_validate_live_forbidden_terms(payload))
    violations.extend(redaction_violations(payload))
    return violations


def _validate_live_manifest_metadata(payload: Mapping[str, object]) -> list[str]:
    violations: list[str] = []
    if payload.get("schema") != _LIVE_SCHEMA:
        violations.append("invalid TechVault live manifest schema")
    if payload.get("cleanup_policy") != "current-operation-owned-resources-only":
        violations.append("invalid TechVault cleanup policy")
    cleanup = payload.get("cleanup")
    if not isinstance(cleanup, Mapping) or cleanup.get("source") != "driver-reported":
        violations.append("cleanup must be a driver-reported section")
    return violations


def _validate_live_scenario(payload: Mapping[str, object]) -> list[str]:
    scenario = payload.get("scenario")
    path = scenario.get("path") if isinstance(scenario, Mapping) else None
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
        return ["scenario.path must be a portable reference"]
    return []


def _validate_live_realization_facts(payload: Mapping[str, object]) -> list[str]:
    facts = payload.get("realization_facts")
    if not isinstance(facts, Mapping):
        return ["realization_facts must be a mapping"]
    violations = _validate_live_fact_sources(facts)
    daemon = facts.get("daemon_observed")
    domains = daemon.get("domains", ()) if isinstance(daemon, Mapping) else ()
    networks = daemon.get("networks", ()) if isinstance(daemon, Mapping) else ()
    violations.extend(_validate_live_daemon_names(domains, networks))
    driver_reported = facts.get("driver_reported")
    succeeded = isinstance(driver_reported, Mapping) and driver_reported.get("status") == "succeeded"
    binding = payload.get("realization_binding")
    cleanup = payload.get("cleanup")
    cleanup_status = cleanup.get("status") if isinstance(cleanup, Mapping) else None
    violations.extend(_validate_live_outcome(succeeded, cleanup_status, domains, networks, binding))
    if isinstance(binding, Mapping):
        violations.extend(_validate_live_binding(binding))
    return violations


def _validate_live_fact_sources(facts: Mapping[str, object]) -> list[str]:
    expected_sources = {
        "authored": "authored",
        "planned": "planned",
        "driver_reported": "driver-reported",
        "daemon_observed": "daemon-observed",
        "guest_observed": "guest-observed",
    }
    return [
        f"{key}.source must be {source}"
        for key, source in expected_sources.items()
        if not isinstance(facts.get(key), Mapping) or facts[key].get("source") != source
    ]


def _validate_live_daemon_names(domains: object, networks: object) -> list[str]:
    violations: list[str] = []
    for collection_name, values in (("domains", domains), ("networks", networks)):
        if not _bounded_native_names(values):
            violations.append(f"daemon_observed.{collection_name} must contain bounded native names")
    return violations


def _bounded_native_names(values: object) -> bool:
    return isinstance(values, list | tuple) and all(isinstance(value, str) and value for value in values)


def _validate_live_outcome(
    succeeded: bool,
    cleanup_status: object,
    domains: object,
    networks: object,
    binding: object,
) -> list[str]:
    if succeeded:
        return _validate_successful_live_outcome(cleanup_status, domains, binding)
    return _validate_failed_live_outcome(cleanup_status, domains, networks, binding)


def _validate_successful_live_outcome(cleanup_status: object, domains: object, binding: object) -> list[str]:
    violations: list[str] = []
    if cleanup_status not in {"verified", "failed"}:
        violations.append("successful native realization requires an explicit cleanup outcome")
    if not domains or not isinstance(binding, Mapping):
        violations.append("successful native run requires daemon observations and realization binding")
    return violations


def _validate_failed_live_outcome(
    cleanup_status: object,
    domains: object,
    networks: object,
    binding: object,
) -> list[str]:
    violations: list[str] = []
    if cleanup_status != "not-required":
        violations.append("failed native realization must mark cleanup not-required")
    if domains or networks or binding is not None:
        violations.append("failed native run cannot publish stale daemon observations or binding")
    return violations


def _validate_live_binding(binding: Mapping[str, object]) -> list[str]:
    violations = _validate_live_binding_identity(binding)
    violations.extend(_validate_live_boot_digests(binding))
    expected_digest = _live_binding_digest(binding)
    if binding.get("driver_configuration_digest") != expected_digest:
        violations.append("realization binding driver configuration digest does not match its material")
    return violations


def _validate_live_binding_identity(binding: Mapping[str, object]) -> list[str]:
    violations: list[str] = []
    if binding.get("driver") != "techvault-appliance":
        violations.append("realization binding driver must be techvault-appliance")
    for field_name in (
        "realization_envelope_digest",
        "configuration_digest",
        "driver_configuration_digest",
        "connection_uri_digest",
        "name_prefix_digest",
    ):
        if not _canonical_digest(binding.get(field_name)):
            violations.append(f"realization binding requires canonical {field_name}")
    return violations


def _validate_live_boot_digests(binding: Mapping[str, object]) -> list[str]:
    boot_artifacts = binding.get("boot_artifact_digests")
    if not isinstance(boot_artifacts, Mapping) or set(boot_artifacts) != {"kernel", "initramfs"}:
        return ["realization binding requires kernel and initramfs digests"]
    if not all(_canonical_digest(value) for value in boot_artifacts.values()):
        return ["realization binding boot digests must be canonical sha256 values"]
    return []


def _live_binding_digest(binding: Mapping[str, object]) -> str:
    material = {
        "driver": binding.get("driver"),
        "configuration_digest": binding.get("configuration_digest"),
        "boot_artifact_digests": binding.get("boot_artifact_digests"),
        "connection_uri_digest": binding.get("connection_uri_digest"),
        "name_prefix_digest": binding.get("name_prefix_digest"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _validate_live_forbidden_terms(payload: Mapping[str, object]) -> list[str]:
    violations: list[str] = []
    rendered = json.dumps(payload, sort_keys=True, default=str)
    if "native-realized" in rendered:
        violations.append("native-realized is not an admitted observation basis")
    if "soc_readback" in rendered:
        violations.append("daemon substrate cannot supply SOC readback")
    return violations


def _domains(snapshot: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = snapshot.get("domains", ())
    return tuple(item for item in raw if isinstance(item, Mapping)) if isinstance(raw, list | tuple) else ()
