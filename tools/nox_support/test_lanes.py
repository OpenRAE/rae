"""Test, compatibility, coverage, integration, scan, and docs lanes."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import nox
from raes_contracts.errors import InvalidInputError, OperationalError
from yaml import YAMLError

from tools.check_adr_immutability import MANIFEST_PATH as ADR_PIN_PATH
from tools.check_adr_immutability import _coerce_manifest
from tools.check_identity_cutover import _load_historical_records
from tools.nox_support.config import (
    DEFAULT_SUITE_EXPRESSION,
    DOCS_BUILD_ROOT,
    INSTALLATION_QUALIFICATION_HARNESSES,
    OSV_SCAN_TARGETS,
    PROJECT_ROOT,
    PUBLIC_DOCS_ENTRYPOINTS,
    PUBLIC_DOCS_EXAMPLE_TESTS,
    PUBLIC_DOCS_ROOT,
    REPO_ROOT,
    SHARD_PLUGIN,
)
from tools.nox_support.runner import (
    SessionReporter,
    _chunked,
    _hygiene_flags,
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
from tools.policy.common import YAML_CONTENT_FAILURES, load_yaml, safe_repo_path
from tools.pytest_shard import ShardManifestError, read_manifest, verify_shard_partition
from tools.vale_tool import ensure_vale
from tools.verification_plan import _run_git, collect_git_changes


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
            xdist="worksteal" if parallel else None,
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
    # Each test module stays on one xdist worker. Module-scoped build, install
    # and documentation fixtures then run once, as they do in a serial run.
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
            xdist="loadfile",
        ),
        detail="xdist auto, max 8, loadfile",
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
            xdist="worksteal",
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
        raise OperationalError("canonical collection returned no node ids")
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
        raise ShardManifestError(f"no shard manifests found under {reduce_dir}")
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


def _run_osv_scan(_session: nox.Session, reporter: SessionReporter) -> None:
    def _scan(lockfile: Path, report: Path) -> None:
        if not lockfile.exists():
            raise InvalidInputError(f"osv-scan: tracked lockfile not found: {lockfile.relative_to(REPO_ROOT)}")
        binary = ensure_osv_scanner(REPO_ROOT)
        exit_code = run_osv_scanner(lockfile, report, binary=binary)
        report_rel = report.relative_to(REPO_ROOT)
        outcome = classify_osv_exit_code(exit_code)
        if outcome is OSVScanOutcome.FINDINGS:
            # The scanned lock does not satisfy the vulnerability gate; the caller must correct it.
            raise InvalidInputError(f"osv-scanner reported vulnerabilities (exit code {exit_code}); see {report_rel}")
        if outcome is OSVScanOutcome.SCANNER_ERROR:
            raise OperationalError(
                f"osv-scanner failed with scanner/setup error exit code {exit_code}; report at {report_rel}"
            )

    for label, lockfile, report in OSV_SCAN_TARGETS:
        reporter.run(
            f"osv-scan / {label}",
            lambda lockfile=lockfile, report=report: _scan(lockfile, report),
            detail=str(lockfile.relative_to(REPO_ROOT)),
        )


def _selected_prose_paths(posargs: list[str]) -> list[str]:
    """Resolve common selection arguments and validate every selected prose path."""
    staged, base_rev, all_files, explicit = _hygiene_flags(posargs, default_all_files=False)
    if explicit:
        paths = explicit
    elif staged:
        paths = _run_git(REPO_ROOT, "diff", "--cached", "--name-only", "--diff-filter=d", "-z").split("\0")
    elif all_files:
        paths = _run_git(REPO_ROOT, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    else:
        paths = [change.path for change in collect_git_changes(REPO_ROOT, base_rev or "HEAD") if change.status != "D"]

    selected: list[str] = []
    for path in dict.fromkeys(paths):
        if Path(path).suffix not in {".md", ".rst"}:
            continue
        target = safe_repo_path(REPO_ROOT, path)
        if target is None:
            raise InvalidInputError("unsafe prose path outside the repository")
        if not target.is_file():
            raise InvalidInputError("selected prose path is not a file")
        selected.append(path)
    return selected


def _protected_prose_paths() -> set[str]:
    """Read exact protected identities through the existing catalog validators."""
    try:
        adrs, failures = _coerce_manifest(load_yaml(REPO_ROOT / ADR_PIN_PATH), ADR_PIN_PATH)
    except (OSError, YAMLError, InvalidInputError, *YAML_CONTENT_FAILURES) as exc:
        raise InvalidInputError("protected prose catalog cannot be read") from exc
    if failures or adrs is None or any(safe_repo_path(REPO_ROOT, entry["path"]) is None for entry in adrs):
        raise InvalidInputError("protected ADR prose catalog is invalid")
    records, _bindings, generated, failures = _load_historical_records(REPO_ROOT)
    if failures:
        raise InvalidInputError("protected historical prose catalog is invalid")
    protected = {"CHANGELOG.md", "THIRD_PARTY_NOTICES.md", *records, *generated}
    protected.update(entry["path"] for entry in adrs)
    return protected


def _run_docs_prose(session: nox.Session, reporter: SessionReporter) -> None:
    """Lint selected maintained prose; report exact protected identities for review."""
    selected = _selected_prose_paths(session.posargs)
    if not selected:
        reporter.skip("docs / Vale changed prose", "no Markdown or reStructuredText selected")
        return
    protected = _protected_prose_paths()
    excluded = [path for path in selected if path in protected]
    if excluded:
        reporter.skip(
            "docs / protected prose",
            "manual source/meaning review and Vale stdin checks of new maintained passages required: " + repr(excluded),
        )
    maintained = [path for path in selected if path not in protected]
    if not maintained:
        return

    binary = str(ensure_vale(REPO_ROOT))
    project_environment = Path(os.environ.get("UV_PROJECT_ENVIRONMENT", str(PROJECT_ROOT / ".venv")))
    if not project_environment.is_absolute():
        project_environment = PROJECT_ROOT / project_environment
    env = {"PATH": os.pathsep.join((str(project_environment / "bin"), os.environ.get("PATH", "")))}

    def lint() -> None:
        for batch in _chunked(maintained):
            _run(
                session,
                binary,
                "--no-global",
                f"--config={REPO_ROOT / '.vale.ini'}",
                "--glob=*.{md,rst}",
                "--",
                *(str(REPO_ROOT / path) for path in batch),
                env=env,
            )

    reporter.run("docs / Vale changed prose", lint, detail=f"{len(maintained)} maintained files")


def _run_docs(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    include_external_links: bool = True,
) -> None:
    _sync_project(session)
    _run_docs_prose(session, reporter)
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
