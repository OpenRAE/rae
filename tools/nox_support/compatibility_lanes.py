"""Python compatibility lane: exact runtime, distribution, and install smokes."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import nox

from tools.nox_support.config import (
    EXPECT_FREE_THREADED_ENV,
    EXPECTED_PYTHON_ENV,
    PROJECT_ROOT,
    PYTHON_CLOSURE_PROFILE_ENV,
    PYTHON_CLOSURE_WHEELHOUSE_ENV,
    PYTHON_COMPATIBILITY_SMOKE_ONLY_ENV,
    REPO_ROOT,
)
from tools.nox_support.runner import (
    SessionReporter,
    _run,
    _run_pytest,
    _sync_project,
)

_BUILD_CONSTRAINTS = "implementations/tooling/python/build-constraints.txt"
_SUPPORTED_FEATURE_RELEASES = frozenset({"3.11", "3.12", "3.13", "3.14"})

_RUNTIME_ASSERTION = """
import sys

expected = tuple(int(part) for part in sys.argv[1].split("."))
assert sys.implementation.name == "cpython", sys.implementation.name
assert sys.version_info[:2] == expected, (sys.version, expected)
is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
if sys.argv[2] == "1":
    assert callable(is_gil_enabled), "interpreter does not disclose GIL state"
    assert is_gil_enabled() is False, "interpreter is not free-threaded"
elif callable(is_gil_enabled):
    assert is_gil_enabled() is True, "standard lane selected a free-threaded interpreter"
print(sys.version)
"""

_INSTALLED_ASSERTION = """
import importlib
import sys
from importlib.metadata import metadata

from packaging.specifiers import SpecifierSet
from packaging.version import Version

expected = tuple(int(part) for part in sys.argv[1].split("."))
assert sys.version_info[:2] == expected, (sys.version, expected)
for module in (
    "raes",
    "raes_backend_libvirt",
    "raes_backend_protocols",
    "raes_backend_stubs",
    "raes_cli",
    "raes_conformance",
    "raes_contracts",
    "raes_mcp",
    "raes_operations",
    "raes_processor",
    "raes_reference_backend",
    "raes_runtime",
):
    importlib.import_module(module)
requires_python = metadata("raes")["Requires-Python"]
support = SpecifierSet(requires_python)
assert Version("3.11") in support
assert Version("3.14") in support
assert Version("3.15") not in support
"""


def _compatibility_runtime_stages(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    selector: str,
    expected: str,
    expect_free_threaded: bool,
    smoke_only: bool,
) -> None:
    restored_wheelhouse = os.environ.get(PYTHON_CLOSURE_WHEELHOUSE_ENV, "")
    if restored_wheelhouse:
        if not smoke_only:
            raise RuntimeError("a restored offline closure is valid only for compatibility smoke execution")
        reporter.skip(
            "python compatibility / frozen sync",
            "the verified restored wheelhouse is exercised by both installed-distribution smokes",
        )
        reporter.run(
            "python compatibility / exact runtime",
            lambda: _run(
                session,
                selector,
                "-c",
                _RUNTIME_ASSERTION,
                expected,
                "1" if expect_free_threaded else "0",
            ),
        )
        return
    reporter.run(
        "python compatibility / frozen sync",
        lambda: _sync_project(session),
        detail=f"selector={selector}",
    )
    reporter.run(
        "python compatibility / exact runtime",
        lambda: _run(
            session,
            "uv",
            "run",
            "--project",
            str(PROJECT_ROOT),
            "--all-extras",
            "--frozen",
            "python",
            "-c",
            _RUNTIME_ASSERTION,
            expected,
            "1" if expect_free_threaded else "0",
        ),
    )
    if not smoke_only:
        reporter.run(
            "python compatibility / hermetic tests",
            lambda: _run_pytest(session, "-q", parallel=True),
            detail="xdist auto, max 8, worksteal",
        )


def _uv_build(
    session: nox.Session,
    *,
    selector: str,
    kind: str,
    out_dir: Path,
    target: Path,
) -> None:
    """Run one constrained uv build of the project or a source distribution."""

    _run(
        session,
        "uv",
        "build",
        kind,
        "--python",
        selector,
        "--build-constraints",
        str(REPO_ROOT / _BUILD_CONSTRAINTS),
        "--require-hashes",
        "--out-dir",
        str(out_dir),
        str(target),
    )


def _build_compatibility_distributions(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    selector: str,
    dist_dir: Path,
) -> tuple[Path, Path]:
    """Build the wheel, the sdist, and the wheel rebuilt from that sdist."""

    reporter.run(
        "python compatibility / build distributions",
        lambda: (
            _uv_build(session, selector=selector, kind="--wheel", out_dir=dist_dir, target=PROJECT_ROOT),
            _uv_build(session, selector=selector, kind="--sdist", out_dir=dist_dir, target=PROJECT_ROOT),
        ),
    )
    wheels = sorted(dist_dir.glob("raes-*.whl"))
    source_distributions = sorted(dist_dir.glob("raes-*.tar.gz"))
    if len(wheels) != 1 or len(source_distributions) != 1:
        raise RuntimeError("compatibility build must produce exactly one wheel and one source distribution")
    reporter.run(
        "python compatibility / build wheel from sdist",
        lambda: _uv_build(
            session,
            selector=selector,
            kind="--wheel",
            out_dir=dist_dir / "from-sdist",
            target=source_distributions[0],
        ),
    )
    sdist_wheels = sorted((dist_dir / "from-sdist").glob("raes-*.whl"))
    if len(sdist_wheels) != 1:
        raise RuntimeError("compatibility sdist build must produce exactly one wheel")
    return wheels[0], sdist_wheels[0]


@dataclass(frozen=True)
class _InstalledCandidate:
    """One candidate distribution and where it is installed for verification."""

    label: str
    candidate: Path
    environment_dir: Path


def _verify_compatibility_install(
    session: nox.Session,
    reporter: SessionReporter,
    installed: _InstalledCandidate,
    *,
    wheelhouse: Path,
    profile_id: str,
    expected: str,
) -> None:
    """Install one candidate distribution offline and exercise the installed surface."""

    label = installed.label
    candidate = installed.candidate
    environment_dir = installed.environment_dir

    reporter.run(
        f"python compatibility / install {label}",
        lambda: _run(
            session,
            sys.executable,
            "-m",
            "tools.python_closure",
            "smoke",
            "--profile",
            profile_id,
            "--candidate",
            str(candidate),
            "--environment",
            str(environment_dir),
            "--wheelhouse",
            str(wheelhouse),
            "--offline",
        ),
    )
    scripts_dir = environment_dir / ("Scripts" if os.name == "nt" else "bin")
    python = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    raes = scripts_dir / ("raes.exe" if os.name == "nt" else "raes")
    reporter.run(
        f"python compatibility / {label} metadata and imports",
        lambda: _run(session, str(python), "-c", _INSTALLED_ASSERTION, expected),
    )
    reporter.run(
        f"python compatibility / {label} CLI version",
        lambda: _run(session, str(raes), "--version"),
    )
    reporter.run(
        f"python compatibility / {label} CLI help",
        lambda: _run(session, str(raes), "--help"),
    )


def _compatibility_distribution_stages(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    selector: str,
    expected: str,
) -> None:
    profile_id = os.environ.get(PYTHON_CLOSURE_PROFILE_ENV, "")
    if not profile_id:
        raise RuntimeError(f"{PYTHON_CLOSURE_PROFILE_ENV} must select a reviewed closure profile")
    with tempfile.TemporaryDirectory(prefix="raes-python-compatibility-") as temporary_dir:
        root = Path(temporary_dir)
        dist_dir = root / "dist"
        configured_wheelhouse = os.environ.get(PYTHON_CLOSURE_WHEELHOUSE_ENV, "")
        wheelhouse = Path(configured_wheelhouse) if configured_wheelhouse else root / "wheelhouse"
        wheel, sdist_wheel = _build_compatibility_distributions(
            session,
            reporter,
            selector=selector,
            dist_dir=dist_dir,
        )
        wheelhouse_operation = "wheelhouse-verify" if configured_wheelhouse else "materialize"
        reporter.run(
            f"python compatibility / {wheelhouse_operation} dependency wheelhouse",
            lambda: _run(
                session,
                sys.executable,
                "-m",
                "tools.python_closure",
                wheelhouse_operation,
                "--profile",
                profile_id,
                "--wheelhouse",
                str(wheelhouse),
            ),
        )
        for label, candidate, environment_dir in (
            ("direct wheel", wheel, root / "installed-direct"),
            ("sdist-built wheel", sdist_wheel, root / "installed-from-sdist"),
        ):
            _verify_compatibility_install(
                session,
                reporter,
                _InstalledCandidate(label=label, candidate=candidate, environment_dir=environment_dir),
                wheelhouse=wheelhouse,
                profile_id=profile_id,
                expected=expected,
            )


def _run_python_compatibility(session: nox.Session, reporter: SessionReporter) -> None:
    expected = os.environ.get(EXPECTED_PYTHON_ENV, "")
    selector = os.environ.get("UV_PYTHON", "")
    if expected not in _SUPPORTED_FEATURE_RELEASES:
        raise RuntimeError(f"{EXPECTED_PYTHON_ENV} must select a supported feature release")
    if not selector:
        raise RuntimeError("UV_PYTHON must select the interpreter under test")
    expect_free_threaded = os.environ.get(EXPECT_FREE_THREADED_ENV) == "1"
    profile_id = os.environ.get(PYTHON_CLOSURE_PROFILE_ENV, "")
    if not expect_free_threaded and f"cp{expected.replace('.', '')}" not in profile_id:
        raise RuntimeError(f"{PYTHON_CLOSURE_PROFILE_ENV} must match the selected interpreter")
    smoke_only_value = os.environ.get(PYTHON_COMPATIBILITY_SMOKE_ONLY_ENV, "0")
    if smoke_only_value not in {"0", "1"}:
        raise RuntimeError(f"{PYTHON_COMPATIBILITY_SMOKE_ONLY_ENV} must be 0 or 1")
    # Nox removes UV_PYTHON inherited from the parent process. Put the
    # matrix selector back into the per-session command environment so every
    # nested uv invocation uses the interpreter that the lane names.
    session.env["UV_PYTHON"] = selector
    _compatibility_runtime_stages(
        session,
        reporter,
        selector=selector,
        expected=expected,
        expect_free_threaded=expect_free_threaded,
        smoke_only=smoke_only_value == "1",
    )
    if expect_free_threaded:
        reporter.skip(
            "python compatibility / distribution closure",
            "the free-threaded interpreter is an advisory preview, not a release closure target",
        )
        return
    _compatibility_distribution_stages(session, reporter, selector=selector, expected=expected)


__all__ = ("_run_python_compatibility",)
