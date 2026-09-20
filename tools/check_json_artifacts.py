#!/usr/bin/env python3
# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.policy.common import REPO_ROOT as POLICY_REPO_ROOT, changed_paths
from tools.tooling_artifact_policy_common import is_regular_repo_file
from tools.python_closure_profiles import frozen_tool_command


REPO_ROOT = POLICY_REPO_ROOT


SCHEMA_DRIVER_PATHS = (
    "contracts/schemas/",
    "implementations/python/packages/raes_contracts/",
    "implementations/python/packages/raes_backend_protocols/",
    "implementations/python/packages/raes_processor/",
    "implementations/python/packages/raes/",
    "tools/generate_contract_schemas.py",
)
JSON_SCHEMA_WORKERS_ENV = "RAES_JSON_SCHEMA_WORKERS"
_AUTHORING_ADAPTER_ROUTES = {
    "contracts/profiles/authoring-adapters/": "authoring-adapter-profile-v1",
    "contracts/fixtures/authoring-adapters-v1/cases/": "authoring-adapter-vector-v1",
}


@dataclass(frozen=True)
class VersionedSchemaRoute:
    """A source tree whose artifacts name their published contract in ``schema_version``.

    ``family`` is the directory under ``contracts/schemas/`` that holds the
    contract. Adding a corpus is a row here, never a per-contract branch, and the
    published-schema coverage gate inherits the row through
    :func:`covered_schema_paths`.
    """

    prefix: str
    family: str
    recursive: bool = False


_VERSIONED_SCHEMA_ROUTES: tuple[VersionedSchemaRoute, ...] = (
    VersionedSchemaRoute("contracts/profiles/semantic/", "profiles"),
    VersionedSchemaRoute("contracts/profiles/backend/", "profiles"),
    VersionedSchemaRoute("contracts/profiles/random-stream/", "profiles"),
    VersionedSchemaRoute(
        "contracts/profiles/participant-information-reconstruction/", "profiles"
    ),
    VersionedSchemaRoute(
        "contracts/profiles/behavioral-relation/", "profiles", recursive=True
    ),
    VersionedSchemaRoute(
        "contracts/profiles/participant-boundary-flow-policy/", "profiles"
    ),
    VersionedSchemaRoute("contracts/profiles/scientific-completeness/", "profiles"),
    VersionedSchemaRoute("contracts/profiles/validation/", "profiles"),
    VersionedSchemaRoute(
        "contracts/profiles/candidate-synthesis/", "candidate-synthesis"
    ),
    VersionedSchemaRoute(
        "contracts/profiles/participant-control/", "participant-runtime"
    ),
    VersionedSchemaRoute("contracts/concept-authority/history/", "concept-authority"),
    VersionedSchemaRoute("contracts/provenance/", "provenance"),
    VersionedSchemaRoute(
        "contracts/realization-envelopes/", "realization-envelope", recursive=True
    ),
    VersionedSchemaRoute(
        "contracts/fixtures/random-stream-vectors/", "profiles", recursive=True
    ),
)

JSON_SUFFIX = ".json"
JSON_GLOB = f"*{JSON_SUFFIX}"

_HISTORICAL_IDENTITY_RECORDS_PATH = "tools/policy/historical_identity_records.json"


@dataclass(frozen=True)
class ValidationTarget:
    path: str
    schema_path: str | None
    mode: str


@dataclass(frozen=True)
class ValidationBatch:
    paths: tuple[str, ...]
    schema_path: str | None
    mode: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate published JSON Schemas and schema-governed JSON artifacts."
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes instead of working tree changes.",
    )
    parser.add_argument("--base-rev", help="Compare against a specific git revision.")
    parser.add_argument(
        "paths", nargs="*", help="Explicit repo-relative paths to check."
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_rel_from(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _schema_filename(schema_version: str) -> str:
    return f"{schema_version.replace('/', '-')}.json"


def _routable(repo_root: Path, path: Path) -> str | None:
    """Return the repo-relative path only when it is a regular in-repository file.

    Corpus trees are PR-controlled, so discovery must not dereference a tracked
    symlink: ``Path.is_file()`` follows one, and both the schema-version read and
    ``check-jsonschema`` would then consume whatever the link resolves to on the
    runner. ``is_regular_repo_file`` rejects a symlink at any component and any
    non-regular leaf, which is the same boundary the published-schema coverage
    gate applies to declared evidence.
    """

    relative = _repo_rel_from(repo_root, path)
    return relative if is_regular_repo_file(repo_root, relative) else None


def _frozen_historical_records(repo_root: Path) -> frozenset[str]:
    """Repo-relative artifacts pinned as immutable pre-cutover historical records.

    ``tools/check_identity_cutover.py`` governs these by content hash: each
    preserves a dated fact in the shape its contract had when it was written, so
    it is not a live document of the contract as published now, and validating it
    against a later revision would be a category error that no edit could
    honestly resolve. Excluding them from routing never hides a contract: the
    live document alongside them still routes, and the published-schema coverage
    gate reads the same join.
    """

    # This manifest decides what routing skips, so a symlink here could redirect
    # the exclusion set at a file outside the checkout and suppress validation.
    # Absent, irregular, or unreadable means "exclude nothing", never "exclude
    # whatever the link resolves to".
    records: object = None
    if is_regular_repo_file(repo_root, _HISTORICAL_IDENTITY_RECORDS_PATH):
        try:
            payload = json.loads(
                (repo_root / _HISTORICAL_IDENTITY_RECORDS_PATH).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError):
            payload = {}
        records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return frozenset()
    return frozenset(
        record["path"]
        for record in records
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    )


def _versioned_schema(repo_root: Path, path: Path, family: str) -> Path:
    """Resolve the published schema an artifact names through its own ``schema_version``."""

    schema_version = _load_json(path)["schema_version"]
    return (
        repo_root / "contracts" / "schemas" / family / _schema_filename(schema_version)
    )


def _versioned_schema_targets(
    repo_root: Path, *, paths: list[str] | None = None
) -> list[ValidationTarget]:
    """Route every artifact that names its own published contract via ``schema_version``."""

    frozen = _frozen_historical_records(repo_root)
    targets: list[ValidationTarget] = []
    for route in _VERSIONED_SCHEMA_ROUTES:
        if paths is None:
            root = repo_root / route.prefix
            candidates = sorted(
                root.rglob(JSON_GLOB) if route.recursive else root.glob(JSON_GLOB)
            )
        else:
            candidates = [
                repo_root / raw_path
                for raw_path in paths
                if raw_path.startswith(route.prefix) and raw_path.endswith(JSON_SUFFIX)
            ]
        for candidate in candidates:
            relative = _routable(repo_root, candidate)
            if relative is None or relative in frozen:
                continue
            targets.append(
                ValidationTarget(
                    relative,
                    _repo_rel_from(
                        repo_root, _versioned_schema(repo_root, candidate, route.family)
                    ),
                    "schema",
                )
            )
    return targets


def _fixture_schema(repo_root: Path, path: Path) -> Path:
    relative = path.relative_to(repo_root / "contracts" / "fixtures")
    category = relative.parts[0]
    schema_name = relative.parts[1]
    if category == "semantic-profile":
        return repo_root / "contracts" / "schemas" / "profiles" / f"{schema_name}.json"
    return repo_root / "contracts" / "schemas" / category / f"{schema_name}.json"


def collect_validation_targets(
    repo_root: Path = REPO_ROOT, *, paths: list[str] | None = None
) -> list[ValidationTarget]:
    if paths is None:
        return _collect_full_targets(repo_root)
    if should_run_full_validation(paths):
        return _collect_full_targets(repo_root)

    targets = _authoring_adapter_targets(repo_root, paths=paths)
    targets.extend(_versioned_schema_targets(repo_root, paths=paths))
    already_routed = {target.path for target in targets}
    for raw_path in paths:
        if (
            raw_path in already_routed
            or _routable(repo_root, repo_root / raw_path) is None
        ):
            continue
        target = _changed_path_target(repo_root, raw_path)
        if target is not None:
            targets.append(target)
    return _dedupe_targets(targets)


def _changed_path_target(repo_root: Path, raw_path: str) -> ValidationTarget | None:
    """Route one changed path, or None when nothing validates it."""

    if not raw_path.endswith(JSON_SUFFIX):
        return None
    target: ValidationTarget | None = None
    if raw_path.startswith("contracts/schemas/"):
        target = ValidationTarget(raw_path, None, "metaschema")
    elif raw_path.startswith("contracts/concept-authority/"):
        schema_path = f"contracts/schemas/concept-authority/{Path(raw_path).name}"
        target = ValidationTarget(raw_path, schema_path, "schema")
    elif raw_path.startswith("contracts/fixtures/") and any(
        segment in raw_path
        for segment in ("/valid/", "/migration/", "/context-invalid/")
    ):
        schema = _fixture_schema(repo_root, repo_root / raw_path)
        target = ValidationTarget(raw_path, _repo_rel_from(repo_root, schema), "schema")
    return target


def covered_schema_paths(repo_root: Path = REPO_ROOT) -> set[str]:
    """Published schema paths that at least one routed, checked-in artifact exercises.

    Corpus routing is owned here, so the published-schema coverage gate
    (``tools/check_schema_coverage.py``) joins on this set instead of copying the
    route tables. A route added above is inherited without editing that gate. The
    set is non-empty by construction: an empty ``valid/`` directory, an
    ``invalid/``-only family, and a bare directory contribute nothing.
    """

    return {
        target.schema_path
        for target in collect_validation_targets(repo_root)
        if target.mode == "schema" and target.schema_path is not None
    }


def should_run_full_validation(paths: list[str]) -> bool:
    return any(
        path.startswith(SCHEMA_DRIVER_PATHS) or path == "tools/check_json_artifacts.py"
        for path in paths
    )


def _collect_full_targets(repo_root: Path) -> list[ValidationTarget]:
    targets = _authoring_adapter_targets(repo_root)
    targets.extend(_versioned_schema_targets(repo_root))
    for schema in sorted((repo_root / "contracts" / "schemas").rglob(JSON_GLOB)):
        relative = _routable(repo_root, schema)
        if relative is not None:
            targets.append(ValidationTarget(relative, None, "metaschema"))
    for artifact in sorted(
        (repo_root / "contracts" / "concept-authority").glob(JSON_GLOB)
    ):
        relative = _routable(repo_root, artifact)
        if relative is not None:
            targets.append(
                ValidationTarget(
                    relative,
                    f"contracts/schemas/concept-authority/{artifact.name}",
                    "schema",
                )
            )
    fixtures_root = repo_root / "contracts" / "fixtures"
    for pattern in (
        f"valid/{JSON_GLOB}",
        f"migration/{JSON_GLOB}",
        f"context-invalid/{JSON_GLOB}",
    ):
        for fixture in sorted(fixtures_root.rglob(pattern)):
            relative = _routable(repo_root, fixture)
            if relative is not None:
                targets.append(
                    ValidationTarget(
                        relative,
                        _repo_rel_from(repo_root, _fixture_schema(repo_root, fixture)),
                        "schema",
                    )
                )
    return _dedupe_targets(targets)


def _authoring_adapter_targets(
    repo_root: Path, *, paths: list[str] | None = None
) -> list[ValidationTarget]:
    targets = []
    for prefix, contract in _AUTHORING_ADAPTER_ROUTES.items():
        candidates = (
            (repo_root / prefix).glob(JSON_GLOB)
            if paths is None
            else (
                repo_root / path
                for path in paths
                if path.startswith(prefix) and path.endswith(JSON_SUFFIX)
            )
        )
        for path in candidates:
            relative = _routable(repo_root, path)
            if relative is None:
                continue
            targets.append(
                ValidationTarget(
                    relative,
                    f"contracts/schemas/authoring-adapters/{contract}.json",
                    "schema",
                )
            )
    return targets


def _dedupe_targets(targets: list[ValidationTarget]) -> list[ValidationTarget]:
    seen: set[tuple[str, str | None, str]] = set()
    ordered: list[ValidationTarget] = []
    for target in targets:
        key = (target.path, target.schema_path, target.mode)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(target)
    ordered.sort(key=lambda item: (item.mode, item.path))
    return ordered


def _run_check_jsonschema(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        frozen_tool_command(REPO_ROOT, "check-jsonschema", *args),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _validation_batches(targets: list[ValidationTarget]) -> list[ValidationBatch]:
    metaschema_paths = sorted(
        target.path for target in targets if target.mode == "metaschema"
    )
    schema_groups: dict[str, list[str]] = defaultdict(list)
    for target in targets:
        if target.mode != "schema":
            continue
        assert target.schema_path is not None
        schema_groups[target.schema_path].append(target.path)

    batches: list[ValidationBatch] = []
    if metaschema_paths:
        batches.append(ValidationBatch(tuple(metaschema_paths), None, "metaschema"))
    batches.extend(
        ValidationBatch(tuple(sorted(paths)), schema_path, "schema")
        for schema_path, paths in sorted(schema_groups.items())
    )
    return batches


def _validate_batch(batch: ValidationBatch) -> subprocess.CompletedProcess[str]:
    if batch.mode == "metaschema":
        return _run_check_jsonschema("--check-metaschema", *batch.paths)
    assert batch.schema_path is not None
    return _run_check_jsonschema("--schemafile", batch.schema_path, *batch.paths)


def validate_targets(targets: list[ValidationTarget]) -> list[str]:
    batches = _validation_batches(targets)
    if not batches:
        return []
    worker_value = os.environ.get(JSON_SCHEMA_WORKERS_ENV, "4")
    try:
        worker_count = int(worker_value)
    except ValueError as exc:
        raise ValueError(f"{JSON_SCHEMA_WORKERS_ENV} must be an integer") from exc
    if worker_count < 1:
        raise ValueError(f"{JSON_SCHEMA_WORKERS_ENV} must be at least one")
    with ThreadPoolExecutor(
        max_workers=min(worker_count, len(batches)), thread_name_prefix="json-schema"
    ) as executor:
        results = list(executor.map(_validate_batch, batches))

    failures: list[str] = []
    for batch, proc in zip(batches, results, strict=True):
        if proc.returncode == 0:
            continue
        details = (
            proc.stderr.strip() or proc.stdout.strip() or "schema validation failed"
        )
        failures.append(f"{', '.join(batch.paths)}: {details}")
    return failures


def main() -> int:
    args = parse_args()
    paths = (
        [Path(path).as_posix() for path in args.paths]
        if args.paths
        else changed_paths(
            REPO_ROOT,
            staged=args.staged,
            base_rev=args.base_rev,
        )
    )
    targets = collect_validation_targets(REPO_ROOT, paths=paths if paths else None)
    failures = validate_targets(targets)
    if failures:
        for failure in failures:
            print(f"[json-schema-validation] {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
