"""Policy regressions for optional versus release-required Docker integration.

Two properties this file exists to hold apart: an *availability* failure may
skip an ordinary local run and must fail a release-required one, while an
*integrity* failure -- the runtime holding an image that is not the reviewed
one -- must fail in either mode. A skip that hides a substituted image would
make the release gate meaningless.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import test_reference_backend_docker_integration as docker_integration
from tools import oci_release_image
from tools.oci_image_layout import LockedPlatformGraph, OciDescriptor

_RUNTIME = "docker"
_REPOSITORY = "docker.io/library/alpine"


def _graph() -> LockedPlatformGraph:
    index = OciDescriptor(digest="sha256:" + "d9" * 32, size=9226)
    return LockedPlatformGraph(
        platform_id="linux-x86_64",
        index=index,
        manifest=OciDescriptor(digest="sha256:" + "c6" * 32, size=1023),
        config=OciDescriptor(digest="sha256:" + "bf" * 32, size=612),
        layers=(OciDescriptor(digest="sha256:" + "25" * 32, size=3630321),),
        diff_ids=("sha256:" + "08" * 32,),
        architecture="amd64",
        os="linux",
    )


def test_optional_docker_integration_skips_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(docker_integration._REQUIRED_MODE_ENV, raising=False)
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: None)

    with pytest.raises(pytest.skip.Exception, match="no container runtime"):
        docker_integration._require_container_runtime()


def test_required_docker_integration_fails_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "1")
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: None)

    with pytest.raises(pytest.fail.Exception, match="required real-container release gate unavailable"):
        docker_integration._require_container_runtime()


def test_required_docker_integration_admits_a_successful_public_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph()
    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "1")
    monkeypatch.delenv(oci_release_image.SOURCE_CLASS_ENV, raising=False)
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: _RUNTIME)
    monkeypatch.setattr(docker_integration, "_locked_graphs", lambda: (graph,))
    monkeypatch.setattr(docker_integration.oci_release_image, "locked_repository", lambda: _REPOSITORY)
    acquired: list[str] = []
    monkeypatch.setattr(
        docker_integration.oci_release_image,
        "acquire_image",
        lambda _source, reference, **_kwargs: acquired.append(reference),
    )
    verified: list[str] = []
    monkeypatch.setattr(
        docker_integration.oci_release_image,
        "verify_daemon_image",
        lambda reference, _graph, **_kwargs: verified.append(reference),
    )

    admitted = docker_integration._require_container_runtime()

    expected_reference = f"{_REPOSITORY}@{graph.index.digest}"
    assert admitted.runtime == _RUNTIME
    assert admitted.image.reference == expected_reference
    # Acquisition and the identity readback name the same digest-pinned ref.
    assert acquired == [expected_reference]
    assert verified == [expected_reference]


def test_invalid_required_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "yes")
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: _RUNTIME)

    with pytest.raises(pytest.fail.Exception, match="must be exactly 0 or 1"):
        docker_integration._require_container_runtime()


def test_release_gate_takes_its_image_identity_from_the_reviewed_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reviewed identity is lock data, never a literal in this test tree."""

    graph = _graph()
    monkeypatch.setattr(docker_integration, "_locked_graphs", lambda: (graph,))
    monkeypatch.setattr(docker_integration.oci_release_image, "locked_repository", lambda: _REPOSITORY)

    admitted = docker_integration._locked_image(docker_integration.oci_release_image.resolve_source({}))

    assert admitted.reference == f"{_REPOSITORY}@{graph.index.digest}"
    assert admitted.graph is graph


def test_preseeded_release_run_admits_without_any_acquisition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "1")
    monkeypatch.setenv(oci_release_image.SOURCE_CLASS_ENV, "preseeded")
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: _RUNTIME)
    monkeypatch.setattr(docker_integration, "_locked_graphs", lambda: (_graph(),))
    monkeypatch.setattr(docker_integration.oci_release_image, "locked_repository", lambda: _REPOSITORY)
    pulls: list[object] = []
    monkeypatch.setattr(
        docker_integration.oci_release_image,
        "acquire_image",
        lambda *args, **kwargs: pulls.append(args),
    )
    monkeypatch.setattr(docker_integration.oci_release_image, "verify_daemon_image", lambda *a, **k: None)

    assert docker_integration._require_container_runtime().runtime == _RUNTIME
    # `acquire_image` is still called -- it is the one seam that decides -- and
    # it is what refuses to reach the network in a pre-seeded context.
    assert len(pulls) == 1


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("reason", ["acquisition-failed", "client-unavailable", "client-timeout"])
def test_unavailable_input_skips_only_when_optional(
    monkeypatch: pytest.MonkeyPatch,
    required: bool,
    reason: str,
) -> None:
    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "1" if required else "0")
    monkeypatch.delenv(oci_release_image.SOURCE_CLASS_ENV, raising=False)
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: _RUNTIME)
    monkeypatch.setattr(docker_integration, "_locked_graphs", lambda: (_graph(),))
    monkeypatch.setattr(docker_integration.oci_release_image, "locked_repository", lambda: _REPOSITORY)

    def _fail(*_args, **_kwargs):
        raise oci_release_image.ImageAdmissionError(reason)

    monkeypatch.setattr(docker_integration.oci_release_image, "acquire_image", _fail)
    expected = pytest.fail.Exception if required else pytest.skip.Exception

    with pytest.raises(expected, match="integration image is not available"):
        docker_integration._require_container_runtime()


@pytest.mark.parametrize("required", [False, True])
def test_integrity_failure_is_never_downgraded_to_a_skip(monkeypatch: pytest.MonkeyPatch, required: bool) -> None:
    """An availability failure may skip a local run; a wrong image may not."""

    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "1" if required else "0")
    monkeypatch.delenv(oci_release_image.SOURCE_CLASS_ENV, raising=False)
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: _RUNTIME)
    monkeypatch.setattr(docker_integration, "_locked_graphs", lambda: (_graph(),))
    monkeypatch.setattr(docker_integration.oci_release_image, "locked_repository", lambda: _REPOSITORY)
    monkeypatch.setattr(docker_integration.oci_release_image, "acquire_image", lambda *a, **k: None)

    def _mismatch(*_args, **_kwargs):
        raise oci_release_image.ImageAdmissionError("image-identity")

    monkeypatch.setattr(docker_integration.oci_release_image, "verify_daemon_image", _mismatch)

    with pytest.raises(pytest.fail.Exception, match="does not match the reviewed"):
        docker_integration._require_container_runtime()


@pytest.mark.parametrize("required", [False, True])
def test_misconfigured_source_class_always_fails(monkeypatch: pytest.MonkeyPatch, required: bool) -> None:
    monkeypatch.setenv(docker_integration._REQUIRED_MODE_ENV, "1" if required else "0")
    monkeypatch.setenv(oci_release_image.SOURCE_CLASS_ENV, "mirror")
    monkeypatch.delenv(oci_release_image.MIRROR_REPOSITORY_ENV, raising=False)
    monkeypatch.setattr(docker_integration, "_available_runtime", lambda: _RUNTIME)

    with pytest.raises(pytest.fail.Exception, match="reviewed OCI input is misconfigured"):
        docker_integration._require_container_runtime()


def test_each_run_gets_its_own_opaque_workspace() -> None:
    first = docker_integration.run_workspace("conf")
    second = docker_integration.run_workspace("conf")

    assert first != second
    assert first.startswith("raes-ref-it-conf-")
    # Bounded so the derived native names stay inside the runtime's limit.
    assert len(first) <= 40


class _FakeDriver:
    """A driver that reports what it realized and records its teardown."""

    def __init__(self, *, addresses: frozenset[str], diagnostics: tuple = ()) -> None:
        self.addresses = addresses
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self._diagnostics = diagnostics

    def realized_addresses(self) -> frozenset[str]:
        return self.addresses

    def destroy(self, *, networks: tuple[str, ...], containers: tuple[str, ...]):
        self.calls.append((networks, containers))
        return SimpleNamespace(diagnostics=self._diagnostics)


def _runtime_runner(names: str):
    def _run(argv, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=names, stderr="")

    return _run


def test_teardown_removes_what_the_driver_actually_realized() -> None:
    """A guessed address can be removed 'successfully' while the real one leaks.

    ``docker rm --force`` is idempotent, so tearing down an address that was
    never realized reports success and removes nothing. Teardown therefore
    derives its target set from the driver rather than from a caller's guess.
    """

    driver = _FakeDriver(addresses=frozenset({"provision.node.web", "provision.network.lan"}))

    with docker_integration.realized(driver, workspace="ws", runtime="docker", runner=_runtime_runner("")):
        pass

    assert driver.calls == [(("provision.network.lan",), ("provision.node.web",))]


def test_teardown_runs_on_both_the_success_and_failure_paths() -> None:
    torn_down: list[tuple[str, ...]] = []

    for body_fails in (False, True):
        driver = _FakeDriver(addresses=frozenset({"provision.node.web"}))
        context = docker_integration.realized(driver, workspace="ws", runtime="docker", runner=_runtime_runner(""))
        if body_fails:
            with pytest.raises(RuntimeError, match="body failed"), context:
                raise RuntimeError("body failed")
        else:
            with context:
                pass
        torn_down.extend(containers for _networks, containers in driver.calls)

    assert torn_down == [("provision.node.web",), ("provision.node.web",)]


def test_failed_teardown_is_reported_rather_than_swallowed() -> None:
    driver = _FakeDriver(
        addresses=frozenset({"provision.node.web"}),
        diagnostics=(SimpleNamespace(code="reference-backend.driver.command-failed"),),
    )

    with (
        pytest.raises(pytest.fail.Exception, match="teardown did not remove"),
        docker_integration.realized(driver, workspace="ws", runtime="docker", runner=_runtime_runner("")),
    ):
        pass


def test_a_resource_surviving_under_this_run_label_fails_the_run() -> None:
    """The proof of teardown is the runtime, not the removal command's exit code."""

    driver = _FakeDriver(addresses=frozenset({"provision.node.web"}))

    with (
        pytest.raises(pytest.fail.Exception, match="still owns"),
        docker_integration.realized(
            driver,
            workspace="ws",
            runtime="docker",
            runner=_runtime_runner("2b1c4d5e6f70\n"),
        ),
    ):
        pass


def test_the_survivor_probe_is_scoped_to_this_run_alone() -> None:
    """A concurrent run's resources must never be visible to this one's sweep."""

    seen: list[list[str]] = []

    def _runner(argv, **_kwargs):
        seen.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    driver = _FakeDriver(addresses=frozenset({"provision.node.web"}))
    with docker_integration.realized(driver, workspace="ws-9f3a", runtime="docker", runner=_runner):
        pass

    assert seen == [["docker", "ps", "--all", "--quiet", "--filter", "label=raes.workspace=ws-9f3a"]]
