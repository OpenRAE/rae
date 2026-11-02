"""GOV-901 regression guards for issue #1111's exact-version fast path."""

from __future__ import annotations

import json
import logging
import os
import statistics
import subprocess
import sys
import types
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from unittest.mock import Mock

import pytest
import raes_cli.entrypoint as cli_entrypoint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = PROJECT_ROOT / "packages"
_FAST_PATH_CPU_BUDGET_SECONDS = 0.25
_PROBE_SAMPLES = 5


@pytest.fixture(autouse=True)
def restore_root_logging():
    """Remove the application handler that a delegated run installs on the root logger.

    The handler writes to the stderr stream of the test that created it, so a
    leaked handler would send later tests' records to a closed capture stream.
    """

    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_exact_version_arguments_bypass_typer_command_imports(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str,
) -> None:
    monkeypatch.delitem(sys.modules, "raes_cli.main", raising=False)
    monkeypatch.setattr(sys, "argv", ["raes", flag])

    cli_entrypoint.main()

    assert capsys.readouterr().out == f"raes {version('raes')}\n"
    assert "raes_cli.main" not in sys.modules


def test_exact_version_fallback_is_honest_sentinel(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(_distribution: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(cli_entrypoint, "version", _raise)
    monkeypatch.setattr(sys, "argv", ["raes", "--version"])

    cli_entrypoint.main()

    assert capsys.readouterr().out == "raes 0.0.0+unknown\n"


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--help"],
        ["processor", "--help"],
        ["--version", "unexpected"],
        ["-V", "unexpected"],
        ["--unknown"],
    ],
)
def test_every_non_exact_argument_shape_delegates_without_rewriting_argv(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    delegated = Mock(return_value=None)
    fake_main = types.ModuleType("raes_cli.main")
    fake_main.__dict__["app"] = delegated
    original_argv = ["raes", *arguments]
    monkeypatch.setitem(sys.modules, "raes_cli.main", fake_main)
    monkeypatch.setattr(sys, "argv", original_argv)

    cli_entrypoint.main()

    delegated.assert_called_once_with()
    assert sys.argv is original_argv


def _probe_environment() -> dict[str, str]:
    current_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath = str(PACKAGES_ROOT)
    if current_pythonpath:
        pythonpath = os.pathsep.join((pythonpath, current_pythonpath))
    return {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": pythonpath}


def _run_cpu_probe(script: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=_probe_environment(),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stderr.strip().splitlines()[-1])


@pytest.mark.integration
def test_source_exact_version_startup_stays_within_relative_and_absolute_budget() -> None:
    fast_script = """
import json
import sys
import time

started = time.process_time()
from raes_cli.entrypoint import main
sys.argv = ["raes", "--version"]
main()
print(json.dumps({
    "cpu_seconds": time.process_time() - started,
    "main_loaded": "raes_cli.main" in sys.modules,
    "heavy_loaded": any(
        name == prefix or name.startswith(prefix + ".")
        for name in sys.modules
        for prefix in ("raes_conformance", "raes_contracts", "raes_processor", "z3")
    ),
}), file=sys.stderr)
"""
    full_graph_script = """
import json
import time

started = time.process_time()
import raes_cli.main
print(json.dumps({"cpu_seconds": time.process_time() - started}), file=__import__("sys").stderr)
"""

    fast_results = [_run_cpu_probe(fast_script) for _ in range(_PROBE_SAMPLES)]
    full_graph_results = [_run_cpu_probe(full_graph_script) for _ in range(_PROBE_SAMPLES)]
    fast_median = statistics.median(float(result["cpu_seconds"]) for result in fast_results)
    full_graph_median = statistics.median(float(result["cpu_seconds"]) for result in full_graph_results)

    assert all(result["main_loaded"] is False for result in fast_results)
    assert all(result["heavy_loaded"] is False for result in fast_results)
    assert fast_median < _FAST_PATH_CPU_BUDGET_SECONDS
    assert fast_median < full_graph_median / 2
