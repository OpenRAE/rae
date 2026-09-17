"""RUN-314 / GOV-913: opt-in real-container integration test.

Marked ``@pytest.mark.docker`` so it is excluded from the default hermetic
suite (``addopts = -m 'not fuzz and not integration and not docker'``).
Run it explicitly with ``pytest -m docker`` / ``nox -s integration_docker``.
It self-skips cleanly for optional local/PR runs when no runtime or image is
available. The exact-SHA release gate sets ``RAES_DOCKER_INTEGRATION_REQUIRED=1``
to turn every such condition into a hard failure.

The image identity is reviewed lock data (``release-test-alpine``), not a
literal here, and *where* it is obtained is the operator's closed source class
(``RAES_OCI_SOURCE_CLASS``). An availability failure may skip an optional run;
an integrity failure -- a runtime holding something other than the reviewed
graph -- never may, in either mode.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import subprocess
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
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
from tools import oci_release_image
from tools.oci_image_layout import LockedPlatformGraph

pytestmark = pytest.mark.docker

_REQUIRED_MODE_ENV = "RAES_DOCKER_INTEGRATION_REQUIRED"
# Bounded so the driver's derived native names stay inside the runtime's limit.
_RUN_TOKEN_BYTES = 4


@dataclass(frozen=True)
class AdmittedImage:
    """The reviewed image this run may realize, and where it came from."""

    reference: str
    graph: LockedPlatformGraph


@dataclass(frozen=True)
class ContainerRuntime:
    runtime: str
    image: AdmittedImage


def run_workspace(purpose: str) -> str:
    """Return one opaque run namespace.

    Concurrent runs must not contend for a native container or network name, so
    every run gets its own namespace and the driver commits resource names to
    it. Ownership is still proven by labels, never by the name.
    """

    return f"raes-ref-it-{purpose}-{secrets.token_hex(_RUN_TOKEN_BYTES)}"


def _locked_graphs() -> tuple[LockedPlatformGraph, ...]:
    return oci_release_image.locked_platform_graphs()


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
    """Report an availability failure: skippable locally, fatal for a release."""

    if _required_mode():
        pytest.fail(f"required real-container release gate unavailable: {reason}")
    pytest.skip(reason)


def _locked_image(source: oci_release_image.ImageSource) -> AdmittedImage:
    """Resolve the reviewed image identity for *source*."""

    graph = oci_release_image.execution_graph(_locked_graphs())
    reference = oci_release_image.image_reference(
        oci_release_image.locked_repository(),
        graph.index.digest,
        source,
    )
    return AdmittedImage(reference=reference, graph=graph)


def _require_container_runtime() -> ContainerRuntime:
    # Validate the release-mode selector even when the runtime and input both
    # resolve; a misspelled admission setting must never silently become an
    # optional run.
    _required_mode()
    source, reason = oci_release_image.attempt(lambda: oci_release_image.resolve_source(os.environ))
    if reason is not None:
        pytest.fail(f"reviewed OCI input is misconfigured: {reason}")
    runtime = _available_runtime()
    if runtime is None:
        _unavailable("no container runtime (docker/podman) available")
    image, reason = oci_release_image.attempt(lambda: _locked_image(source))
    if reason is not None or image is None:
        pytest.fail(f"reviewed OCI input is misconfigured: {reason}")
    # Obtain the reviewed bytes for this source class. A pre-seeded context
    # performs no acquisition, and a mirror-only one never falls back publicly.
    _, reason = oci_release_image.attempt(
        lambda: oci_release_image.acquire_image(source, image.reference, runtime=runtime)
    )
    if reason is not None:
        _unavailable("integration image is not available (offline registry?)")
    # Whatever the source class, the runtime must now hold exactly the reviewed
    # platform graph. This is an integrity check, so it fails in either mode.
    _, reason = oci_release_image.attempt(
        lambda: oci_release_image.verify_daemon_image(image.reference, image.graph, runtime=runtime)
    )
    if reason is not None:
        pytest.fail(f"container runtime image does not match the reviewed OCI graph: {reason}")
    return ContainerRuntime(runtime=runtime, image=image)


def _surviving_owned_resources(runtime: str, workspace: str, runner) -> list[str]:
    """Return runtime resources still carrying this run's ownership label.

    The filter names this run's exact workspace, so a concurrent run's
    resources are never visible here and can never be swept.
    """

    completed = runner(
        [runtime, "ps", "--all", "--quiet", "--filter", f"label=raes.workspace={workspace}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


@contextlib.contextmanager
def realized(driver, *, workspace: str, runtime: str, runner=subprocess.run) -> Iterator[None]:
    """Tear down this run's resources on both the success and failure paths.

    The teardown set comes from what the driver actually realized, not from a
    caller-supplied guess: ``docker rm --force`` is idempotent, so asking it to
    remove an address that was never realized reports success while the real
    resource leaks. Afterwards the runtime itself is asked whether anything
    still carries this run's ownership label, because a removal command's exit
    code is not proof that the resource is gone. Both a failed teardown and a
    survivor are reported rather than hidden behind ``--rm`` or a best-effort
    sweep.
    """

    try:
        yield
    finally:
        addresses = driver.realized_addresses()
        networks = tuple(sorted(address for address in addresses if ".network." in address))
        containers = tuple(sorted(address for address in addresses if address not in networks))
        result = driver.destroy(networks=networks, containers=containers)
        survivors = _surviving_owned_resources(runtime, workspace, runner)
        if result.diagnostics:
            codes = sorted({diagnostic.code for diagnostic in result.diagnostics})
            pytest.fail(f"real-container teardown did not remove every owned resource: {codes}")
        if survivors:
            pytest.fail(f"container runtime still owns {len(survivors)} resource(s) from this run after teardown")


@pytest.fixture(scope="module")
def container_runtime() -> ContainerRuntime:
    return _require_container_runtime()


def _scenario(image: str) -> str:
    return f"""
name: ref-docker
nodes:
  web:
    type: compute
    source: {image}
    resources: {{ram: 1 gib, cpu: 1}}
"""


def test_real_container_provision_inventory_and_teardown(container_runtime: ContainerRuntime):
    image = container_runtime.image.reference
    # The scenario pins an explicit image source, so the operator allowlists it
    # through the image-trust policy (plan-pinned tags are rejected by default).
    workspace = run_workspace("provision")
    driver = OciDeploymentDriver(
        runtime=container_runtime.runtime,
        workspace=workspace,
        image_policy=ImageTrustPolicy(allowed_images=(image,)),
    )
    target = create_reference_backend_target(driver=driver)

    manager = RuntimeManager(target)
    execution_plan = manager.plan(parse_sdl(textwrap.dedent(_scenario(image))))

    control_plane = RuntimeControlPlane(target)
    with realized(driver, workspace=workspace, runtime=container_runtime.runtime):
        control_plane.register_planner_produced_plan(execution_plan)
        receipt = control_plane.submit_provisioning(execution_plan.provisioning)
        status = control_plane.get_operation(receipt.operation_id)
        assert status is not None and status.state.value == "succeeded"
        # The driver records realization against the real runtime; the portable
        # snapshot shows the realized node.
        assert "provision.node.web" in control_plane.snapshot.entries
        assert "provision.node.web" in driver.realized_addresses()


def test_real_driver_conformance_executes_native_cases_and_fails_closed_for_nonconstructive_envelope(
    container_runtime: ContainerRuntime,
):
    image = container_runtime.image.reference
    workspace = run_workspace("conformance")
    driver = OciDeploymentDriver(
        runtime=container_runtime.runtime,
        workspace=workspace,
        image_policy=ImageTrustPolicy(default_image=image),
    )
    target = create_reference_backend_target(driver=driver)

    with realized(driver, workspace=workspace, runtime=container_runtime.runtime):
        report = run_target_conformance(
            target,
            participant_opacity_harness=ReferenceParticipantOpacityHarness(),
            reference_scenario=_scenario(image),
        )

        assert report.profile == BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE
        assert report.passed is False
        failed_cases = [case for case in report.cases if not case.passed]
        assert {case.name for case in failed_cases} == {"realization-envelope-constructive"}
        assert {diagnostic.code for case in failed_cases for diagnostic in case.diagnostics} == {
            "realization-envelope.positive-probe.no-witness",
            "realization-envelope.negative-probe.no-witness",
        }
