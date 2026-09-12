"""Session reporting and low-level command execution for nox lanes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import nox

from tools.gitleaks_tool import ensure_gitleaks
from tools.nox_support.config import (
    COVERAGE_JSON_PATH,
    COVERAGE_XML_PATH,
    EXCLUDED_PREFIXES,
    MINIMUM_LINE_COVERAGE_PERCENT,
    PROJECT_ROOT,
    REPO_ROOT,
    REQUIREMENT_UID_RE,
    RUFF_CONFIG,
    VERIFY_PROJECT_SYNCED_ENV,
)
from tools.python_closure_profiles import frozen_tool_command


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    detail: str = ""
    duration_s: float | None = None


@dataclass(frozen=True)
class HygieneSelection:
    paths: list[str]
    source: str


class SessionReporter:
    def __init__(self, session: nox.Session, session_name: str) -> None:
        self.session = session
        self.session_name = session_name
        self.results: list[StageResult] = []

    def run(self, name: str, func: Callable[[], None], *, detail: str = "") -> None:
        self._log("START", name, detail)
        started = perf_counter()
        try:
            func()
        except Exception:
            duration_s = perf_counter() - started
            self.results.append(StageResult(name=name, status="FAIL", detail=detail, duration_s=duration_s))
            self._log("FAIL", name, detail, duration_s)
            raise
        duration_s = perf_counter() - started
        self.results.append(StageResult(name=name, status="PASS", detail=detail, duration_s=duration_s))
        self._log("PASS", name, detail, duration_s)

    def skip(self, name: str, reason: str) -> None:
        self.results.append(StageResult(name=name, status="SKIP", detail=reason))
        self._log("SKIP", name, reason)

    def summary(self) -> None:
        self.session.log(f"[{self.session_name}] stage summary:")
        if not self.results:
            self.session.log(f"[{self.session_name}]   SKIP no stages executed")
            return
        for result in self.results:
            duration = f" ({result.duration_s:.2f}s)" if result.duration_s is not None else ""
            detail = f" :: {result.detail}" if result.detail else ""
            self.session.log(f"[{self.session_name}]   {result.status:<4} {result.name}{duration}{detail}")

    def _log(self, status: str, name: str, detail: str, duration_s: float | None = None) -> None:
        duration = f" ({duration_s:.2f}s)" if duration_s is not None else ""
        suffix = f" :: {detail}" if detail else ""
        self.session.log(f"[{self.session_name}] {status}: {name}{duration}{suffix}")


def _run(
    session: nox.Session,
    *args: str,
    silent: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    session.run(*args, external=True, silent=silent, env=env)


def _git_lines(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


_EXCLUDE_DELETED_FILTER = "--diff-filter=d"


def _changed_paths(*, staged: bool = False, base_rev: str | None = None) -> list[str]:
    if staged:
        return _normalize_paths(_git_lines("diff", "--name-only", _EXCLUDE_DELETED_FILTER, "--cached"))
    if base_rev:
        return _normalize_paths(_git_lines("diff", "--name-only", _EXCLUDE_DELETED_FILTER, base_rev, "HEAD"))
    return _normalize_paths(_git_lines("diff", "--name-only", _EXCLUDE_DELETED_FILTER, "HEAD"))


def _sync_project(session: nox.Session) -> None:
    if os.environ.get(VERIFY_PROJECT_SYNCED_ENV) == str(os.getppid()):
        return
    _run(
        session,
        "uv",
        "sync",
        "--project",
        str(PROJECT_ROOT),
        "--all-extras",
        "--frozen",
    )


def _run_project_python(session: nox.Session, script: str, *args: str) -> None:
    _run(
        session,
        "uv",
        "run",
        "--project",
        str(PROJECT_ROOT),
        "--frozen",
        "python",
        script,
        *args,
    )


def _run_external_subprocess(*args: str) -> None:
    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    raise RuntimeError(f"{Path(args[0]).name} failed with exit code {proc.returncode}")


def _run_ruff(session: nox.Session, *args: str, project_relative: bool = False) -> None:
    command = frozen_tool_command(REPO_ROOT, "ruff")
    if project_relative:
        with session.chdir(PROJECT_ROOT):
            _run(session, *command, *args)
        return
    _run(session, *command, "--config", str(RUFF_CONFIG), *args)


def _run_pytest(
    session: nox.Session,
    *args: str,
    coverage_file: Path | None = None,
    append_coverage: bool = False,
    finalize_coverage: bool = False,
    parallel: bool = False,
) -> None:
    _sync_project(session)
    normalized_args = [
        str((REPO_ROOT / arg).relative_to(PROJECT_ROOT)) if arg.startswith("implementations/python/") else arg
        for arg in args
    ]
    command = ["uv", "run", "--frozen", "python", "-m", "pytest"]
    if parallel:
        command.extend(["-n", "auto", "--maxprocesses=8", "--dist=worksteal"])
    coverage_env: dict[str, str] | None = None
    if coverage_file is not None:
        coverage_env = {"COVERAGE_FILE": str(coverage_file)}
        command.extend(["--cov", "--cov-config=pyproject.toml", "--cov-report="])
        if append_coverage:
            command.append("--cov-append")
    command.extend(normalized_args)
    with session.chdir(PROJECT_ROOT):
        _run(session, *command, env=coverage_env)
        if finalize_coverage:
            _write_and_check_coverage(session, coverage_env)


def _required_option_value(values: Sequence[str], index: int, option: str) -> str:
    value_index = index + 1
    if value_index >= len(values) or not values[value_index] or values[value_index].startswith("--"):
        raise ValueError(f"{option} requires a value")
    return values[value_index]


def _split_policy_session_args(posargs: list[str]) -> tuple[list[str], list[str], bool]:
    repo_args: list[str] = []
    requirement_args: list[str] = []
    skip_requirement = False
    index = 0
    while index < len(posargs):
        arg = posargs[index]
        if arg == "--skip-requirement":
            skip_requirement = True
            index += 1
            continue
        if arg == "--requirement-uid":
            requirement_args.extend([arg, _required_option_value(posargs, index, arg)])
            index += 2
            continue
        if arg == "--base-rev":
            value = _required_option_value(posargs, index, arg)
            repo_args.extend([arg, value])
            requirement_args.extend([arg, value])
            index += 2
            continue
        repo_args.append(arg)
        requirement_args.append(arg)
        index += 1
    return repo_args, requirement_args, skip_requirement


def _requirement_aware_policy_args(*args: str) -> list[str]:
    if os.environ.get("RAES_REQUIREMENT_UID", "").strip():
        return list(args)
    branch = next(iter(_git_lines("branch", "--show-current")), "")
    if REQUIREMENT_UID_RE.search(branch):
        return list(args)
    return [*args, "--skip-requirement"]


def _hygiene_flags(posargs: Sequence[str], *, default_all_files: bool) -> tuple[bool, str | None, bool, list[str]]:
    staged = False
    base_rev: str | None = None
    all_files = default_all_files
    explicit_paths: list[str] = []
    index = 0
    values = list(posargs)
    while index < len(values):
        arg = values[index]
        if arg == "--staged":
            staged = True
            all_files = False
            index += 1
            continue
        if arg == "--all-files":
            all_files = True
            staged = False
            base_rev = None
            index += 1
            continue
        if arg == "--base-rev":
            base_rev = _required_option_value(values, index, arg)
            all_files = False
            index += 2
            continue
        if arg == "--skip-requirement":
            index += 1
            continue
        if arg == "--requirement-uid":
            _required_option_value(values, index, arg)
            index += 2
            continue
        explicit_paths.append(arg)
        all_files = False
        index += 1
    return staged, base_rev, all_files, explicit_paths


def _parse_hygiene_posargs(posargs: Sequence[str], *, default_all_files: bool) -> HygieneSelection:
    staged, base_rev, all_files, explicit_paths = _hygiene_flags(posargs, default_all_files=default_all_files)
    if explicit_paths:
        selection = HygieneSelection(paths=_normalize_paths(explicit_paths), source="explicit path selection")
    elif staged:
        selection = HygieneSelection(paths=_changed_paths(staged=True), source="staged tracked files")
    elif base_rev:
        selection = HygieneSelection(paths=_changed_paths(base_rev=base_rev), source=f"changes since {base_rev}")
    elif all_files:
        selection = HygieneSelection(paths=_tracked_repo_paths(), source="tracked repository files")
    else:
        selection = HygieneSelection(paths=_changed_paths(), source="working tree changes")
    return selection


def _tracked_repo_paths() -> list[str]:
    return _normalize_paths(_git_lines("ls-files", "--cached", "--others", "--exclude-standard"))


def _normalize_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in paths:
        path = Path(raw).as_posix().strip("/")
        if not path or path.startswith(EXCLUDED_PREFIXES):
            continue
        absolute = REPO_ROOT / path
        if not absolute.is_file() or path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def _text_paths(paths: list[str]) -> list[str]:
    text_paths: list[str] = []
    for path in paths:
        try:
            sample = (REPO_ROOT / path).read_bytes()[:8192]
        except OSError:
            continue
        if b"\x00" in sample:
            continue
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            continue
        text_paths.append(path)
    return text_paths


def _suffix_paths(paths: list[str], suffixes: tuple[str, ...]) -> list[str]:
    suffix_set = {suffix.lower() for suffix in suffixes}
    return [path for path in paths if Path(path).suffix.lower() in suffix_set]


def _chunked(paths: Sequence[str], *, size: int = 200) -> list[list[str]]:
    return [list(paths[index : index + size]) for index in range(0, len(paths), size)]


def _paths_trigger(paths: Iterable[str], prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefixes) or path in prefixes for path in paths)


def _run_pre_commit_hook(_session: nox.Session, command: str, *args: str, paths: list[str]) -> None:
    for batch in _chunked(paths):
        _run_external_subprocess(
            *frozen_tool_command(REPO_ROOT, command),
            *args,
            *batch,
        )


def _run_gitleaks_dir_scan(_session: nox.Session, paths: list[str]) -> None:
    binary = ensure_gitleaks(REPO_ROOT)
    with tempfile.TemporaryDirectory(prefix="raes-gitleaks-") as tmpdir:
        scan_root = Path(tmpdir) / "scan"
        scan_root.mkdir()
        for path in paths:
            source = (REPO_ROOT / path).resolve()
            target = scan_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source)
        _run_external_subprocess(
            str(binary),
            "dir",
            "--config",
            str(REPO_ROOT / ".gitleaks.toml"),
            "--follow-symlinks",
            "--no-banner",
            "--redact",
            "--log-level",
            "warn",
            str(scan_root),
        )


def _enforce_line_coverage(report_path: Path) -> float:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        totals = report["totals"]
        covered_lines = totals["covered_lines"]
        statements = totals["num_statements"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"could not read line coverage totals from {report_path}") from exc
    if (
        not isinstance(covered_lines, int)
        or isinstance(covered_lines, bool)
        or not isinstance(statements, int)
        or isinstance(statements, bool)
        or covered_lines < 0
        or statements < 0
        or covered_lines > statements
    ):
        raise RuntimeError(f"invalid line coverage totals in {report_path}")
    percent = 100.0 if statements == 0 else 100.0 * covered_lines / statements
    if percent + 1e-12 < MINIMUM_LINE_COVERAGE_PERCENT:
        raise RuntimeError(f"line coverage {percent:.3f}% is below required {MINIMUM_LINE_COVERAGE_PERCENT:.3f}%")
    return percent


def _write_and_check_coverage(session: nox.Session, coverage_env: dict[str, str]) -> None:
    _run(
        session,
        "uv",
        "run",
        "--frozen",
        "coverage",
        "xml",
        "-o",
        str(COVERAGE_XML_PATH),
        env=coverage_env,
    )
    _run(
        session,
        "uv",
        "run",
        "--frozen",
        "coverage",
        "json",
        "-o",
        str(COVERAGE_JSON_PATH),
        env=coverage_env,
    )
    _run(
        session,
        "uv",
        "run",
        "--frozen",
        "coverage",
        "report",
        "--format=total",
        env=coverage_env,
    )
    _enforce_line_coverage(COVERAGE_JSON_PATH)
