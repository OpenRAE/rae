"""RUN-314: opt-in real-container integration test.

Marked ``@pytest.mark.docker`` so it is excluded from the default hermetic
suite (``addopts = -m 'not fuzz and not integration and not docker'``).
Run it explicitly with ``pytest -m docker`` / ``nox -s integration_docker``.
It self-skips cleanly for optional local/PR runs when no runtime or image is
available. The exact-SHA release gate sets ``RAES_DOCKER_INTEGRATION_REQUIRED=1``
to turn every such condition into a hard failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from typing import NoReturn

import pytest
from raes import parse_sdl
from raes_conformance.conformance import (
    BackendCapabilityProfile,
    run_target_conformance,
)
from raes_conformance.conformance.reference_participant_opacity import ReferenceParticipantOpacityHarness
from raes_reference_backend import create_reference_backend_target
from raes_reference_backend.drivers.oci import ImageTrustPolicy, OciDeploymentDriver
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager

pytestmark = pytest.mark.docker

_REQUIRED_MODE_ENV = "RAES_DOCKER_INTEGRATION_REQUIRED"
_IMAGE = "docker.io/library/alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"
_SCENARIO = f"""
name: ref-docker
nodes:
  web:
    type: compute
    source: {_IMAGE}
    resources: {{ram: 1 gib, cpu: 1}}
"""


def _available_runtime() -> str | None:
    for runtime in ("docker", "podman"):
        if shutil.which(runtime) is None:
            continue
        try:
            completed = subprocess.run(
                [runtime, "info"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0:
            return runtime
    return None


def _required_mode() -> bool:
    value = os.environ.get(_REQUIRED_MODE_ENV, "0")
    if value not in {"0", "1"}:
        pytest.fail(f"{_REQUIRED_MODE_ENV} must be exactly 0 or 1")
    return value == "1"


def _unavailable(reason: str) -> NoReturn:
    if _required_mode():
        pytest.fail(f"required real-container release gate unavailable: {reason}")
    pytest.skip(reason)


def _require_container_runtime() -> str:
    # Validate the release-mode selector even when the runtime and pull both
    # succeed; a misspelled admission setting must never silently become an
    # optional run.
    _required_mode()
    runtime = _available_runtime()
    if runtime is None:
        _unavailable("no container runtime (docker/podman) available")
    # Pre-pull the reviewed multiarch image. Optional runs skip if the registry
    # is unavailable; release-required mode fails closed.
    try:
        completed = subprocess.run(
            [runtime, "pull", _IMAGE],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        _unavailable("container runtime present but image pull failed")
    if completed.returncode != 0:
        _unavailable("integration image is not available (offline registry?)")
    return runtime


@pytest.fixture(scope="module")
def container_runtime() -> str:
    return _require_container_runtime()


def test_real_container_provision_inventory_and_teardown(container_runtime: str):
    workspace = "raes-ref-it"
    # The scenario pins an explicit image source, so the operator allowlists it
    # through the image-trust policy (plan-pinned tags are rejected by default).
    driver = OciDeploymentDriver(
        runtime=container_runtime,
        workspace=workspace,
        image_policy=ImageTrustPolicy(allowed_images=(_IMAGE,)),
    )
    target = create_reference_backend_target(driver=driver)

    manager = RuntimeManager(target)
    execution_plan = manager.plan(parse_sdl(textwrap.dedent(_SCENARIO)))

    control_plane = RuntimeControlPlane(target)
    try:
        control_plane.register_planner_produced_plan(execution_plan)
        receipt = control_plane.submit_provisioning(execution_plan.provisioning)
        status = control_plane.get_operation(receipt.operation_id)
        assert status is not None and status.state.value == "succeeded"
        # The driver records realization against the real runtime; the portable
        # snapshot shows the realized node.
        assert "provision.node.web" in control_plane.snapshot.entries
        assert "provision.node.web" in driver.realized_addresses()
    finally:
        driver.destroy(networks=(), containers=("provision.node.web",))


def test_real_driver_conformance_executes_native_cases_and_fails_closed_for_nonconstructive_envelope(
    container_runtime: str,
):
    driver = OciDeploymentDriver(
        runtime=container_runtime,
        workspace="raes-ref-it-conf",
        image_policy=ImageTrustPolicy(default_image=_IMAGE),
    )
    target = create_reference_backend_target(driver=driver)

    try:
        report = run_target_conformance(
            target,
            participant_opacity_harness=ReferenceParticipantOpacityHarness(),
            reference_scenario=_SCENARIO,
        )

        assert report.profile == BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE
        assert report.passed is False
        failed_cases = [case for case in report.cases if not case.passed]
        assert {case.name for case in failed_cases} == {"realization-envelope-constructive"}
        assert {diagnostic.code for case in failed_cases for diagnostic in case.diagnostics} == {
            "realization-envelope.positive-probe.no-witness",
            "realization-envelope.negative-probe.no-witness",
        }
    finally:
        driver.destroy(networks=(), containers=("provision.node.vm",))
