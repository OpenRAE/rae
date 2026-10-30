"""ADR-117 structural baselines: read, validate and compare them with the base revision.

The import contracts hold the import debt in their ``ignore_imports`` lists.
``structural_baseline.json`` holds the cyclic components, the private imports
and the deep classes, with the adoption commit and the analysis record.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from raes_contracts.errors import InvalidInputError, OperationalError

from .common import parse_bounded_json_object, read_repository_text, run_git, safe_repo_path

IMPORT_CONTRACTS_PATH = "tools/policy/import_contracts.toml"
STRUCTURAL_BASELINE_PATH = "tools/policy/structural_baseline.json"
BASELINE_SCHEMA = "raes.structural-baseline/v1"
LAYERS_CONTRACT_ID = "raes-package-layers"
CYCLES_CONTRACT_ID = "raes-sibling-cycles"
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
ANALYSIS_KEYS = ("exclude_type_checking_imports", "grimp", "import-linter", "max_repository_ancestors", "sibling_depth")

_DOTTED = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
_IMPORT_EXPRESSION = re.compile(rf"^({_DOTTED}) -> ({_DOTTED})\Z", re.ASCII)
_DOTTED_NAME = re.compile(rf"^{_DOTTED}\Z", re.ASCII)
_CLASS_ID = re.compile(rf"^{_DOTTED}:[A-Za-z_<>.\w]+\Z", re.ASCII)
_COMMIT = re.compile(r"^[0-9a-f]{40}\Z", re.ASCII)
_REVISION = re.compile(r"^\w[\w./@^~{}-]*\Z", re.ASCII)
_SESSION_KEYS = {"root_packages", "include_external_packages", "exclude_type_checking_imports", "contracts"}
_CONTRACT_KEYS = {
    LAYERS_CONTRACT_ID: (
        "layers",
        {"id", "name", "type", "layers", "ignore_imports", "unmatched_ignore_imports_alerting"},
    ),
    CYCLES_CONTRACT_ID: (
        "acyclic_siblings",
        {"id", "name", "type", "ancestors", "depth", "ignore_imports", "unmatched_ignore_imports_alerting"},
    ),
}

ImportPair = tuple[str, str]


@dataclass(frozen=True)
class ImportContracts:
    root_packages: tuple[str, ...]
    exclude_type_checking_imports: bool
    layers: tuple[str, ...]
    cycles_ancestors: tuple[str, ...]
    cycles_depth: int
    ignores: Mapping[str, frozenset[ImportPair]]


@dataclass(frozen=True)
class StructuralBaseline:
    adopted_commit: str
    analysis: Mapping[str, object]
    cycle_components: Mapping[str, tuple[tuple[str, ...], ...]]
    private_imports: Mapping[ImportPair, int]
    deep_classes: Mapping[str, int]


class BaseRevision(Protocol):
    """The revision whose baselines bound the current baselines (ADR-117 I5, I6)."""

    revision: str

    def read(self, rel_path: str) -> str | None: ...

    def sources_changed(self, roots: Sequence[str]) -> bool: ...


class GitBaseRevision:
    """Read the base revision from the Git object store of the checkout."""

    def __init__(self, repo_root: Path, revision: str) -> None:
        self._repo_root = repo_root
        self.revision = validate_git_revision(revision)

    def read(self, rel_path: str) -> str | None:
        return read_base_artifact(self._repo_root, self.revision, rel_path)

    def sources_changed(self, roots: Sequence[str]) -> bool:
        return package_sources_changed(self._repo_root, self.revision, roots)


def validate_git_revision(value: str) -> str:
    """Accept a revision that git cannot read as an option."""

    if not _REVISION.match(value):
        raise InvalidInputError("a git revision must not be empty, start with '-' or contain other characters")
    return value


def read_artifact(repo_root: Path, rel_path: str) -> str:
    path = safe_repo_path(repo_root, rel_path)
    if path is None or not path.is_file():
        raise InvalidInputError(f"{rel_path} is missing or is not a regular file in the repository")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise InvalidInputError(f"{rel_path} exceeds the {MAX_ARTIFACT_BYTES}-byte limit")
    return read_repository_text(path, rel_path)


def read_base_artifact(repo_root: Path, base_rev: str, rel_path: str) -> str | None:
    """Return ``rel_path`` at ``base_rev``, or None when the base revision does not have it."""

    revision = validate_git_revision(base_rev)
    verified = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{revision}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if verified.returncode != 0:
        raise OperationalError(f"base revision {revision!r} is not a commit in this repository")
    commit = verified.stdout.strip()
    if not _git(repo_root, ["ls-tree", "--name-only", commit, "--", rel_path]).strip():
        return None
    size = int(_git(repo_root, ["cat-file", "-s", f"{commit}:{rel_path}"]).strip())
    if size > MAX_ARTIFACT_BYTES:
        raise InvalidInputError(f"{rel_path} at the base revision exceeds the {MAX_ARTIFACT_BYTES}-byte limit")
    try:
        return _git(repo_root, ["show", f"{commit}:{rel_path}"])
    except UnicodeDecodeError as exc:
        raise InvalidInputError(f"{rel_path} at the base revision is not UTF-8 text") from exc


def package_sources_changed(repo_root: Path, base_rev: str, roots: Sequence[str]) -> bool:
    """Tell whether a tracked or untracked file under ``roots`` differs from ``base_rev``."""

    revision = validate_git_revision(base_rev)
    changed = _git(repo_root, ["diff", "--name-only", "--end-of-options", revision, "--", *roots])
    untracked = _git(repo_root, ["ls-files", "--others", "--exclude-standard", "--", *roots])
    return bool(changed.strip() or untracked.strip())


def _git(repo_root: Path, args: list[str]) -> str:
    try:
        return run_git(args, repo_root=repo_root)
    except subprocess.CalledProcessError as exc:
        raise OperationalError(f"git {args[0]} failed while reading the base revision") from exc


def parse_import_contracts(text: str, source: str) -> ImportContracts:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidInputError(f"{source} is not valid TOML") from exc
    tool = document.get("tool")
    session = tool.get("importlinter") if isinstance(tool, dict) else None
    if set(document) != {"tool"} or not isinstance(session, dict) or set(tool) != {"importlinter"}:
        raise InvalidInputError(f"{source} must hold only a [tool.importlinter] table")
    if set(session) != _SESSION_KEYS:
        raise InvalidInputError(f"{source}: [tool.importlinter] keys must be {sorted(_SESSION_KEYS)}")
    root_packages = _name_list(session["root_packages"], f"{source}: root_packages")
    if session["include_external_packages"] is not False:
        raise InvalidInputError(f"{source}: include_external_packages must be false")
    exclude_type_checking = session["exclude_type_checking_imports"]
    if not isinstance(exclude_type_checking, bool):
        raise InvalidInputError(f"{source}: exclude_type_checking_imports must be a boolean")
    contracts = session["contracts"]
    if not isinstance(contracts, list) or not all(isinstance(item, dict) for item in contracts):
        raise InvalidInputError(f"{source}: contracts must be a list of tables")
    by_id = {contract.get("id"): contract for contract in contracts}
    if len(contracts) != len(_CONTRACT_KEYS) or set(by_id) != set(_CONTRACT_KEYS):
        raise InvalidInputError(f"{source}: contracts must be exactly {sorted(_CONTRACT_KEYS)}")
    ignores: dict[str, frozenset[ImportPair]] = {}
    for contract_id, (contract_type, keys) in _CONTRACT_KEYS.items():
        contract = by_id[contract_id]
        label = f"{source}: contract {contract_id}"
        if set(contract) != keys or contract["type"] != contract_type or not isinstance(contract["name"], str):
            raise InvalidInputError(f"{label} must have type {contract_type!r} and keys {sorted(keys)}")
        if contract["unmatched_ignore_imports_alerting"] != "error":
            raise InvalidInputError(f"{label}: unmatched_ignore_imports_alerting must be 'error'")
        ignores[contract_id] = _import_pairs(contract["ignore_imports"], label)
    layers = by_id[LAYERS_CONTRACT_ID]["layers"]
    if not isinstance(layers, list) or not layers or not all(isinstance(item, str) for item in layers):
        raise InvalidInputError(f"{source}: layers must be a non-empty list of strings")
    depth = by_id[CYCLES_CONTRACT_ID]["depth"]
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
        raise InvalidInputError(f"{source}: depth must be a non-negative integer")
    return ImportContracts(
        root_packages=root_packages,
        exclude_type_checking_imports=exclude_type_checking,
        layers=tuple(layers),
        cycles_ancestors=_name_list(by_id[CYCLES_CONTRACT_ID]["ancestors"], f"{source}: ancestors"),
        cycles_depth=depth,
        ignores=ignores,
    )


def parse_structural_baseline(text: str, source: str) -> StructuralBaseline:
    payload = parse_bounded_json_object(text, source)
    expected = {"schema", "adopted_commit", "analysis", "cycle_components", "private_imports", "deep_classes"}
    if set(payload) != expected:
        raise InvalidInputError(f"{source} keys must be {sorted(expected)}")
    if payload["schema"] != BASELINE_SCHEMA:
        raise InvalidInputError(f"{source}: schema must be {BASELINE_SCHEMA!r}")
    commit = payload["adopted_commit"]
    if not isinstance(commit, str) or not _COMMIT.match(commit):
        raise InvalidInputError(f"{source}: adopted_commit must be a 40-character commit id")
    analysis = payload["analysis"]
    if not isinstance(analysis, dict) or set(analysis) != set(ANALYSIS_KEYS):
        raise InvalidInputError(f"{source}: analysis keys must be {list(ANALYSIS_KEYS)}")
    return StructuralBaseline(
        adopted_commit=commit,
        analysis=analysis,
        cycle_components=_components(payload["cycle_components"], source),
        private_imports=_private_imports(payload["private_imports"], source),
        deep_classes=_deep_classes(payload["deep_classes"], source),
    )


def _name_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise InvalidInputError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and _DOTTED_NAME.match(item) for item in value):
        raise InvalidInputError(f"{label} must hold dotted module names")
    if len(set(value)) != len(value):
        raise InvalidInputError(f"{label} must not repeat a name")
    return tuple(value)


def _import_pairs(value: object, label: str) -> frozenset[ImportPair]:
    if not isinstance(value, list):
        raise InvalidInputError(f"{label}: ignore_imports must be a list")
    pairs: list[ImportPair] = []
    for item in value:
        match = _IMPORT_EXPRESSION.match(item) if isinstance(item, str) else None
        if match is None:
            raise InvalidInputError(f"{label}: ignore_imports entries must be exact 'importer -> imported' modules")
        pairs.append((match.group(1), match.group(2)))
    if len(set(pairs)) != len(pairs):
        raise InvalidInputError(f"{label}: ignore_imports must not repeat an entry")
    return frozenset(pairs)


def _components(value: object, source: str) -> dict[str, tuple[tuple[str, ...], ...]]:
    if not isinstance(value, dict):
        raise InvalidInputError(f"{source}: cycle_components must be an object")
    result: dict[str, tuple[tuple[str, ...], ...]] = {}
    for package, components in value.items():
        if not _DOTTED_NAME.match(package) or not isinstance(components, list) or not components:
            raise InvalidInputError(f"{source}: cycle_components[{package!r}] must be a non-empty list")
        seen: set[str] = set()
        parsed: list[tuple[str, ...]] = []
        for component in components:
            if (
                not isinstance(component, list)
                or len(component) < 2
                or component != sorted(set(component))
                or not all(isinstance(member, str) and _is_child(package, member) for member in component)
                or seen.intersection(component)
            ):
                raise InvalidInputError(
                    f"{source}: each component of {package!r} must be a sorted list of two or more distinct "
                    "children of the package, in no other component"
                )
            seen.update(component)
            parsed.append(tuple(component))
        result[package] = tuple(sorted(parsed))
    return result


def _private_imports(value: object, source: str) -> dict[ImportPair, int]:
    if not isinstance(value, dict):
        raise InvalidInputError(f"{source}: private_imports must be an object")
    result: dict[ImportPair, int] = {}
    for importer, targets in value.items():
        if not _DOTTED_NAME.match(importer) or not isinstance(targets, dict) or not targets:
            raise InvalidInputError(f"{source}: private_imports[{importer!r}] must be a non-empty object")
        for target, count in targets.items():
            if not _DOTTED_NAME.match(target) or not _positive(count):
                raise InvalidInputError(f"{source}: private_imports[{importer!r}][{target!r}] must be a positive count")
            result[(importer, target)] = count
    return result


def _deep_classes(value: object, source: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise InvalidInputError(f"{source}: deep_classes must be an object")
    for class_id, count in value.items():
        if not _CLASS_ID.match(class_id) or not _positive(count):
            raise InvalidInputError(f"{source}: deep_classes[{class_id!r}] must be a positive ancestor count")
    return dict(value)


def _is_child(package: str, member: str) -> bool:
    return (
        bool(_DOTTED_NAME.match(member)) and member.startswith(f"{package}.") and "." not in member[len(package) + 1 :]
    )


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
