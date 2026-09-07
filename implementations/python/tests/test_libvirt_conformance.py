"""Issue #606: libvirt backend conformance (fixture + target adapter).

Acceptance bar:

1. ``raes conformance backend --profile provisioning-only`` passes with no
   ``unsupported-capability-claim`` / ``unsupported-contract-declaration``
   diagnostics (covered by ``test_backend_conformance_cli.py`` /
   ``run_fixture_suite`` -- asserted green here for the libvirt-relevant profile).
2. ``run_target_conformance`` keeps ordinary target conformance distinct from
   the constructive-envelope certification that the published libvirt envelope
   still cannot satisfy without native ASR-519 probes.
3. A conformance report is captured and committed (drift-guarded here).

The direct control-plane tests still exercise the real ``LibvirtProvisioner``
path through an injected recording driver without a libvirt/QEMU daemon. That
is hermetic adapter evidence only.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from textwrap import dedent

from libvirt_conformance_fixtures import RecordingLibvirtDriver
from libvirt_participant_fixtures import NullLibvirtDriver
from raes.parser import parse_sdl
from raes_backend_libvirt.target import create_libvirt_target
from raes_conformance.conformance import (
    BackendCapabilityProfile,
    run_fixture_suite,
    run_target_conformance,
)
from raes_contracts.planning import RuntimeDomain
from raes_processor.reference import run_reference_processor
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTED_REPORT = REPO_ROOT / "docs" / "conformance" / "libvirt-qemu.provisioning-only.report.json"

_PROVISIONING_SCENARIO = dedent(
    """
    name: libvirt-conformance
    nodes:
      vm:
        type: compute
        resources: {ram: 1 gib, cpu: 1}
    """
)


def _execution_plan(target, snapshot=None):
    scenario = parse_sdl(_PROVISIONING_SCENARIO)
    if snapshot is None:
        return run_reference_processor(scenario, target.manifest).execution_plan
    return RuntimeManager(target, initial_snapshot=snapshot).plan(scenario)


def _bounded_report_payload(report) -> dict:
    """Bounded, environment-stable projection of a conformance report.

    Keeps only fields that are reproducible across runs and dependency versions:
    profile, pass/fail, per-case identity + pass/fail + stable diagnostic
    *codes*, and gap sets. Free-text diagnostic messages (which carry
    validator-version-specific prose) are intentionally excluded so the
    committed report never drifts on an unrelated dependency bump.
    """

    return {
        "profile": report.profile,
        "passed": report.passed,
        "cases": [
            {
                "name": case.name,
                "contract_name": case.contract_name,
                "valid": case.valid,
                "passed": case.passed,
                "diagnostic_codes": sorted({diag.code for diag in case.diagnostics}),
            }
            for case in report.cases
        ],
        "unsupported_contract_gaps": list(report.unsupported_contract_gaps),
        "unsupported_capability_gaps": list(report.unsupported_capability_gaps),
        "diagnostic_codes": sorted({diag.code for diag in report.diagnostics}),
    }


def _libvirt_conformance_report():
    return run_target_conformance(
        create_libvirt_target(driver=RecordingLibvirtDriver()),
        reference_scenario=_PROVISIONING_SCENARIO,
    )


# ---------------------------------------------------------------------------
# AC1: fixture suite for the libvirt-relevant profile is clean
# ---------------------------------------------------------------------------


def test_provisioning_only_fixture_suite_has_no_unsupported_diagnostics():
    report = run_fixture_suite(profile=BackendCapabilityProfile.PROVISIONING_ONLY)

    assert report.passed is True, [diag.message for diag in report.diagnostics]
    codes = {diag.code for diag in report.diagnostics} | {
        diag.code for case in report.cases for diag in case.diagnostics if not case.passed
    }
    assert "conformance.unsupported-capability-claim" not in codes
    assert "conformance.unsupported-contract-declaration" not in codes


# ---------------------------------------------------------------------------
# AC2: target conformance remains separate from constructive-envelope refusal
# ---------------------------------------------------------------------------


def test_provisioning_only_conformance_reports_non_constructive_envelope_separately():
    report = _libvirt_conformance_report()

    assert report.profile == BackendCapabilityProfile.PROVISIONING_ONLY
    assert report.passed is False
    assert not report.unsupported_contract_gaps
    assert not report.unsupported_capability_gaps

    case_names = {case.name for case in report.cases}
    assert "target-manifest" in case_names
    assert "target-provisioning" in case_names
    assert "target-snapshot" in case_names
    constructive = next(case for case in report.cases if case.name == "realization-envelope-constructive")
    assert constructive.outcome == "unsupported"
    assert constructive.passed is False


def test_libvirt_provisioning_mutates_snapshot():
    driver = RecordingLibvirtDriver()
    target = create_libvirt_target(driver=driver)
    control_plane = RuntimeControlPlane(target)
    execution_plan = _execution_plan(target)
    provisioning_plan = execution_plan.provisioning
    control_plane.register_planner_produced_plan(execution_plan)

    receipt = control_plane.submit_provisioning(provisioning_plan)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None and status.state.value == "succeeded", status
    assert status.changed_addresses, "provisioning must report changed addresses"

    provisioned = {
        address
        for address, entry in control_plane.snapshot.entries.items()
        if entry.domain == RuntimeDomain.PROVISIONING
    }
    assert provisioned, "snapshot must gain provisioning entries (real mutation, not contract-surface)"
    # The real libvirt provisioner path drove the injected driver.
    assert driver.realized_addresses(), "driver must have realized the provisioned addresses"
    assert provisioned & set(driver.realized_addresses())


def test_libvirt_conformance_driver_bootstraps_missing_noop_substrate_evidence():
    driver = RecordingLibvirtDriver()
    target = create_libvirt_target(driver=driver)
    scenario = parse_sdl(_PROVISIONING_SCENARIO)
    first = RuntimeControlPlane(target)
    initial_execution_plan = _execution_plan(target)
    initial_plan = initial_execution_plan.provisioning
    first.register_planner_produced_plan(initial_execution_plan)
    first.submit_provisioning(initial_plan)
    legacy_snapshot = replace(first.snapshot, realization_observations=())
    unchanged_execution_plan = _execution_plan(target, legacy_snapshot)
    unchanged = unchanged_execution_plan.provisioning
    assert all(operation.action.value == "unchanged" for operation in unchanged.operations)

    upgraded = RuntimeControlPlane(target, initial_snapshot=legacy_snapshot)
    upgraded.register_planner_produced_plan(unchanged_execution_plan)
    receipt = upgraded.submit_provisioning(unchanged)

    assert upgraded.get_operation(receipt.operation_id).state.value == "succeeded"
    assert upgraded.snapshot.realization_observations
    assert any(operation.verb == "observe" for operation in driver.recorded_ops)


def test_provisioning_only_conformance_requires_confirmed_realization():
    """A driver that does not confirm realization fails the ordinary adapter boundary.

    This remains a direct hermetic adapter test; passing target conformance does
    not replace constructive-envelope certification evidence.
    """

    target = create_libvirt_target(driver=NullLibvirtDriver())
    control_plane = RuntimeControlPlane(target)
    execution_plan = _execution_plan(target)
    provisioning_plan = execution_plan.provisioning
    control_plane.register_planner_produced_plan(execution_plan)
    receipt = control_plane.submit_provisioning(provisioning_plan)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None and status.state.value == "failed"
    assert not status.changed_addresses
    assert not any(entry.domain == RuntimeDomain.PROVISIONING for entry in control_plane.snapshot.entries.values())


# ---------------------------------------------------------------------------
# AC3: committed conformance report is captured and kept current
# ---------------------------------------------------------------------------


def test_committed_conformance_report_is_current():
    assert COMMITTED_REPORT.exists(), f"committed conformance report missing at {COMMITTED_REPORT}"
    committed = json.loads(COMMITTED_REPORT.read_text(encoding="utf-8"))
    fresh = _bounded_report_payload(_libvirt_conformance_report())

    assert committed == fresh, (
        "committed libvirt conformance report is stale; regenerate "
        f"{COMMITTED_REPORT.relative_to(REPO_ROOT)} from run_target_conformance"
    )
    assert committed["passed"] is False
