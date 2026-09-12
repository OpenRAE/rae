# ruff: noqa: E402, I001
"""Repository nox sessions.

Configuration constants, the session reporter/runner, lane implementations,
and graph composition live in ``tools/nox_support``; this file is the public
session registry.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import nox

nox.options.default_venv_backend = "none"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["verify"]

REPO_ROOT = Path(__file__).resolve().parent
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.nox_support.compatibility_lanes import _run_python_compatibility
from tools.nox_support.config import (
    CONTRACT_TRIGGER_PREFIXES,
    FULL_TEST_TRIGGER_PREFIXES,
    TARGETED_POLICY_TESTS,
    TOOLING_TEST_TRIGGER_PREFIXES,
    VERIFY_COVERAGE_FILE_ENV,
)
from tools.nox_support.policy_lanes import (
    _run_changed_lint,
    _run_contracts,
    _run_hygiene,
    _run_lint,
    _run_participant_opacity_proof,
    _run_policy,
)
from tools.nox_support.graph import (
    _run_changed_verification,
    _run_parallel_verification,
)
from tools.nox_support.runner import (
    SessionReporter,
    _paths_trigger,
    _requirement_aware_policy_args,
    _run_pytest,
    _sync_project,
)
from tools.nox_support.test_lanes import (
    _run_docker_integration_tests,
    _run_docs,
    _run_docs_linkcheck,
    _run_fuzz,
    _run_integration_tests,
    _run_osv_scan,
    _run_tests,
)

from tools.verification_plan import (
    select_changed_python_tests,
)


@nox.session
def hygiene(session: nox.Session) -> None:
    reporter = SessionReporter(session, "hygiene")
    try:
        _run_hygiene(session, reporter, posargs=session.posargs, default_all_files=True)
    finally:
        reporter.summary()


@nox.session
def policy(session: nox.Session) -> None:
    reporter = SessionReporter(session, "policy")
    try:
        _run_policy(session, reporter, *session.posargs)
    finally:
        reporter.summary()


@nox.session
def lint(session: nox.Session) -> None:
    reporter = SessionReporter(session, "lint")
    try:
        _run_lint(session, reporter)
    finally:
        reporter.summary()


@nox.session
def contracts(session: nox.Session) -> None:
    reporter = SessionReporter(session, "contracts")
    try:
        _run_contracts(session, reporter, *session.posargs)
    finally:
        reporter.summary()


@nox.session(name="participant-opacity-proof")
def participant_opacity_proof(session: nox.Session) -> None:
    """Replay the pinned, network-isolated SEM-231 mathematical proof."""

    reporter = SessionReporter(session, "participant-opacity-proof")
    try:
        _run_participant_opacity_proof(session, reporter)
    finally:
        reporter.summary()


@nox.session
def tests(session: nox.Session) -> None:
    reporter = SessionReporter(session, "tests")
    try:
        with tempfile.TemporaryDirectory(prefix="raes-coverage-") as coverage_dir:
            _run_tests(
                session,
                reporter,
                Path(coverage_dir) / ".coverage",
                list(session.posargs),
            )
    finally:
        reporter.summary()


@nox.session(name="python-compatibility")
def python_compatibility(session: nox.Session) -> None:
    """Test one exact supported interpreter and its installed distribution."""

    reporter = SessionReporter(session, "python-compatibility")
    try:
        _run_python_compatibility(session, reporter)
    finally:
        reporter.summary()


@nox.session
def fuzz(session: nox.Session) -> None:
    reporter = SessionReporter(session, "fuzz")
    try:
        _run_fuzz(session, reporter)
    finally:
        reporter.summary()


@nox.session
def integration(session: nox.Session) -> None:
    """Run pytest with the `integration` marker only.

    The default test session excludes subprocess, build, installed-distribution,
    and whole-system tests. This session opts them in. `verify` wires this session
    in after the parallel test sweep so CI keeps both layers covered.
    """
    reporter = SessionReporter(session, "integration")
    try:
        _sync_project(session)
        _run_integration_tests(session, reporter)
    finally:
        reporter.summary()


@nox.session(name="integration_docker")
def integration_docker(session: nox.Session) -> None:
    """Run the opt-in container-runtime integration tests (`docker` marker).

    Requires a real container runtime (docker/podman). The tests self-skip
    cleanly when no runtime is available unless
    `RAES_DOCKER_INTEGRATION_REQUIRED=1` selects the fail-closed release mode.
    This session is intentionally NOT wired into `verify`, so the canonical
    verification graph stays hermetic.
    """
    reporter = SessionReporter(session, "integration_docker")
    try:
        _sync_project(session)
        _run_docker_integration_tests(session, reporter)
    finally:
        reporter.summary()


@nox.session
def docs(session: nox.Session) -> None:
    reporter = SessionReporter(session, "docs")
    try:
        _run_docs(session, reporter)
    finally:
        reporter.summary()


@nox.session(name="docs-local")
def docs_local(session: nox.Session) -> None:
    """Run deterministic documentation checks without external HTTP requests."""

    reporter = SessionReporter(session, "docs-local")
    try:
        _run_docs(session, reporter, include_external_links=False)
    finally:
        reporter.summary()


@nox.session(name="docs-links")
def docs_links(session: nox.Session) -> None:
    """Check external documentation links; intended for the dedicated CI job."""

    reporter = SessionReporter(session, "docs-links")
    try:
        _run_docs_linkcheck(session, reporter)
    finally:
        reporter.summary()


@nox.session(name="osv_scan")
def osv_scan(session: nox.Session) -> None:
    """Required OSV-Scanner sweep over the Python dependency lockfile (#1098).

    This remains outside `verify` / `hook-pre-push` because acquiring and running
    OSV-Scanner requires network access. The standalone CI job is gating: both
    findings and scanner/setup errors fail, with distinct diagnostics, while CI
    still publishes the JSON report artifact.
    """
    reporter = SessionReporter(session, "osv_scan")
    try:
        _run_osv_scan(session, reporter)
    finally:
        reporter.summary()


@nox.session(name="hook-pre-commit")
def hook_pre_commit(session: nox.Session) -> None:
    reporter = SessionReporter(session, "hook-pre-commit")
    changed = [Path(arg).as_posix() for arg in session.posargs if not arg.startswith("-")]
    changed_tests = select_changed_python_tests(changed)
    try:
        _run_hygiene(session, reporter, posargs=changed, default_all_files=False)
        _run_policy(session, reporter, *_requirement_aware_policy_args("--staged"))
        _run_changed_lint(session, reporter, changed)
        if _paths_trigger(changed, CONTRACT_TRIGGER_PREFIXES):
            _run_contracts(session, reporter)
        else:
            reporter.skip("contracts / generated schema drift", "no contract-bearing changes")
            reporter.skip("contracts / json artifact validation", "no contract-bearing changes")
        if changed_tests:
            reporter.run(
                "tests / directly changed pytest modules",
                lambda: _run_pytest(session, *changed_tests, "-q"),
                detail=" ".join(changed_tests),
            )
        elif _paths_trigger(changed, FULL_TEST_TRIGGER_PREFIXES):
            reporter.skip(
                "tests / pytest",
                "no directly changed test module; full regression runs at pre-push and completion",
            )
        elif _paths_trigger(changed, TOOLING_TEST_TRIGGER_PREFIXES):
            reporter.run(
                "tests / targeted tooling tests",
                lambda: _run_pytest(session, *TARGETED_POLICY_TESTS, "-q"),
                detail=" ".join(TARGETED_POLICY_TESTS),
            )
        else:
            reporter.skip(
                "tests / pytest",
                "no implementation or tooling test trigger paths changed",
            )
    finally:
        reporter.summary()


@nox.session(name="hook-pre-push")
def hook_pre_push(session: nox.Session) -> None:
    reporter = SessionReporter(session, "hook-pre-push")
    try:
        _run_changed_verification(session, reporter, list(session.posargs))
    finally:
        reporter.summary()


@nox.session(name="verify-changed")
def verify_changed(session: nox.Session) -> None:
    """Run the fail-closed local gate selected from changes since the upstream ref."""

    reporter = SessionReporter(session, "verify-changed")
    try:
        _run_changed_verification(session, reporter, list(session.posargs))
    finally:
        reporter.summary()


def _required_coverage_file() -> Path:
    value = os.environ.get(VERIFY_COVERAGE_FILE_ENV)
    if not value:
        raise RuntimeError(f"{VERIFY_COVERAGE_FILE_ENV} is required for an orchestrated coverage lane")
    return Path(value)


@nox.session(name="verify-static-lane")
def verify_static_lane(session: nox.Session) -> None:
    """Internal lane for full-tree hygiene, policy, and lint checks."""

    reporter = SessionReporter(session, "verify-static-lane")
    posargs = list(session.posargs)
    include_policy = "--include-policy" in posargs
    if include_policy:
        posargs.remove("--include-policy")
    try:
        _run_hygiene(
            session,
            reporter,
            posargs=posargs or ["--all-files"],
            default_all_files=True,
        )
        if include_policy:
            _run_policy(session, reporter, *posargs)
        _run_lint(session, reporter)
    finally:
        reporter.summary()


@nox.session(name="verify-tests-lane")
def verify_tests_lane(session: nox.Session) -> None:
    """Internal unit-test lane that emits an independently combinable data file."""

    reporter = SessionReporter(session, "verify-tests-lane")
    try:
        _run_tests(
            session,
            reporter,
            _required_coverage_file(),
            finalize_coverage=False,
        )
    finally:
        reporter.summary()


@nox.session(name="verify-integration-lane")
def verify_integration_lane(session: nox.Session) -> None:
    """Internal integration lane with coverage isolated from the unit workers."""

    reporter = SessionReporter(session, "verify-integration-lane")
    try:
        _run_integration_tests(
            session,
            reporter,
            coverage_file=_required_coverage_file(),
            append_coverage=False,
            finalize_coverage=False,
        )
    finally:
        reporter.summary()


@nox.session
def verify(session: nox.Session) -> None:
    reporter = SessionReporter(session, "verify")
    try:
        _run_parallel_verification(session, reporter, include_policy=True)
    finally:
        reporter.summary()


@nox.session(name="verify-completion")
def verify_completion(session: nox.Session) -> None:
    """Run the completion graph whose Ground Control pair runs policy next."""

    reporter = SessionReporter(session, "verify-completion")
    try:
        _run_parallel_verification(session, reporter, include_policy=False)
    finally:
        reporter.summary()
