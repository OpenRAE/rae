from __future__ import annotations

import fnmatch
import json
import subprocess
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from raes_contracts.errors import InvalidInputError

REPO_ROOT = Path(__file__).resolve().parents[2]

# The safe constructor raises these, not a YAMLError, for a scalar that it cannot build, such as an
# impossible date, an integer beyond the interpreter digit limit, an unknown !!bool value or an
# empty !!int value.
_YAML_CONSTRUCTOR_FAILURES = (ValueError, KeyError, AttributeError, IndexError)
# Besides yaml.YAMLError, reading a file with read_text() and yaml.safe_load() raises these for
# malformed input: UnicodeDecodeError (a ValueError) for text that is not UTF-8, the constructor
# failures above, and RecursionError for nesting beyond the recursive composer. Catch them only
# around those calls.
YAML_CONTENT_FAILURES = (*_YAML_CONSTRUCTOR_FAILURES, RecursionError)


@dataclass(frozen=True)
class PolicyFailure:
    rule_id: str
    message: str
    path: str | None = None

    def render(self) -> str:
        if self.path:
            return f"[{self.rule_id}] {self.path}: {self.message}"
        return f"[{self.rule_id}] {self.message}"


def load_yaml(path: Path) -> dict:
    """Load one repository YAML document.

    Raise ``InvalidInputError`` for a scalar that the safe constructor cannot
    build and for nesting beyond the parser depth. ``yaml.YAMLError``,
    ``UnicodeDecodeError`` and ``OSError`` keep their types.
    """

    with path.open("r", encoding="utf-8") as handle:
        try:
            data = yaml.safe_load(handle)
        except UnicodeDecodeError:
            raise
        except _YAML_CONSTRUCTOR_FAILURES as exc:
            raise InvalidInputError(f"{path.name} contains a YAML value that cannot be constructed") from exc
        except RecursionError as exc:
            # Without a depth limit, the recursive composer stops at the interpreter recursion limit.
            raise InvalidInputError(f"{path.name} nests beyond the YAML parser depth") from exc
    return data or {}


def repo_path(value: str | Path) -> str:
    return Path(value).as_posix().strip("/")


def safe_repo_path(repo_root: Path, rel_path: str) -> Path | None:
    """Resolve ``rel_path`` against ``repo_root`` and return the resolved
    path only if it stays inside the repository. Returns None for absolute
    paths, parent-traversal segments, or symlinks that resolve outside the
    repo. This guards every place a policy reads a path that ultimately comes
    from PR-controlled config or the changed-file list."""
    candidate = Path(rel_path)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        return None
    try:
        resolved = (repo_root / candidate).resolve()
        resolved.relative_to(repo_root.resolve())
    except (ValueError, OSError):
        return None
    return resolved


def load_bounded_json_object(
    repo_root: Path,
    rel_path: str,
    *,
    max_bytes: int,
) -> dict[str, object]:
    """Load one repository JSON object with containment, size, and duplicate-key checks.

    Raise ``InvalidInputError`` when the artifact is missing, unsafe, too large,
    not UTF-8 JSON, has a duplicate key, has an integer beyond the interpreter
    digit limit, nests beyond the decoder depth or is not an object.
    ``OSError`` reports a file that exists but cannot be read.
    """

    path = safe_repo_path(repo_root, rel_path)
    if path is None or not path.is_file():
        raise InvalidInputError(f"missing or unsafe repository artifact {rel_path!r}")
    if path.stat().st_size > max_bytes:
        raise InvalidInputError(f"{rel_path!r} exceeds the {max_bytes}-byte limit")

    def object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise InvalidInputError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def bounded_integer(literal: str) -> int:
        # The decoder passes only JSON integer literals, so int() fails only beyond the interpreter digit limit.
        try:
            return int(literal)
        except ValueError as exc:
            raise InvalidInputError(f"{rel_path!r} contains an integer beyond the digit limit") from exc

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_without_duplicates,
            parse_int=bounded_integer,
        )
    except UnicodeDecodeError as exc:
        raise InvalidInputError(f"{rel_path!r} is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise InvalidInputError(
            f"{rel_path!r} is not valid JSON ({exc.msg} at line {exc.lineno} column {exc.colno})"
        ) from exc
    except RecursionError as exc:
        # Without a depth limit, the recursive decoder stops at the interpreter recursion limit.
        raise InvalidInputError(f"{rel_path!r} exceeds the JSON decoder depth limit") from exc
    if not isinstance(payload, dict):
        raise InvalidInputError(f"{rel_path!r} must contain a JSON object")
    return payload


def run_git(args: list[str], repo_root: Path = REPO_ROOT) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout


def changed_paths(
    repo_root: Path = REPO_ROOT,
    *,
    staged: bool = False,
    base_rev: str | None = None,
) -> list[str]:
    if staged:
        output = run_git(["diff", "--name-only", "--diff-filter=d", "--cached"], repo_root=repo_root)
    elif base_rev:
        output = run_git(
            ["diff", "--name-only", "--diff-filter=d", base_rev, "HEAD"],
            repo_root=repo_root,
        )
    else:
        output = run_git(["diff", "--name-only", "--diff-filter=d", "HEAD"], repo_root=repo_root)
    return [line.strip() for line in output.splitlines() if line.strip()]


def path_matches_prefix(path: str, prefix: str) -> bool:
    norm = repo_path(path)
    pref = repo_path(prefix)
    return norm == pref or norm.startswith(f"{pref}/")


def path_matches_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path_matches_prefix(path, prefix) for prefix in prefixes)


def glob_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


_INVALID_EXCEPTIONS = "tools/policy/exceptions.yaml is not a valid policy exceptions document"


def load_exceptions(repo_root: Path = REPO_ROOT) -> list[dict]:
    """Load the policy exceptions; raise ``InvalidInputError`` when the file is not a YAML mapping.

    ``OSError`` reports a file that exists but cannot be read.
    """

    try:
        raw = load_yaml(repo_root / "tools" / "policy" / "exceptions.yaml")
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise InvalidInputError(_INVALID_EXCEPTIONS) from exc
    if not isinstance(raw, dict):
        raise InvalidInputError(_INVALID_EXCEPTIONS)
    return raw.get("exceptions", [])


def _text_items(value: object) -> bool:
    return isinstance(value, (str, list, dict, set)) and all(isinstance(item, str) for item in value)


def exception_active(entry: dict, *, today: date | None = None) -> bool:
    if today is None:
        today = date.today()
    expires_at = entry.get("expires_at")
    if not expires_at:
        return True
    try:
        expiry = date.fromisoformat(str(expires_at))
    except ValueError as exc:
        raise InvalidInputError("policy exception expires_at must be an ISO date") from exc
    return today <= expiry


def apply_exceptions(
    failures: list[PolicyFailure],
    exceptions: list[dict],
    *,
    requirement_uid: str | None = None,
) -> list[PolicyFailure]:
    if not failures or not exceptions:
        return failures

    remaining: list[PolicyFailure] = []
    for failure in failures:
        waived = False
        for entry in exceptions:
            # An entry or field that this matching cannot read is malformed input, not a defect.
            if not isinstance(entry, dict):
                raise InvalidInputError(_INVALID_EXCEPTIONS)
            if not exception_active(entry):
                continue
            if entry.get("rule_id") != failure.rule_id:
                continue
            entry_requirement = entry.get("requirement_uid")
            if requirement_uid and not isinstance(entry_requirement, Hashable):
                raise InvalidInputError(_INVALID_EXCEPTIONS)
            if requirement_uid and entry_requirement not in {
                None,
                requirement_uid,
            }:
                continue
            match_paths = entry.get("paths") or []
            if failure.path and match_paths and not _text_items(match_paths):
                raise InvalidInputError(_INVALID_EXCEPTIONS)
            if failure.path and match_paths and not path_matches_any(failure.path, match_paths):
                continue
            waived = True
            break
        if not waived:
            remaining.append(failure)
    return remaining


def failures_to_json(failures: list[PolicyFailure]) -> str:
    return json.dumps(
        [
            {
                "rule_id": failure.rule_id,
                "message": failure.message,
                "path": failure.path,
            }
            for failure in failures
        ],
        indent=2,
        sort_keys=True,
    )
