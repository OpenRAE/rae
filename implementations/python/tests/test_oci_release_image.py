"""GOV-913 (#1223): source-class admission for the release-test OCI image.

Mirror-only and pre-seeded operation exist so a site with no route to the public
registry can still run the required lane. That guarantee is worth nothing if any
path can quietly fall back to a public pull, resolve a mutable tag, or accept an
image override, so those are the properties under test here.
"""

from __future__ import annotations

import subprocess

import pytest
from tools.oci_release_image import (
    ImageAdmissionError,
    SourceClass,
    acquire_image,
    export_layout,
    image_reference,
    import_layout_into_daemon,
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
    from tools.oci_image_layout import LockedPlatformGraph, OciDescriptor

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


def test_default_source_class_is_the_public_origin() -> None:
    source = resolve_source({})

    assert source.source_class is SourceClass.PUBLIC
    assert source.repository is None


def test_preseeded_operation_performs_no_acquisition() -> None:
    runner = _Runner()
    source = resolve_source({"RAES_OCI_SOURCE_CLASS": "preseeded"})

    acquire_image(source, "ignored", runtime="docker", runner=runner)

    assert runner.calls == []


def test_mirror_operation_pulls_only_from_the_configured_mirror() -> None:
    runner = _Runner()
    source = resolve_source({"RAES_OCI_SOURCE_CLASS": "mirror", "RAES_OCI_MIRROR_REPOSITORY": _MIRROR_REPOSITORY})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    acquire_image(source, reference, runtime="docker", runner=runner)

    assert reference == f"{_MIRROR_REPOSITORY}@{_INDEX_DIGEST}"
    assert runner.calls == [["docker", "pull", reference]]
    assert not any(_PUBLIC_REPOSITORY in " ".join(call) for call in runner.calls)


def test_failed_mirror_acquisition_never_retries_against_the_public_origin() -> None:
    runner = _Runner(returncode=1)
    source = resolve_source({"RAES_OCI_SOURCE_CLASS": "mirror", "RAES_OCI_MIRROR_REPOSITORY": _MIRROR_REPOSITORY})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    with pytest.raises(ImageAdmissionError) as excinfo:
        acquire_image(source, reference, runtime="docker", runner=runner)

    assert excinfo.value.reason == "acquisition-failed"
    assert len(runner.calls) == 1


def test_mirror_configuration_is_never_echoed_into_a_diagnostic() -> None:
    runner = _Runner(returncode=1)
    source = resolve_source({"RAES_OCI_SOURCE_CLASS": "mirror", "RAES_OCI_MIRROR_REPOSITORY": _MIRROR_REPOSITORY})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    with pytest.raises(ImageAdmissionError) as excinfo:
        acquire_image(source, reference, runtime="docker", runner=runner)

    assert _MIRROR_REPOSITORY not in str(excinfo.value)


@pytest.mark.parametrize(
    "repository",
    [
        "https://registry.internal.invalid/mirror/alpine",
        "user:token@registry.internal.invalid/mirror/alpine",
        "registry.internal.invalid/mirror/alpine:latest",
        "registry.internal.invalid/mirror/alpine@sha256:" + "ab" * 32,
        "registry.internal.invalid/mirror/alpine?token=secret",
        "",
    ],
)
def test_mirror_repository_must_be_a_bare_reviewed_reference(repository: str) -> None:
    with pytest.raises(ImageAdmissionError) as excinfo:
        resolve_source({"RAES_OCI_SOURCE_CLASS": "mirror", "RAES_OCI_MIRROR_REPOSITORY": repository})

    assert excinfo.value.reason == "mirror-configuration"


def test_mirror_class_without_a_configured_mirror_fails_closed() -> None:
    with pytest.raises(ImageAdmissionError) as excinfo:
        resolve_source({"RAES_OCI_SOURCE_CLASS": "mirror"})

    assert excinfo.value.reason == "mirror-configuration"


def test_unknown_source_class_fails_closed() -> None:
    with pytest.raises(ImageAdmissionError) as excinfo:
        resolve_source({"RAES_OCI_SOURCE_CLASS": "whatever-the-operator-typed"})

    assert excinfo.value.reason == "source-class"


def test_image_reference_is_always_digest_pinned() -> None:
    source = resolve_source({})

    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    assert reference == f"{_PUBLIC_REPOSITORY}@{_INDEX_DIGEST}"
    with pytest.raises(ImageAdmissionError) as excinfo:
        image_reference(_PUBLIC_REPOSITORY, "3.20.10", source)
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


def test_layout_export_and_import_use_fixed_bounded_client_argv(tmp_path) -> None:
    runner = _Runner()
    layout = tmp_path / "layout"

    export_layout(f"{_PUBLIC_REPOSITORY}@{_INDEX_DIGEST}", layout, runner=runner)
    import_layout_into_daemon(layout, "raes-release-test:preseeded", runner=runner)

    export_argv, import_argv = runner.calls
    assert export_argv[:2] == ["skopeo", "copy"]
    assert "--all" in export_argv and "--preserve-digests" in export_argv
    assert export_argv[-2] == f"docker://{_PUBLIC_REPOSITORY}@{_INDEX_DIGEST}"
    assert export_argv[-1] == f"oci:{layout}:release-test"
    assert import_argv[:2] == ["skopeo", "copy"]
    assert import_argv[-1] == "docker-daemon:raes-release-test:preseeded"


def test_client_invocations_never_inherit_ambient_registry_state() -> None:
    captured: dict[str, object] = {}

    def _runner(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    acquire_image(resolve_source({}), f"{_PUBLIC_REPOSITORY}@{_INDEX_DIGEST}", runtime="docker", runner=_runner)

    assert set(captured["env"]) == {"LC_ALL", "LANG", "PATH"}
    assert isinstance(captured["timeout"], int) and 0 < captured["timeout"] <= 900
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

    assert [graph.platform_id for graph in graphs] == ["linux-x86_64", "linux-arm64"]
    # One reviewed index binds every platform selection together.
    assert len({graph.index for graph in graphs}) == 1
    assert seen == [("3.20.10", "linux-x86_64"), ("3.20.10", "linux-arm64")]


def test_locked_platform_graphs_refuse_an_index_only_selection() -> None:
    from tools.oci_release_image import locked_platform_graphs

    with pytest.raises(ImageAdmissionError) as excinfo:
        locked_platform_graphs(loader=lambda **_kwargs: _locked_selection(None))

    assert excinfo.value.reason == "graph-unavailable"


def test_locked_platform_graphs_refuse_platforms_under_different_indexes() -> None:
    from tools.oci_release_image import locked_platform_graphs

    def _loader(*, platform_id: str, **_kwargs):
        document = dict(_GRAPH_DOCUMENT)
        if platform_id == "linux-arm64":
            document |= {"index": {"digest": "sha256:" + "ee" * 32, "size": 9226}}
        return _locked_selection(document)

    with pytest.raises(ImageAdmissionError) as excinfo:
        locked_platform_graphs(loader=_loader)

    assert excinfo.value.reason == "index-identity"


@pytest.mark.integration
def test_checked_in_lock_admits_the_release_test_image_for_every_required_platform() -> None:
    from tools.oci_release_image import REQUIRED_PLATFORM_IDS, locked_platform_graphs, locked_repository

    graphs = locked_platform_graphs()

    assert [graph.platform_id for graph in graphs] == list(REQUIRED_PLATFORM_IDS)
    assert len({graph.index for graph in graphs}) == 1
    assert {(graph.architecture, graph.os) for graph in graphs} == {("amd64", "linux"), ("arm64", "linux")}
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

    source = resolve_source({})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    with pytest.raises(ImageAdmissionError) as excinfo:
        acquire_image(source, reference, runtime="docker", runner=_runner)

    assert excinfo.value.reason == reason
    assert "no such client" not in str(excinfo.value)


def test_only_the_reviewed_container_runtimes_may_be_driven() -> None:
    source = resolve_source({})
    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    with pytest.raises(ImageAdmissionError) as excinfo:
        acquire_image(source, reference, runtime="rm -rf /", runner=_Runner())

    assert excinfo.value.reason == "runtime-not-allowed"


def test_preseeded_reference_is_the_reviewed_index_under_a_local_name() -> None:
    from tools.oci_release_image import PRESEED_LOCAL_REPOSITORY

    source = resolve_source({"RAES_OCI_SOURCE_CLASS": "preseeded"})

    reference = image_reference(_PUBLIC_REPOSITORY, _INDEX_DIGEST, source)

    # An imported image has no registry repo digest, so the local name carries
    # the reviewed index digest itself. It cannot float to other content, and
    # it is not an operator-supplied override.
    assert reference == f"{PRESEED_LOCAL_REPOSITORY}:{_INDEX_DIGEST.removeprefix('sha256:')}"


def test_export_refuses_to_run_in_a_preseeded_context() -> None:
    from tools.oci_release_image import export_command

    with pytest.raises(ImageAdmissionError) as excinfo:
        export_command(
            layout_root="/nonexistent",
            environ={"RAES_OCI_SOURCE_CLASS": "preseeded"},
            loader=lambda **_kwargs: None,
        )

    assert excinfo.value.reason == "source-class"


def test_import_verifies_the_layout_before_touching_the_daemon(tmp_path, monkeypatch) -> None:
    from tools import oci_release_image as module

    order: list[str] = []

    def _verify_layout(_root, _graphs):
        order.append("verify-layout")
        raise module.LayoutRejected("blob-corrupt")

    monkeypatch.setattr(module, "verify_layout", _verify_layout)
    monkeypatch.setattr(module, "import_layout_into_daemon", lambda *a, **k: order.append("import"))
    monkeypatch.setattr(module, "verify_daemon_image", lambda *a, **k: order.append("verify-daemon"))
    monkeypatch.setattr(module, "locked_platform_graphs", lambda **_k: (_graph(),))

    with pytest.raises(module.LayoutRejected):
        module.import_command(layout_root=tmp_path, runtime="docker", environ={})

    assert order == ["verify-layout"]


def test_import_admits_then_loads_then_reverifies(tmp_path, monkeypatch) -> None:
    from tools import oci_release_image as module

    order: list[str] = []
    monkeypatch.setattr(module, "verify_layout", lambda *a, **k: order.append("verify-layout"))
    monkeypatch.setattr(module, "import_layout_into_daemon", lambda *a, **k: order.append("import"))
    monkeypatch.setattr(module, "verify_daemon_image", lambda *a, **k: order.append("verify-daemon"))
    monkeypatch.setattr(module, "locked_platform_graphs", lambda **_k: (_graph(),))

    reference = module.import_command(layout_root=tmp_path, runtime="docker", environ={})

    assert order == ["verify-layout", "import", "verify-daemon"]
    assert reference == f"{module.PRESEED_LOCAL_REPOSITORY}:{_INDEX_DIGEST.removeprefix('sha256:')}"


@pytest.mark.integration
def test_module_is_runnable_as_a_script_from_the_repository_root() -> None:
    """The release lane invokes this file as a script, not as a package import.

    Run that way, `sys.path[0]` is `tools/` rather than the repository root, so
    the module's own package imports have to be made resolvable by the entry
    point itself.
    """

    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [sys.executable, "tools/oci_release_image.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "export" in completed.stdout and "import" in completed.stdout
