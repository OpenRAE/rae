"""Test, compatibility, coverage, integration, scan, and docs lanes."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import nox

from tools.nox_support.config import (
    DOCS_BUILD_ROOT,
    EXPECT_FREE_THREADED_ENV,
    EXPECTED_PYTHON_ENV,
    OSV_LOCKFILE_PATH,
    OSV_REPORT_PATH,
    PROJECT_ROOT,
    PUBLIC_DOCS_ENTRYPOINTS,
    PUBLIC_DOCS_EXAMPLE_TESTS,
    PUBLIC_DOCS_ROOT,
    PYTHON_CLOSURE_PROFILE_ENV,
    PYTHON_CLOSURE_WHEELHOUSE_ENV,
    PYTHON_COMPATIBILITY_SMOKE_ONLY_ENV,
    REPO_ROOT,
)
from tools.nox_support.runner import (
    SessionReporter,
    _run,
    _run_project_python,
    _run_pytest,
    _sync_project,
    _write_and_check_coverage,
)
from tools.osv_scanner_tool import (
    OSVScanOutcome,
    classify_osv_exit_code,
    ensure_osv_scanner,
    run_osv_scanner,
)
from tools.vale_tool import ensure_vale


def _run_tests(
    session: nox.Session,
    reporter: SessionReporter,
    coverage_file: Path,
    posargs: list[str] | None = None,
    *,
    finalize_coverage: bool = True,
) -> None:
    args = list(posargs) if posargs else ["-q"]
    parallel = not posargs
    execution = "xdist auto, max 8, worksteal" if parallel else "explicit selection, serial"
    reporter.run(
        "tests / pytest",
        lambda: _run_pytest(
            session,
            *args,
            coverage_file=coverage_file,
            finalize_coverage=finalize_coverage,
            parallel=parallel,
        ),
        detail=f"{' '.join(args)} :: {execution}",
    )


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


def _compatibility_distribution_stages(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    selector: str,
    expected: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="raes-python-compatibility-") as temporary_dir:
        root = Path(temporary_dir)
        dist_dir = root / "dist"
        configured_wheelhouse = os.environ.get(PYTHON_CLOSURE_WHEELHOUSE_ENV, "")
        wheelhouse = Path(configured_wheelhouse) if configured_wheelhouse else root / "wheelhouse"
        direct_environment = root / "installed-direct"
        sdist_environment = root / "installed-from-sdist"
        profile_id = os.environ.get(PYTHON_CLOSURE_PROFILE_ENV, "")
        if not profile_id:
            raise RuntimeError(f"{PYTHON_CLOSURE_PROFILE_ENV} must select a reviewed closure profile")

        reporter.run(
            "python compatibility / build distributions",
            lambda: (
                _run(
                    session,
                    "uv",
                    "build",
                    "--wheel",
                    "--python",
                    selector,
                    "--build-constraints",
                    str(REPO_ROOT / "implementations/tooling/python/build-constraints.txt"),
                    "--require-hashes",
                    "--out-dir",
                    str(dist_dir),
                    str(PROJECT_ROOT),
                ),
                _run(
                    session,
                    "uv",
                    "build",
                    "--sdist",
                    "--python",
                    selector,
                    "--build-constraints",
                    str(REPO_ROOT / "implementations/tooling/python/build-constraints.txt"),
                    "--require-hashes",
                    "--out-dir",
                    str(dist_dir),
                    str(PROJECT_ROOT),
                ),
            ),
        )
        wheels = sorted(dist_dir.glob("raes-*.whl"))
        source_distributions = sorted(dist_dir.glob("raes-*.tar.gz"))
        if len(wheels) != 1 or len(source_distributions) != 1:
            raise RuntimeError("compatibility build must produce exactly one wheel and one source distribution")
        reporter.run(
            "python compatibility / build wheel from sdist",
            lambda: _run(
                session,
                "uv",
                "build",
                "--wheel",
                "--python",
                selector,
                "--build-constraints",
                str(REPO_ROOT / "implementations/tooling/python/build-constraints.txt"),
                "--require-hashes",
                "--out-dir",
                str(dist_dir / "from-sdist"),
                str(source_distributions[0]),
            ),
        )
        sdist_wheels = sorted((dist_dir / "from-sdist").glob("raes-*.whl"))
        if len(sdist_wheels) != 1:
            raise RuntimeError("compatibility sdist build must produce exactly one wheel")
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
            ("direct wheel", wheels[0], direct_environment),
            ("sdist-built wheel", sdist_wheels[0], sdist_environment),
        ):
            reporter.run(
                f"python compatibility / install {label}",
                lambda candidate=candidate, environment_dir=environment_dir: _run(
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
                lambda python=python: _run(session, str(python), "-c", _INSTALLED_ASSERTION, expected),
            )
            reporter.run(
                f"python compatibility / {label} CLI version",
                lambda raes=raes: _run(session, str(raes), "--version"),
            )
            reporter.run(
                f"python compatibility / {label} CLI help",
                lambda raes=raes: _run(session, str(raes), "--help"),
            )


def _run_python_compatibility(session: nox.Session, reporter: SessionReporter) -> None:
    expected = os.environ.get(EXPECTED_PYTHON_ENV, "")
    selector = os.environ.get("UV_PYTHON", "")
    if expected not in {"3.11", "3.12", "3.13", "3.14"}:
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


def _run_fuzz(session: nox.Session, reporter: SessionReporter) -> None:
    reporter.run(
        "tests / pytest fuzz",
        lambda: _run_pytest(session, "-m", "fuzz", "-v"),
    )


def _run_integration_tests(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    coverage_file: Path | None = None,
    append_coverage: bool = False,
    finalize_coverage: bool = False,
) -> None:
    reporter.run(
        "tests / pytest integration",
        lambda: _run_pytest(
            session,
            "-m",
            "integration",
            "-v",
            coverage_file=coverage_file,
            append_coverage=append_coverage,
            finalize_coverage=finalize_coverage,
        ),
    )


def _finalize_parallel_coverage(session: nox.Session, coverage_dir: Path) -> None:
    coverage_file = coverage_dir / ".coverage"
    coverage_env = {"COVERAGE_FILE": str(coverage_file)}
    with session.chdir(PROJECT_ROOT):
        _run(
            session,
            "uv",
            "run",
            "--frozen",
            "coverage",
            "combine",
            "--keep",
            str(coverage_dir),
            env=coverage_env,
        )
        _write_and_check_coverage(session, coverage_env)


def _run_docker_integration_tests(session: nox.Session, reporter: SessionReporter) -> None:
    reporter.run(
        "tests / pytest docker integration",
        lambda: _run_pytest(session, "-m", "docker", "-v", *session.posargs),
    )


def _run_osv_scan(_session: nox.Session, reporter: SessionReporter) -> None:
    def _scan() -> None:
        lockfile = OSV_LOCKFILE_PATH
        if not lockfile.exists():
            raise RuntimeError(f"osv-scan: tracked lockfile not found: {lockfile.relative_to(REPO_ROOT)}")
        binary = ensure_osv_scanner(REPO_ROOT)
        exit_code = run_osv_scanner(lockfile, OSV_REPORT_PATH, binary=binary)
        report_rel = OSV_REPORT_PATH.relative_to(REPO_ROOT)
        outcome = classify_osv_exit_code(exit_code)
        if outcome is OSVScanOutcome.FINDINGS:
            raise RuntimeError(f"osv-scanner reported vulnerabilities (exit code {exit_code}); see {report_rel}")
        if outcome is OSVScanOutcome.SCANNER_ERROR:
            raise RuntimeError(
                f"osv-scanner failed with scanner/setup error exit code {exit_code}; report at {report_rel}"
            )

    reporter.run(
        "osv-scan / uv.lock",
        _scan,
        detail=str(OSV_LOCKFILE_PATH.relative_to(REPO_ROOT)),
    )


def _run_docs(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    include_external_links: bool = True,
) -> None:
    _sync_project(session)
    html_dir = DOCS_BUILD_ROOT / "html"
    linkcheck_dir = DOCS_BUILD_ROOT / "linkcheck"

    def _build(builder: str, output_dir: Path, *, clean: bool = False) -> None:
        if clean:
            shutil.rmtree(output_dir, ignore_errors=True)
        _run(
            session,
            "uv",
            "run",
            "--project",
            str(PROJECT_ROOT),
            "--frozen",
            "sphinx-build",
            "-W",
            "--keep-going",
            "-b",
            builder,
            str(PUBLIC_DOCS_ROOT),
            str(output_dir),
        )

    reporter.run(
        "docs / public source boundary",
        lambda: _run_project_python(session, "tools/check_public_docs.py"),
    )
    reporter.run(
        "docs / Vale reader style",
        lambda: _run(
            session,
            str(ensure_vale(REPO_ROOT)),
            "--config=.vale.ini",
            "--glob=*.md",
            *PUBLIC_DOCS_ENTRYPOINTS,
            str(PUBLIC_DOCS_ROOT),
        ),
        detail="Stripe-inspired RAES style",
    )
    reporter.run(
        "docs / executable quickstart",
        lambda: _run(
            session,
            "uv",
            "run",
            "--project",
            str(PROJECT_ROOT),
            "--frozen",
            "python",
            "-m",
            "pytest",
            "-q",
            *PUBLIC_DOCS_EXAMPLE_TESTS,
        ),
    )
    reporter.run(
        "docs / Sphinx HTML",
        lambda: _build("html", html_dir, clean=True),
        detail=f"{PUBLIC_DOCS_ROOT.relative_to(REPO_ROOT)} -> {html_dir.relative_to(REPO_ROOT)}",
    )
    reporter.run(
        "docs / public output inventory",
        lambda: _run_project_python(
            session,
            "tools/check_public_docs.py",
            "--output",
            str(html_dir),
        ),
    )
    if include_external_links:
        reporter.run(
            "docs / Sphinx link check",
            lambda: _build("linkcheck", linkcheck_dir),
            detail=str(PUBLIC_DOCS_ROOT.relative_to(REPO_ROOT)),
        )


def _run_docs_linkcheck(session: nox.Session, reporter: SessionReporter) -> None:
    _sync_project(session)
    linkcheck_dir = DOCS_BUILD_ROOT / "linkcheck"
    reporter.run(
        "docs / Sphinx external link check",
        lambda: _run(
            session,
            "uv",
            "run",
            "--project",
            str(PROJECT_ROOT),
            "--frozen",
            "sphinx-build",
            "-W",
            "--keep-going",
            "-b",
            "linkcheck",
            str(PUBLIC_DOCS_ROOT),
            str(linkcheck_dir),
        ),
        detail=str(PUBLIC_DOCS_ROOT.relative_to(REPO_ROOT)),
    )
