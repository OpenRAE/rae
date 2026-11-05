#!/usr/bin/env python3
# ruff: noqa: E402
"""Run one exact pytest case and report its outcome as one JSON object.

The Ground Control design review runs this as ``workflow.design.acceptance_command``.
Stdin holds one JSON object with ``test_file`` (a repository-relative path in the
pytest project ``implementations/python``) and ``test_name``. The name matches a
collected case when it equals the case name, such as ``test_x`` or ``test_x[a]``,
or the node id after the file, such as ``TestY::test_x``.

Stdout holds one JSON object with ``test_name``, ``status``, ``matches`` and
``message``. Pytest output goes to stderr. A valid observation exits 0. An input
or runner failure exits 1 and writes the reason to stderr.

Status values:

- ``failed``: one case ran and its test body failed.
- ``passed``: one case ran and passed.
- ``missing``: no case, or more than one case, has the exact name.
- ``skipped``: the case was skipped, was an expected failure, or the default
  marker expression deselected it.
- ``broken``: the file did not collect, setup or teardown failed, or the test
  body raised ``SyntaxError``, ``NameError`` or ``ImportError``.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT / "implementations" / "python"
if str(PROJECT_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "packages"))

from raes_contracts.errors import InvalidInputError, OperationalError
from raes_contracts.operational_logging import run_application

MAX_INPUT_BYTES = 16 * 1024
MAX_MESSAGE_CHARS = 6000
# A test body that raises one of these did not run against the behavior, so the
# case cannot show a failing assertion.
BROKEN_EXCEPTIONS = (SyntaxError, NameError, ImportError)
_RUNNER_FAILURES = (pytest.ExitCode.INTERRUPTED, pytest.ExitCode.INTERNAL_ERROR, pytest.ExitCode.USAGE_ERROR)


def read_request(text: str) -> tuple[Path, str]:
    """Return the resolved test file and the exact test name from the request text."""

    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise InvalidInputError("acceptance input is too large")
    try:
        request = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidInputError("acceptance input must be JSON") from exc
    if not isinstance(request, dict) or set(request) != {"test_file", "test_name"}:
        raise InvalidInputError("acceptance input must hold only test_file and test_name")
    test_file, test_name = request["test_file"], request["test_name"]
    if not isinstance(test_file, str) or not test_file or not isinstance(test_name, str) or not test_name:
        raise InvalidInputError("test_file and test_name must be non-empty strings")
    return resolve_test_file(test_file), test_name


def resolve_test_file(test_file: str) -> Path:
    """Return the regular, non-symlink Python file inside the pytest project."""

    relative = Path(test_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise InvalidInputError("test_file must be a repository-relative path")
    path = REPO_ROOT / relative
    if path.is_symlink() or not path.is_file() or path.suffix != ".py":
        raise InvalidInputError("test_file must be a regular Python file")
    resolved = path.resolve()
    if resolved != path.absolute() or not resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise InvalidInputError("test_file must be in implementations/python")
    return resolved


def bounded(text: str) -> str:
    """Keep the head and the tail of ``text`` within the message limit."""

    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    marker = "\n...\n"
    half = (MAX_MESSAGE_CHARS - len(marker)) // 2
    return text[:half] + marker + text[-half:]


def classify_failure(when: str, exception_type: type[BaseException] | None) -> str:
    """Return ``failed`` for a failing test body and ``broken`` for every other failure."""

    if when != "call" or exception_type is None or issubclass(exception_type, BROKEN_EXCEPTIONS):
        return "broken"
    return "failed"


@dataclass
class CaseResult:
    status: str = "passed"
    message: str = ""


@dataclass
class Observer:
    """Pytest plugin that selects the exact case and records its reports."""

    test_name: str
    collection_errors: list[str] = field(default_factory=list)
    marker_deselected: int = 0
    cases: dict[str, CaseResult] = field(default_factory=dict)
    exception_types: dict[str, type[BaseException]] = field(default_factory=dict)

    def matches(self, item: pytest.Item) -> bool:
        return item.name == self.test_name or item.nodeid.partition("::")[2] == self.test_name

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self.marker_deselected += sum(1 for item in items if self.matches(item))

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            self.collection_errors.append(report.longreprtext)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config: pytest.Config, items: list[pytest.Item]) -> None:
        # trylast: the default marker expression has already deselected its cases.
        others = [item for item in items if not self.matches(item)]
        if others:
            config.hook.pytest_deselected(items=others)
            items[:] = [item for item in items if self.matches(item)]

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[None]
    ) -> Generator[None, pytest.TestReport, pytest.TestReport]:
        if call.when == "call" and call.excinfo is not None:
            self.exception_types[item.nodeid] = call.excinfo.type
        return (yield)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        case = self.cases.setdefault(report.nodeid, CaseResult())
        if case.status != "passed":
            return
        if hasattr(report, "wasxfail"):
            case.status, case.message = "skipped", "The acceptance case is marked as an expected failure."
        elif report.skipped:
            case.status, case.message = "skipped", "The acceptance case was skipped."
        elif report.failed:
            case.status = classify_failure(report.when, self.exception_types.get(report.nodeid))
            case.message = bounded(report.longreprtext)


def observation(observer: Observer) -> dict[str, object]:
    """Reduce the recorded reports to one observation."""

    matches = len(observer.cases)
    if observer.collection_errors:
        status, message = "broken", bounded("\n".join(observer.collection_errors))
    elif matches == 1:
        case = next(iter(observer.cases.values()))
        status, message = case.status, case.message
    elif matches > 1:
        status, message = "missing", f"{matches} executed cases have the exact name."
    elif observer.marker_deselected:
        status, message = "skipped", "The default marker expression deselected the acceptance case."
    else:
        status, message = "missing", "No collected case has the exact name."
    return result(observer.test_name, status, matches, message)


def result(test_name: str, status: str, matches: int, message: str) -> dict[str, object]:
    return {"test_name": test_name, "status": status, "matches": matches, "message": message}


def observe(test_file: Path, test_name: str) -> dict[str, object]:
    """Run the exact case in the pytest project and return the observation."""

    observer = Observer(test_name)
    args = ["-p", "no:cacheprovider", "-q", str(test_file)]
    previous = Path.cwd()
    os.chdir(PROJECT_ROOT)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            exit_code = pytest.main(args, plugins=[observer])
    finally:
        os.chdir(previous)
    if exit_code in _RUNNER_FAILURES and not observer.collection_errors:
        raise OperationalError(f"pytest stopped with exit code {int(exit_code)}")
    return observation(observer)


def main() -> int:
    try:
        test_file, test_name = read_request(sys.stdin.read(MAX_INPUT_BYTES + 1))
        report = observe(test_file, test_name)
    except (InvalidInputError, OperationalError) as exc:
        print(f"design-acceptance: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(report) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
