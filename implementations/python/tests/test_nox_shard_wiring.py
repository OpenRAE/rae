"""Wiring tests for the #935 shard/reduce/fast-feedback nox sessions.

These import the lane graph and the noxfile session registry against a stand-in
``nox`` (the project env has no nox) and assert each session delegates to the
right lane helper with the right arguments, so the CI-only session wrappers are
covered without a real nox run.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from types import ModuleType, SimpleNamespace

import pytest
from tools.verification_plan import ChangeRecord


class _Reporter:
    def __init__(self) -> None:
        self.ran: list[str] = []
        self.skipped: list[tuple[str, str]] = []

    def run(self, name: str, func: Callable[[], None], *, detail: str = "") -> None:
        self.ran.append(name)
        func()

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append((name, reason))

    def summary(self) -> None:  # noqa: D401 - stand-in
        pass


class _Session:
    def __init__(self) -> None:
        self.posargs: list[str] = []
        self.logs: list[str] = []

    def log(self, message: str) -> None:
        self.logs.append(message)


def _stub_nox(monkeypatch: pytest.MonkeyPatch) -> None:
    def _session(*d_args: object, **_d_kwargs: object) -> object:
        if len(d_args) == 1 and callable(d_args[0]):
            return d_args[0]
        return lambda func: func

    nox_stub = SimpleNamespace(session=_session, options=SimpleNamespace(), Session=object)
    monkeypatch.setitem(sys.modules, "nox", nox_stub)
    for name in [n for n in sys.modules if n == "noxfile" or n.startswith("tools.nox_support")]:
        monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    _stub_nox(monkeypatch)
    return importlib.import_module("tools.nox_support.graph")


@pytest.fixture
def noxfile_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    _stub_nox(monkeypatch)
    return importlib.import_module("noxfile")


def test_fast_feedback_runs_changed_test_modules(monkeypatch: pytest.MonkeyPatch, graph: ModuleType) -> None:
    changed = [ChangeRecord(status="A", path="implementations/python/tests/test_x.py")]
    monkeypatch.setattr(graph, "collect_git_changes", lambda _root, _base: changed)
    monkeypatch.setattr(graph, "_requirement_aware_policy_args", lambda *args: list(args))
    calls: list[str] = []
    monkeypatch.setattr(graph, "_run_hygiene", lambda *a, **k: calls.append("hygiene"))
    monkeypatch.setattr(graph, "_run_policy", lambda *a, **k: calls.append("policy"))
    monkeypatch.setattr(graph, "_run_changed_lint", lambda *a, **k: calls.append("lint"))
    pytest_args: list[tuple[str, ...]] = []
    monkeypatch.setattr(graph, "_run_pytest", lambda _session, *args, **_k: pytest_args.append(args))

    reporter = _Reporter()
    graph._run_fast_feedback(_Session(), reporter, ["--base-rev", "BASE"])

    assert calls == ["hygiene", "policy", "lint"]
    assert pytest_args == [("implementations/python/tests/test_x.py", "-q")]


def test_fast_feedback_defers_when_no_test_module_changed(monkeypatch: pytest.MonkeyPatch, graph: ModuleType) -> None:
    changed = [ChangeRecord(status="M", path="implementations/python/packages/raes/x.py")]
    monkeypatch.setattr(graph, "collect_git_changes", lambda _root, _base: changed)
    monkeypatch.setattr(graph, "_requirement_aware_policy_args", lambda *args: list(args))
    monkeypatch.setattr(graph, "_run_hygiene", lambda *a, **k: None)
    monkeypatch.setattr(graph, "_run_policy", lambda *a, **k: None)
    monkeypatch.setattr(graph, "_run_changed_lint", lambda *a, **k: None)
    monkeypatch.setattr(graph, "_run_pytest", lambda *a, **k: pytest.fail("must not run tests when none changed"))

    reporter = _Reporter()
    graph._run_fast_feedback(_Session(), reporter, ["--base-rev", "BASE"])

    assert any("no authoritative targeted selection" in reason for _name, reason in reporter.skipped)


def test_verify_shard_session_delegates(monkeypatch: pytest.MonkeyPatch, noxfile_module: ModuleType) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        noxfile_module,
        "_run_shard_tests",
        lambda _session, _reporter, coverage_file, **kwargs: captured.update(
            {"coverage_file": coverage_file, **kwargs}
        ),
    )
    monkeypatch.setenv("RAES_SHARD_COUNT", "4")
    monkeypatch.setenv("RAES_SHARD_INDEX", "1")
    monkeypatch.setenv("RAES_VERIFY_COVERAGE_FILE", "/tmp/out/.coverage.shard-1")
    monkeypatch.setenv("RAES_SHARD_MANIFEST", "/tmp/out/shard-1.json")
    monkeypatch.setenv("RAES_SHARD_SOURCE_SHA", "abc123")

    noxfile_module.verify_shard(_Session())

    assert captured["shard_count"] == 4
    assert captured["shard_index"] == 1
    assert str(captured["coverage_file"]) == "/tmp/out/.coverage.shard-1"
    assert str(captured["manifest_path"]) == "/tmp/out/shard-1.json"
    assert captured["source_sha"] == "abc123"


def test_verify_coverage_reduce_session_delegates(monkeypatch: pytest.MonkeyPatch, noxfile_module: ModuleType) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        noxfile_module,
        "_run_coverage_reduce",
        lambda _session, _reporter, reduce_dir, **kwargs: captured.update({"reduce_dir": reduce_dir, **kwargs}),
    )
    monkeypatch.setenv("RAES_COVERAGE_REDUCE_DIR", "/tmp/reduce")
    monkeypatch.setenv("RAES_SHARD_COUNT", "4")
    monkeypatch.setenv("RAES_SHARD_SOURCE_SHA", "def456")

    noxfile_module.verify_coverage_reduce(_Session())

    assert str(captured["reduce_dir"]) == "/tmp/reduce"
    assert captured["shard_count"] == 4
    assert captured["source_sha"] == "def456"


def test_verify_fast_feedback_session_delegates(monkeypatch: pytest.MonkeyPatch, noxfile_module: ModuleType) -> None:
    calls: list[object] = []
    monkeypatch.setattr(noxfile_module, "_run_fast_feedback", lambda *a, **k: calls.append(a))
    noxfile_module.verify_fast_feedback(_Session())
    assert len(calls) == 1


def test_required_env_helpers_fail_closed(monkeypatch: pytest.MonkeyPatch, noxfile_module: ModuleType) -> None:
    monkeypatch.delenv("RAES_SHARD_COUNT", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        noxfile_module._required_env("RAES_SHARD_COUNT")

    monkeypatch.setenv("RAES_SHARD_COUNT", "not-an-int")
    with pytest.raises(RuntimeError, match="must be an integer"):
        noxfile_module._required_env_int("RAES_SHARD_COUNT")
