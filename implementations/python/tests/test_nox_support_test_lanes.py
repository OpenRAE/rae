"""Direct command-construction tests for the nox test and qualification lanes."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def test_lanes(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the lane module against a stand-in nox; the project env has no nox."""

    monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
    for module_name in ("tools.nox_support.runner", "tools.nox_support.test_lanes"):
        # Registering the key makes monkeypatch remove the stand-in import afterward.
        monkeypatch.setitem(sys.modules, module_name, None)
        monkeypatch.delitem(sys.modules, module_name)
    return importlib.import_module("tools.nox_support.test_lanes")


class _Reporter:
    def __init__(self) -> None:
        self.stages: list[tuple[str, str]] = []

    def run(self, name: str, func: Callable[[], None], *, detail: str = "") -> None:
        self.stages.append((name, detail))
        func()


def _record_pytest(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType
) -> list[tuple[tuple[str, ...], dict[str, object]]]:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
    monkeypatch.setattr(module, "_run_pytest", lambda _session, *args, **kwargs: calls.append((args, kwargs)))
    return calls


def test_default_test_lane_runs_the_parallel_quiet_suite_with_coverage(
    monkeypatch: pytest.MonkeyPatch,
    test_lanes: ModuleType,
) -> None:
    calls = _record_pytest(monkeypatch, test_lanes)
    reporter = _Reporter()

    test_lanes._run_tests(object(), reporter, Path("coverage-file"), finalize_coverage=False)

    assert calls == [(("-q",), {"coverage_file": Path("coverage-file"), "finalize_coverage": False, "parallel": True})]
    assert reporter.stages == [("tests / pytest", "-q :: xdist auto, max 8, worksteal")]


def test_explicit_test_selection_runs_serially_with_the_selected_arguments(
    monkeypatch: pytest.MonkeyPatch,
    test_lanes: ModuleType,
) -> None:
    calls = _record_pytest(monkeypatch, test_lanes)
    reporter = _Reporter()

    test_lanes._run_tests(object(), reporter, Path("coverage-file"), ["tests/test_a.py", "-k", "case"])

    assert calls == [
        (
            ("tests/test_a.py", "-k", "case"),
            {"coverage_file": Path("coverage-file"), "finalize_coverage": True, "parallel": False},
        )
    ]
    assert reporter.stages == [("tests / pytest", "tests/test_a.py -k case :: explicit selection, serial")]


def test_fuzz_and_integration_lanes_select_their_markers_and_coverage(
    monkeypatch: pytest.MonkeyPatch,
    test_lanes: ModuleType,
) -> None:
    calls = _record_pytest(monkeypatch, test_lanes)
    reporter = _Reporter()

    test_lanes._run_fuzz(object(), reporter)
    test_lanes._run_integration_tests(
        object(),
        reporter,
        coverage_file=Path("integration-coverage"),
        append_coverage=True,
        finalize_coverage=True,
    )
    test_lanes._run_docker_integration_tests(SimpleNamespace(posargs=["--junitxml", "docker.xml"]), reporter)

    assert calls == [
        (("-m", "fuzz", "-v"), {}),
        (
            ("-m", "integration", "-v"),
            {"coverage_file": Path("integration-coverage"), "append_coverage": True, "finalize_coverage": True},
        ),
        (("-m", "docker", "-v", "--junitxml", "docker.xml"), {}),
    ]
    assert [name for name, _detail in reporter.stages] == [
        "tests / pytest fuzz",
        "tests / pytest integration",
        "tests / pytest docker integration",
    ]


@pytest.mark.parametrize("name", ["local-installation-qualification", "proof-input-qualification"])
def test_installation_qualification_lane_runs_its_harness_in_a_resolved_private_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_lanes: ModuleType,
    name: str,
) -> None:
    from tools.nox_support.config import INSTALLATION_QUALIFICATION_HARNESSES

    real_temporary = tmp_path / "real-temporary"
    real_temporary.mkdir()
    alias = tmp_path / "temporary-alias"
    alias.symlink_to(real_temporary, target_is_directory=True)
    invocations: list[tuple[str, ...]] = []
    restored: list[Path] = []

    def fake_run(_session: object, *args: str, **_kwargs: object) -> None:
        invocations.append(args)

    monkeypatch.setattr(test_lanes, "_run", fake_run)
    monkeypatch.setattr(test_lanes, "_restore_owner_write", restored.append)
    monkeypatch.setattr(test_lanes.tempfile, "tempdir", str(alias))
    reporter = _Reporter()

    test_lanes._run_installation_qualification(object(), reporter, name, ["--output", "evidence.json"])

    harness, detail = INSTALLATION_QUALIFICATION_HARNESSES[name]
    (invocation,) = invocations
    root = Path(invocation[2])
    assert invocation == (sys.executable, str(REPO_ROOT / harness), str(root), "--output", "evidence.json")
    assert "temporary-alias" not in root.parts
    assert real_temporary.resolve() in root.parents
    assert root.name == "root"
    assert len(restored) == 1
    assert restored[0].resolve() == root.parent
    assert reporter.stages == [(f"qualification / {name}", detail)]
    assert (REPO_ROOT / harness).is_file()


def test_failed_qualification_still_restores_owner_write_for_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_lanes: ModuleType,
) -> None:
    restored: list[Path] = []

    def failing_run(_session: object, *args: str, **_kwargs: object) -> None:
        raise RuntimeError("harness failed")

    monkeypatch.setattr(test_lanes, "_run", failing_run)
    monkeypatch.setattr(test_lanes, "_restore_owner_write", restored.append)
    monkeypatch.setattr(test_lanes.tempfile, "tempdir", str(tmp_path))

    session = object()
    reporter = _Reporter()
    with pytest.raises(RuntimeError, match="harness failed"):
        test_lanes._run_installation_qualification(session, reporter, "proof-input-qualification", [])
    assert len(restored) == 1
    assert restored[0].resolve().parent == tmp_path.resolve()


def test_restore_owner_write_reopens_sealed_directories_without_following_links(
    tmp_path: Path,
    test_lanes: ModuleType,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o500)
    root = tmp_path / "root"
    (root / "a" / "b").mkdir(parents=True)
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "a" / "b").chmod(0o500)
    (root / "a").chmod(0o500)

    test_lanes._restore_owner_write(root)

    assert (root / "a").stat().st_mode & 0o777 == 0o700
    assert (root / "a" / "b").stat().st_mode & 0o777 == 0o700
    assert outside.stat().st_mode & 0o777 == 0o500
    outside.chmod(0o700)


class _FakeSession:
    """Minimal nox.Session stand-in for the shard/reduce lane tests."""

    def __init__(self, run_output: str = "") -> None:
        self._run_output = run_output
        self.chdir_calls: list[object] = []

    def chdir(self, path: object):  # noqa: ANN201 - context manager stand-in
        import contextlib

        self.chdir_calls.append(path)
        return contextlib.nullcontext()

    def run(self, *args: object, **kwargs: object) -> str:
        return self._run_output


def test_shard_lane_constructs_the_deterministic_partition_invocation(
    monkeypatch: pytest.MonkeyPatch,
    test_lanes: ModuleType,
) -> None:
    calls = _record_pytest(monkeypatch, test_lanes)
    reporter = _Reporter()

    test_lanes._run_shard_tests(
        object(),
        reporter,
        Path("cov/.coverage.shard-1"),
        shard_count=4,
        shard_index=1,
        manifest_path=Path("cov/shard-1.json"),
        source_sha="deadbeef",
    )

    (args, kwargs) = calls[0]
    assert args == (
        "-q",
        "-p",
        "tools.pytest_shard_plugin",
        "--shard-count",
        "4",
        "--shard-index",
        "1",
        "--shard-manifest",
        "cov/shard-1.json",
        "--shard-source-sha",
        "deadbeef",
        "--shard-suite-expression",
        "not fuzz and not integration and not docker",
    )
    assert kwargs["coverage_file"] == Path("cov/.coverage.shard-1")
    assert kwargs["finalize_coverage"] is False
    assert kwargs["parallel"] is True
    assert kwargs["extra_env"] == {"PYTHONPATH": str(test_lanes.REPO_ROOT)}


def test_coverage_reduce_proves_completeness_before_combining(
    monkeypatch: pytest.MonkeyPatch,
    test_lanes: ModuleType,
    tmp_path: Path,
) -> None:
    from tools.pytest_shard import SHARD_ALGORITHM_VERSION, ShardManifest, owned_nodeids, write_manifest

    suite = [f"tests/test_m.py::t{index}" for index in range(20)]
    for index in range(2):
        write_manifest(
            tmp_path / f"shard-{index}.json",
            ShardManifest(
                algorithm_version=SHARD_ALGORITHM_VERSION,
                source_sha="sha1",
                suite_expression="expr",
                shard_count=2,
                shard_index=index,
                node_ids=tuple(owned_nodeids(suite, 2, index)),
            ),
        )

    monkeypatch.setattr(test_lanes, "_sync_project", lambda _session: None)
    monkeypatch.setattr(test_lanes, "_collect_canonical_nodeids", lambda _session: list(suite))
    events: list[object] = []
    monkeypatch.setattr(test_lanes, "_run", lambda *_a, **_k: events.append("combine"))
    monkeypatch.setattr(test_lanes, "_write_and_check_coverage", lambda *_a, **_k: events.append("report"))

    verify_calls: list[tuple[int, int, object]] = []
    real_verify = test_lanes.verify_shard_partition

    def _spy(manifests, canonical, *, shard_count, source_sha=None):  # noqa: ANN001, ANN202
        verify_calls.append((len(list(manifests)), shard_count, source_sha))
        events.append("proof")
        real_verify(manifests, canonical, shard_count=shard_count, source_sha=source_sha)

    monkeypatch.setattr(test_lanes, "verify_shard_partition", _spy)

    test_lanes._run_coverage_reduce(_FakeSession(), _Reporter(), tmp_path, shard_count=2, source_sha="sha1")

    assert verify_calls == [(2, 2, "sha1")]
    # The completeness proof must run before any combine/report work.
    assert events == ["proof", "combine", "report"]


def test_coverage_reduce_fails_closed_without_manifests(
    monkeypatch: pytest.MonkeyPatch,
    test_lanes: ModuleType,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(test_lanes, "_sync_project", lambda _session: None)
    combined: list[object] = []
    monkeypatch.setattr(test_lanes, "_run", lambda *_a, **_k: combined.append("combine"))

    session = _FakeSession()
    reporter = _Reporter()
    with pytest.raises(RuntimeError, match="no shard manifests"):
        test_lanes._run_coverage_reduce(session, reporter, tmp_path, shard_count=2, source_sha="x")

    assert combined == []


def test_collect_canonical_nodeids_parses_and_fails_closed(test_lanes: ModuleType) -> None:
    session = _FakeSession(run_output="tests/a.py::t1\ntests/a.py::t2\n2 tests collected\n")
    assert test_lanes._collect_canonical_nodeids(session) == ["tests/a.py::t1", "tests/a.py::t2"]

    empty_session = _FakeSession(run_output="0 tests collected\n")
    with pytest.raises(RuntimeError, match="no node ids"):
        test_lanes._collect_canonical_nodeids(empty_session)
