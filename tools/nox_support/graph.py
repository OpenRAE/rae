"""The parallel verification graph and change-selected verification."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import nox

from tools.nox_support.config import (
    JSON_SCHEMA_WORKERS_ENV,
    REPO_ROOT,
    VERIFY_COVERAGE_FILE_ENV,
    VERIFY_PROJECT_SYNCED_ENV,
)
from tools.nox_support.policy_lanes import (
    _run_contracts,
    _run_hygiene,
    _run_lint,
    _run_policy,
)
from tools.nox_support.runner import (
    SessionReporter,
    _requirement_aware_policy_args,
    _run_project_python,
    _sync_project,
)
from tools.nox_support.test_lanes import (
    _finalize_parallel_coverage,
    _run_docs,
    _run_fuzz,
    _run_tests,
)
from tools.parallel_verification import VerificationLane, run_verification_lanes
from tools.verification_plan import (
    collect_git_changes,
    plan_for_changes,
    resolve_upstream,
)


def _changed_base_rev(posargs: list[str]) -> str:
    if "--base-rev" in posargs:
        index = posargs.index("--base-rev")
        if index + 1 >= len(posargs):
            raise ValueError("--base-rev requires a revision")
        return posargs[index + 1]
    return resolve_upstream(REPO_ROOT)


def _verification_lanes(
    *,
    posargs: Sequence[str],
    coverage_dir: Path,
    include_policy: bool,
    cpu_count: int | None = None,
) -> tuple[VerificationLane, ...]:
    available_cpus = cpu_count if cpu_count is not None else _available_cpu_count()
    shared_posargs = tuple(posargs)
    static_posargs = (("--include-policy",) if include_policy else ()) + shared_posargs
    return (
        VerificationLane(
            name="unit-tests",
            nox_session="verify-tests-lane",
            env={
                VERIFY_COVERAGE_FILE_ENV: str(coverage_dir / ".coverage.unit"),
                "PYTEST_ADDOPTS": f"-o cache_dir={coverage_dir / 'pytest-unit'}",
                "PYTEST_XDIST_AUTO_NUM_WORKERS": str(max(1, min(8, available_cpus // 2))),
            },
        ),
        VerificationLane(
            name="integration-tests",
            nox_session="verify-integration-lane",
            env={
                VERIFY_COVERAGE_FILE_ENV: str(coverage_dir / ".coverage.integration"),
                "PYTEST_ADDOPTS": f"-o cache_dir={coverage_dir / 'pytest-integration'}",
            },
        ),
        VerificationLane(
            name="contracts",
            nox_session="contracts",
            posargs=shared_posargs,
            env={JSON_SCHEMA_WORKERS_ENV: str(max(1, min(4, available_cpus // 4)))},
        ),
        VerificationLane(
            name="static",
            nox_session="verify-static-lane",
            posargs=static_posargs,
        ),
        VerificationLane(
            name="participant-opacity-proof",
            nox_session="participant-opacity-proof",
        ),
        VerificationLane(
            name="docs-local",
            nox_session="docs-local",
            env={
                "PYTEST_ADDOPTS": f"-o cache_dir={coverage_dir / 'pytest-docs'}",
            },
        ),
    )


def _available_cpu_count() -> int:
    if hasattr(os, "sched_getaffinity"):
        try:
            return max(1, len(os.sched_getaffinity(0)))
        except OSError:
            pass
    return max(1, os.cpu_count() or 1)


def _verification_lane_workers(*, cpu_count: int, lane_count: int) -> int:
    return min(lane_count, 4, max(1, cpu_count // 2))


def _failure_summary(output: str) -> str:
    summary_lines = [line.strip() for line in output.splitlines() if line.startswith(("FAILED ", "ERROR "))]
    if not summary_lines:
        summary_lines = [line.strip() for line in output.splitlines() if line.strip()][-1:]
    summary = " | ".join(summary_lines[:3])
    return summary if len(summary) <= 600 else f"{summary[:599]}…"


def _execute_verification_lanes(
    session: nox.Session,
    lanes: tuple[VerificationLane, ...],
    lane_workers: int,
) -> None:
    results = run_verification_lanes(
        lanes,
        nox_python=Path(sys.executable),
        noxfile=REPO_ROOT / "noxfile.py",
        repo_root=REPO_ROOT,
        base_env={
            VERIFY_PROJECT_SYNCED_ENV: str(os.getpid()),
            "PYTHONUNBUFFERED": "1",
        },
        max_workers=lane_workers,
    )
    failures = [result for result in results if result.returncode != 0]
    for result in failures:
        session.log(f"[verify] failure summary {result.name}: {_failure_summary(result.output)}")
    for result in results:
        state = "PASS" if result.returncode == 0 else "FAIL"
        session.log(f"[verify] lane {result.name}: {state} ({result.duration_s:.2f}s)")
        if result.output:
            print(result.output, end="" if result.output.endswith("\n") else "\n")
    if failures:
        failed = ", ".join(f"{result.name} (exit {result.returncode})" for result in failures)
        raise RuntimeError(f"parallel verification lanes failed: {failed}")


def _run_parallel_verification(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    include_policy: bool,
) -> None:
    reporter.run(
        "verify / locked project environment",
        lambda: _sync_project(session),
        detail="one synchronization shared by all isolated lanes",
    )
    reporter.run(
        "verify / shared policy toolchain",
        lambda: _run_project_python(
            session,
            "-c",
            "from tools.policy.conftest_tool import ensure_conftest; ensure_conftest()",
        ),
        detail="prime checksum-verified Conftest before parallel policy tests",
    )
    with tempfile.TemporaryDirectory(prefix="raes-coverage-") as coverage_root:
        coverage_dir = Path(coverage_root)
        available_cpus = _available_cpu_count()
        lanes = _verification_lanes(
            posargs=session.posargs,
            coverage_dir=coverage_dir,
            include_policy=include_policy,
            cpu_count=available_cpus,
        )
        lane_workers = _verification_lane_workers(
            cpu_count=available_cpus,
            lane_count=len(lanes),
        )
        reporter.run(
            "verify / isolated deterministic lanes",
            lambda: _execute_verification_lanes(session, lanes, lane_workers),
            detail=(
                "unit, integration, contracts, static, proof, docs-local :: "
                f"{lane_workers} lane workers on {available_cpus} CPUs"
            ),
        )
        reporter.run(
            "verify / combined coverage",
            lambda: _finalize_parallel_coverage(session, coverage_dir),
            detail="unit + integration data files",
        )


def _run_changed_verification(
    session: nox.Session,
    reporter: SessionReporter,
    posargs: list[str],
) -> None:
    try:
        base_rev = _changed_base_rev(posargs)
        changes = collect_git_changes(REPO_ROOT, base_rev)
        plan = plan_for_changes(changes)
        session.log(f"change-aware verification against {base_rev}: {plan.reason}; {len(changes)} change records")
    except (RuntimeError, ValueError) as exc:
        base_rev = None
        plan = plan_for_changes([])
        session.log(f"change classification failed closed to the full local gate: {exc}")

    base_policy_args = ["--base-rev", base_rev] if base_rev is not None else []
    policy_args = _requirement_aware_policy_args(*base_policy_args)
    _run_hygiene(session, reporter, posargs=["--all-files"], default_all_files=True)
    _run_policy(session, reporter, *policy_args)
    _run_lint(session, reporter)
    if plan.contracts:
        _run_contracts(session, reporter, *policy_args)
    else:
        reporter.skip("contracts / governed artifact graph", plan.reason)
    if plan.regression:
        with tempfile.TemporaryDirectory(prefix="raes-coverage-") as coverage_dir:
            _run_tests(session, reporter, Path(coverage_dir) / ".coverage")
    else:
        reporter.skip("tests / pytest", plan.reason)
    if plan.fuzz:
        _run_fuzz(session, reporter)
    else:
        reporter.skip("tests / pytest fuzz", plan.reason)
    if plan.docs:
        _run_docs(session, reporter)
    else:
        reporter.skip("docs / sphinx-build", plan.reason)
