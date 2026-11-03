"""ADR-117 check 4: access to a private member of another object.

The rule is Ruff ``SLF001`` (flake8-self): ``obj._x`` is a finding, and
``self._x``, ``cls._x`` and ``super()._x`` are not. The check runs Ruff from the
locked tooling environment with only this rule selected and without repository
configuration. Ruff parses the source; it never imports or runs it.

The identity of a finding is the module and the attribute name.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError, OperationalError

from .source_index import SourceIndex

RULE = "SLF001"
_MESSAGE = re.compile(r"^Private member accessed: `([A-Za-z_]\w*)`$", re.ASCII)
_TIMEOUT_SECONDS = 600


@dataclass(frozen=True, order=True)
class PrivateMemberAccess:
    module: str
    member: str


@dataclass(frozen=True)
class PrivateMemberAnalysis:
    counts: Counter[PrivateMemberAccess]
    version: str


def analyze_private_members(repo_root: Path, index: SourceIndex) -> PrivateMemberAnalysis:
    """Run Ruff ``SLF001`` on the coverage roots and count each finding by module and member.

    Raise ``OperationalError`` when Ruff is not installed or does not finish, and
    ``InvalidInputError`` when its report is not the expected shape or names a
    file outside the index.
    """

    version = _ruff(["--version"], repo_root).strip().removeprefix("ruff ").strip()
    report = _ruff(
        [
            "check",
            "--isolated",
            "--no-cache",
            "--exit-zero",
            "--target-version",
            "py314",
            "--select",
            RULE,
            "--output-format",
            "json",
            *index.coverage_roots,
        ],
        repo_root,
    )
    return PrivateMemberAnalysis(counts=count_private_members(report, repo_root, index), version=version)


def count_private_members(report: str, repo_root: Path, index: SourceIndex) -> Counter[PrivateMemberAccess]:
    """Turn one Ruff JSON report into counts; fail closed on any other diagnostic or an unknown file."""

    try:
        diagnostics = json.loads(report)
    except json.JSONDecodeError as exc:
        raise InvalidInputError("the Ruff report is not JSON") from exc
    if not isinstance(diagnostics, list):
        raise InvalidInputError("the Ruff report must be a list of diagnostics")
    modules_by_path = {module.rel_path: module.name for module in index.modules.values()}
    counts: Counter[PrivateMemberAccess] = Counter()
    for diagnostic in diagnostics:
        counts[_finding(diagnostic, repo_root, modules_by_path)] += 1
    return counts


def _finding(diagnostic: object, repo_root: Path, modules_by_path: dict[str, str]) -> PrivateMemberAccess:
    if not isinstance(diagnostic, dict) or diagnostic.get("code") != RULE:
        code = diagnostic.get("code") if isinstance(diagnostic, dict) else None
        raise InvalidInputError(f"the Ruff report has a diagnostic other than {RULE}: {code!r}")
    match = _MESSAGE.match(str(diagnostic.get("message", "")))
    try:
        rel_path = Path(str(diagnostic.get("filename"))).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise InvalidInputError("the Ruff report names a file outside the repository") from exc
    module = modules_by_path.get(rel_path)
    if match is None or module is None:
        raise InvalidInputError(f"the Ruff report has an unexpected {RULE} diagnostic for {rel_path}")
    return PrivateMemberAccess(module, match.group(1))


def _ruff(args: Sequence[str], repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "ruff", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OperationalError("the private-member check could not run Ruff") from exc
    if completed.returncode != 0:
        raise OperationalError("the private-member check needs Ruff from the locked tooling environment")
    return completed.stdout


__all__ = ["PrivateMemberAccess", "PrivateMemberAnalysis", "analyze_private_members", "count_private_members"]
