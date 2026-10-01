"""Test, compatibility, coverage, integration, scan, and docs lanes."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import nox

from tools.nox_support.config import (
    DEFAULT_SUITE_EXPRESSION,
    DOCS_BUILD_ROOT,
    INSTALLATION_QUALIFICATION_HARNESSES,
    OSV_LOCKFILE_PATH,
    OSV_REPORT_PATH,
    PROJECT_ROOT,
    PUBLIC_DOCS_ENTRYPOINTS,
    PUBLIC_DOCS_EXAMPLE_TESTS,
    PUBLIC_DOCS_ROOT,
    REPO_ROOT,
    SHARD_PLUGIN,
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
from tools.pytest_shard import read_manifest, verify_shard_partition
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


def _run_shard_tests(
    session: nox.Session,
    reporter: SessionReporter,
    coverage_file: Path,
    *,
    shard_count: int,
    shard_index: int,
    manifest_path: Path,
    source_sha: str,
) -> None:
    """Run one deterministic shard of the default-marker suite, emitting a manifest.

    The partition plugin lives in the repo-root ``tools`` package; export the repo
    root so ``-p`` resolves before the ini ``pythonpath`` is applied. xdist still
    parallelizes within the shard but never partitions across jobs.
    """

    args = [
        "-q",
        "-p",
        SHARD_PLUGIN,
        "--shard-count",
        str(shard_count),
        "--shard-index",
        str(shard_index),
        "--shard-manifest",
        str(manifest_path),
        "--shard-source-sha",
        source_sha,
        "--shard-suite-expression",
        DEFAULT_SUITE_EXPRESSION,
    ]
    reporter.run(
        f"tests / shard {shard_index} of {shard_count}",
        lambda: _run_pytest(
            session,
            *args,
            coverage_file=coverage_file,
            finalize_coverage=False,
            parallel=True,
            extra_env={"PYTHONPATH": str(REPO_ROOT)},
        ),
        detail="deterministic sha256 node-id partition :: xdist within shard",
    )


def _collect_canonical_nodeids(session: nox.Session) -> list[str]:
    """Freshly collect the canonical default-marker suite node ids."""

    with session.chdir(PROJECT_ROOT):
        output = session.run(
            "uv",
            "run",
            "--frozen",
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-header",
            external=True,
            silent=True,
        )
    nodeids = [line.strip() for line in (output or "").splitlines() if "::" in line]
    if not nodeids:
        raise RuntimeError("canonical collection returned no node ids")
    return nodeids


def _run_coverage_reduce(
    session: nox.Session,
    reporter: SessionReporter,
    reduce_dir: Path,
    *,
    shard_count: int,
    source_sha: str,
) -> None:
    """Prove shard completeness, then combine shard + integration coverage once.

    ``reduce_dir`` holds every producer's ``.coverage.*`` data file and the
    ``shard-*.json`` manifests. The completeness proof runs before any combine so
    a missing, failed, or stale shard fails closed instead of yielding a partial
    report.
    """

    _sync_project(session)
    manifests = [read_manifest(path) for path in sorted(reduce_dir.glob("shard-*.json"))]
    if not manifests:
        raise RuntimeError(f"no shard manifests found under {reduce_dir}")
    canonical = _collect_canonical_nodeids(session)
    reporter.run(
        "coverage / shard completeness proof",
        lambda: verify_shard_partition(
            manifests,
            canonical,
            shard_count=shard_count,
            source_sha=source_sha or None,
        ),
        detail=f"{len(manifests)} shards :: {len(canonical)} canonical node ids",
    )

    coverage_env = {"COVERAGE_FILE": str(reduce_dir / ".coverage")}

    def _combine_and_report() -> None:
        with session.chdir(PROJECT_ROOT):
            _run(session, "uv", "run", "--frozen", "coverage", "combine", "--keep", str(reduce_dir), env=coverage_env)
            _write_and_check_coverage(session, coverage_env)

    reporter.run(
        "coverage / combined shard and integration report",
        _combine_and_report,
        detail="coverage combine :: xml + json :: 90% line floor",
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


def _restore_owner_write(root: Path) -> None:
    for current, directories, _files in os.walk(root, followlinks=False):
        for name in directories:
            directory = Path(current) / name
            if not directory.is_symlink():
                directory.chmod(0o700)


def _run_installation_qualification(
    session: nox.Session,
    reporter: SessionReporter,
    name: str,
    posargs: list[str],
) -> None:
    """Run one qualification harness from the frozen tooling closure in a private root."""

    harness, detail = INSTALLATION_QUALIFICATION_HARNESSES[name]
    with tempfile.TemporaryDirectory(prefix=f"raes-{name}-") as temporary:
        # Resolve platform temp aliases such as macOS /var so the private-root
        # anchor chain contains no symbolic link.
        root = Path(temporary).resolve() / "root"
        try:
            reporter.run(
                f"qualification / {name}",
                lambda: _run(session, sys.executable, str(REPO_ROOT / harness), str(root), *posargs),
                detail=detail,
            )
        finally:
            _restore_owner_write(Path(temporary))
