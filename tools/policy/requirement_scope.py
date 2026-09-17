"""Closed issue-bound assignments over the incumbent requirement predicates."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from tools.policy.common import (
    PolicyFailure,
    apply_exceptions,
    load_bounded_json_object,
    load_exceptions,
)
from tools.policy.requirement_governance import (
    RequirementClient,
    evaluate_requirement_governance,
)
from tools.tooling_artifact_policy_common import is_regular_repo_file

_UID = re.compile(r"[A-Z]{3}-\d{3,}")
_ISSUE_BRANCH = re.compile(r"([1-9]\d*)-[A-Za-z0-9][A-Za-z0-9._/-]*", flags=re.ASCII)
_FIELDS = frozenset(
    {
        "schema_version",
        "issue_number",
        "primary_requirement_uid",
        "requirement_uids",
        "bindings",
    }
)
_MAX_SCOPE_BYTES = 256 * 1024


class RequirementScopeError(ValueError):
    """Scope authority is malformed or conflicts with the delivery context."""


@dataclass(frozen=True)
class RequirementScope:
    issue_number: int
    primary_requirement_uid: str
    requirement_uids: tuple[str, ...]
    bindings: Mapping[str, tuple[str, ...]]


def _uids(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 64
        or any(not isinstance(uid, str) or _UID.fullmatch(uid) is None for uid in value)
        or len(set(value)) != len(value)
    ):
        raise RequirementScopeError("Scope requires a nonempty unique list of canonical requirement UIDs.")
    return tuple(value)


def _exact_path(value: object) -> bool:
    if not isinstance(value, str) or not value or any(char in value for char in "\\:*?[]"):
        return False
    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and value == path.as_posix()
        and all(part not in {".", "..", ".secrets"} for part in path.parts)
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def parse_requirement_scope(document: object, *, issue_number: int) -> RequirementScope:
    """Admit exact assignments, never glob/prefix matches or inferred owners."""
    if not isinstance(document, dict) or document.keys() != _FIELDS:
        raise RequirementScopeError("Scope must contain exactly the supported fields.")
    if (
        document["schema_version"] != "requirement-scope/v1"
        or type(document["issue_number"]) is not int
        or document["issue_number"] != issue_number
        or issue_number < 1
    ):
        raise RequirementScopeError("Scope version or issue identity does not match its canonical location.")
    uids = _uids(document["requirement_uids"])
    primary = document["primary_requirement_uid"]
    if primary not in uids:
        raise RequirementScopeError("The primary requirement must be explicitly in scope.")
    bindings = _parse_bindings(document["bindings"], uids)
    return RequirementScope(issue_number, primary, uids, MappingProxyType(bindings))


def _parse_bindings(raw_bindings: object, uids: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw_bindings, dict) or not raw_bindings:
        raise RequirementScopeError("Scope requires exact file assignments.")
    bindings = {}
    for path, assigned in raw_bindings.items():
        if not _exact_path(path):
            raise RequirementScopeError("Scope assignments must name canonical repository-relative files.")
        owners = _uids(assigned)
        if not set(owners) <= set(uids):
            raise RequirementScopeError("A file assignment names a requirement outside the declared scope.")
        bindings[path] = owners
    return bindings


def load_requirement_scope(repo_root: Path, branch: str | None) -> RequirementScope | None:
    """Select only the canonical manifest for the issue identified by the branch."""
    match = _ISSUE_BRANCH.fullmatch(branch or "")
    if match is None:
        return None
    issue_number = int(match[1])
    relative = f"docs/governance/requirement-scopes/{issue_number}.json"
    path = repo_root.resolve() / relative
    try:
        # A substituted or dangling authority component is not an absent scope.
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent != repo_root.resolve()):
            raise RequirementScopeError("Scope authority must not use symlinks.")
        if not path.exists():
            if _scope_previously_established(repo_root, relative):
                raise RequirementScopeError("Previously established requirement scope authority is missing.")
            return None
        if not is_regular_repo_file(repo_root, relative):
            raise RequirementScopeError("Scope authority must be a regular canonical repository file.")
        document = load_bounded_json_object(repo_root, relative, max_bytes=_MAX_SCOPE_BYTES)
        return parse_requirement_scope(document, issue_number=issue_number)
    except (OSError, ValueError, RecursionError) as exc:
        raise RequirementScopeError("Requirement scope cannot be read and validated.") from exc


def _scope_previously_established(repo_root: Path, relative: str) -> bool:
    """Retain scope authority across index removals, renames and committed deletions."""
    if not (repo_root / ".git").exists():
        return False
    try:
        # All retained refs include the integration base even in detached PR checkouts.
        # Full history also catches a deletion already committed on the issue branch.
        history = subprocess.run(
            [
                "git",
                "log",
                "--all",
                "--full-history",
                "-1",
                "--format=%H",
                "--",
                relative,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        index = subprocess.run(
            ["git", "ls-files", "--", relative],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RequirementScopeError("Established scope authority cannot be determined.") from exc
    return bool(history.stdout.strip() or index.stdout.strip())


def evaluate_requirement_scope(
    repo_root: Path,
    changed: list[str],
    *,
    client: RequirementClient,
    scope: RequirementScope,
) -> list[PolicyFailure]:
    """AND each assigned owner's complete checks; never union partial successes."""
    failures = [
        PolicyFailure(
            "requirement-scope-unassigned",
            "Changed file has no explicit requirement assignment.",
            path,
        )
        for path in sorted(set(changed) - scope.bindings.keys())
    ]
    exceptions = load_exceptions(repo_root)
    for uid in scope.requirement_uids:
        owned = sorted(path for path in set(changed) if uid in scope.bindings.get(path, ()))
        # Even an owner with no files in this incremental diff must remain valid.
        failures.extend(
            apply_exceptions(
                evaluate_requirement_governance(repo_root, owned, client=client, requirement_uid=uid),
                exceptions,
                requirement_uid=uid,
            )
        )
    return failures
