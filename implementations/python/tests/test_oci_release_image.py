"""Release-test image pins, native pulls, bounded clients, and daemon identity."""

from __future__ import annotations

import subprocess

import pytest
from tools.oci_release_image import (
    ImageAdmissionError,
    acquire_image,
    image_reference,
    resolve_source,
    verify_daemon_image,
)

_INDEX_DIGEST = "sha256:" + "d9" * 32
_PUBLIC_REPOSITORY = "docker.io/library/alpine"
_MIRROR_REPOSITORY = "registry.internal.invalid:5000/mirror/library/alpine"


class _Runner:
    def __init__(self, *, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(args=argv, returncode=self._returncode, stdout=self._stdout, stderr="")


def _graph(architecture: str = "amd64", diff_ids: tuple[str, ...] = ("sha256:" + "08" * 32,)):
    from tools.oci_release_selection import LockedPlatformGraph, OciDescriptor

    descriptor = OciDescriptor(digest=_INDEX_DIGEST, size=9226)
    return LockedPlatformGraph(
        platform_id="linux-x86_64",
        index=descriptor,
        manifest=OciDescriptor(digest="sha256:" + "c6" * 32, size=1023),
        config=OciDescriptor(digest="sha256:" + "bf" * 32, size=612),
        layers=(OciDescriptor(digest="sha256:" + "25" * 32, size=3630321),),
        diff_ids=diff_ids,
        architecture=architecture,
        os="linux",
    )


def test_unknown_source_class_fails_closed() -> None:
    with pytest.raises(ImageAdmissionError) as excinfo:
        resolve_source({"RAES_OCI_SOURCE_CLASS": "whatever-the-operator-typed"})

    assert excinfo.value.reason == "source-class"


def test_image_reference_is_always_digest_pinned() -> None:
    resolve_source({})

    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST)

    assert reference == f"{_PUBLIC_REPOSITORY}@{_INDEX_DIGEST}"
    with pytest.raises(ImageAdmissionError) as excinfo:
        image_reference(_PUBLIC_REPOSITORY, "3.20.10")
    assert excinfo.value.reason == "image-identity"


def test_daemon_readback_admits_only_the_locked_platform_identity() -> None:
    graph = _graph()
    runner = _Runner(stdout=f'amd64\nlinux\n["{graph.diff_ids[0]}"]\n')

    verify_daemon_image("ref", graph, runtime="docker", runner=runner)

    assert runner.calls[0][:3] == ["docker", "image", "inspect"]


@pytest.mark.parametrize(
    "stdout",
    [
        # Wrong architecture for the platform under test.
        'arm64\nlinux\n["sha256:{diff}"]\n',
        # Right platform, different filesystem content.
        'amd64\nlinux\n["sha256:{other}"]\n',
        # A daemon that reports nothing usable.
        "\n",
    ],
)
def test_daemon_readback_rejects_a_substituted_image(stdout: str) -> None:
    graph = _graph()
    payload = stdout.format(diff=graph.diff_ids[0].removeprefix("sha256:"), other="ff" * 32)
    runner = _Runner(stdout=payload)

    with pytest.raises(ImageAdmissionError) as excinfo:
        verify_daemon_image("ref", graph, runtime="docker", runner=runner)

    assert excinfo.value.reason == "image-identity"


def test_client_invocations_never_inherit_ambient_registry_state() -> None:
    captured: dict[str, object] = {}

    def _runner(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    acquire_image(f"{_PUBLIC_REPOSITORY}@{_INDEX_DIGEST}", runtime="docker", runner=_runner)

    assert set(captured["env"]) == {"LC_ALL", "LANG", "PATH"}
    assert isinstance(captured["timeout"], int)
    assert 0 < captured["timeout"] <= 900
    assert captured["check"] is False
    assert "shell" not in captured


def _locked_selection(oci_graph: dict | None) -> object:
    from tools.tooling_policy_gate import LockedArtifactSelection, LockedManifestEntry, locked_oci_graph

    return LockedArtifactSelection(
        artifact_id="release-test-alpine",
        version="3.20.10",
        platform_id="linux-x86_64",
        profile_id="public-linux-x86_64",
        repository="https://github.com/alpinelinux/docker-alpine",
        release=_INDEX_DIGEST,
        source_urls=("https://registry-1.docker.io/v2/library/alpine/manifests/" + _INDEX_DIGEST,),
        raw_manifest=(LockedManifestEntry(path="alpine-index.json", sha256="d9" * 32, size=9226),),
        installed_manifest=(),
        artifact_class="oci-image",
        policy_refs=("oci-graph-v1",),
        installed_identity=(("implementation", "OCI image"),),
        locator_refs=("docker-official-images-registry",),
        oci_graph=locked_oci_graph(oci_graph),
        asset=_PUBLIC_REPOSITORY,
    )


_GRAPH_DOCUMENT = {
    "index": {"digest": _INDEX_DIGEST, "size": 9226},
    "manifest": {"digest": "sha256:" + "c6" * 32, "size": 1023},
    "config": {"digest": "sha256:" + "bf" * 32, "size": 612},
    "layers": [{"digest": "sha256:" + "25" * 32, "size": 3630321}],
    "diff_ids": ["sha256:" + "08" * 32],
    "architecture": "amd64",
    "os": "linux",
}


def test_locked_platform_graphs_project_every_required_platform() -> None:
    from tools.oci_release_image import locked_platform_graphs

    seen: list[tuple[str, str]] = []

    def _loader(*, version: str, platform_id: str, profile_id: str):
        seen.append((version, platform_id))
        document = dict(_GRAPH_DOCUMENT)
        if platform_id == "linux-arm64":
            document |= {"architecture": "arm64", "manifest": {"digest": "sha256:" + "45" * 32, "size": 1026}}
        return _locked_selection(document)

    graphs = locked_platform_graphs(loader=_loader)

    assert [graph.platform_id for graph in graphs] == ["linux-x86_64"]
    # One reviewed index binds every platform selection together.
    assert len({graph.index for graph in graphs}) == 1
    assert seen == [("3.20.10", "linux-x86_64")]


def test_locked_platform_graphs_refuse_an_index_only_selection() -> None:
    from tools.oci_release_image import locked_platform_graphs

    with pytest.raises(ImageAdmissionError) as excinfo:
        locked_platform_graphs(loader=lambda **_kwargs: _locked_selection(None))

    assert excinfo.value.reason == "graph-unavailable"


@pytest.mark.integration
def test_checked_in_lock_admits_the_release_test_image_for_every_required_platform() -> None:
    from tools.oci_release_image import REQUIRED_PLATFORM_IDS, locked_platform_graphs, locked_repository

    graphs = locked_platform_graphs()

    assert [graph.platform_id for graph in graphs] == list(REQUIRED_PLATFORM_IDS)
    assert len({graph.index for graph in graphs}) == 1
    assert {(graph.architecture, graph.os) for graph in graphs} == {("amd64", "linux")}
    assert all(len(graph.layers) == len(graph.diff_ids) >= 1 for graph in graphs)
    assert locked_repository() == _PUBLIC_REPOSITORY


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (OSError("no such client"), "client-unavailable"),
        (subprocess.TimeoutExpired(cmd=["docker"], timeout=1), "client-timeout"),
    ],
)
def test_client_failures_are_classified_without_leaking_native_detail(failure, reason: str) -> None:
    def _runner(*_args, **_kwargs):
        raise failure

    resolve_source({})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST)

    with pytest.raises(ImageAdmissionError) as excinfo:
        acquire_image(reference, runtime="docker", runner=_runner)

    assert excinfo.value.reason == reason
    assert "no such client" not in str(excinfo.value)


def test_only_the_reviewed_container_runtimes_may_be_driven() -> None:
    resolve_source({})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST)

    runner = _Runner()

    with pytest.raises(ImageAdmissionError) as excinfo:
        acquire_image(reference, runtime="rm -rf /", runner=runner)

    assert excinfo.value.reason == "runtime-not-allowed"
