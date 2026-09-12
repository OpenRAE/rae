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
from tools.python_closure import frozen_tool_command


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
    parser = argparse.ArgumentParser(description="Validate published JSON Schemas and schema-governed JSON artifacts.")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes instead of working tree changes.",
    )
    parser.add_argument("--base-rev", help="Compare against a specific git revision.")
    parser.add_argument("paths", nargs="*", help="Explicit repo-relative paths to check.")
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_rel_from(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _schema_filename(schema_version: str) -> str:
    return f"{schema_version.replace('/', '-')}.json"


def _semantic_profile_schema(repo_root: Path, path: Path) -> Path:
    payload = _load_json(path)
    schema_version = payload["schema_version"]
    return repo_root / "contracts" / "schemas" / "profiles" / _schema_filename(schema_version)


def _backend_profile_schema(repo_root: Path, path: Path) -> Path:
    payload = _load_json(path)
    schema_version = payload["schema_version"]
    return repo_root / "contracts" / "schemas" / "profiles" / _schema_filename(schema_version)


def _random_stream_profile_schema(repo_root: Path, path: Path) -> Path:
    payload = _load_json(path)
    schema_version = payload["schema_version"]
    return repo_root / "contracts" / "schemas" / "profiles" / _schema_filename(schema_version)


def _participant_information_reconstruction_profile_schema(repo_root: Path, path: Path) -> Path:
    payload = _load_json(path)
    schema_version = payload["schema_version"]
    return repo_root / "contracts" / "schemas" / "profiles" / _schema_filename(schema_version)


def _random_stream_vector_schema(repo_root: Path, path: Path) -> Path:
    payload = _load_json(path)
    schema_version = payload["schema_version"]
    return repo_root / "contracts" / "schemas" / "profiles" / _schema_filename(schema_version)


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

    targets: list[ValidationTarget] = []
    for raw_path in paths:
        path = repo_root / raw_path
        if not path.exists():
            continue
        if raw_path.startswith("contracts/schemas/") and raw_path.endswith(".json"):
            targets.append(ValidationTarget(raw_path, None, "metaschema"))
            continue
        if raw_path.startswith("contracts/concept-authority/") and raw_path.endswith(".json"):
            targets.append(
                ValidationTarget(
                    raw_path,
                    f"contracts/schemas/concept-authority/{path.name}",
                    "schema",
                )
            )
            continue
        if raw_path.startswith("contracts/profiles/semantic/") and raw_path.endswith(".json"):
            targets.append(
                ValidationTarget(
                    raw_path,
                    _repo_rel_from(repo_root, _semantic_profile_schema(repo_root, path)),
                    "schema",
                )
            )
            continue
        if raw_path.startswith("contracts/profiles/backend/") and raw_path.endswith(".json"):
            targets.append(
                ValidationTarget(
                    raw_path,
                    _repo_rel_from(repo_root, _backend_profile_schema(repo_root, path)),
                    "schema",
                )
            )
            continue
        if raw_path.startswith("contracts/profiles/random-stream/") and raw_path.endswith(".json"):
            targets.append(
                ValidationTarget(
                    raw_path,
                    _repo_rel_from(repo_root, _random_stream_profile_schema(repo_root, path)),
                    "schema",
                )
            )
            continue
        if raw_path.startswith("contracts/profiles/participant-information-reconstruction/") and raw_path.endswith(
            ".json"
        ):
            targets.append(
                ValidationTarget(
                    raw_path,
                    _repo_rel_from(
                        repo_root,
                        _participant_information_reconstruction_profile_schema(repo_root, path),
                    ),
                    "schema",
                )
            )
            continue
        if raw_path.startswith("contracts/fixtures/random-stream-vectors/") and raw_path.endswith(".json"):
            targets.append(
                ValidationTarget(
                    raw_path,
                    _repo_rel_from(repo_root, _random_stream_vector_schema(repo_root, path)),
                    "schema",
                )
            )
            continue
        if "/valid/" in raw_path and raw_path.startswith("contracts/fixtures/") and raw_path.endswith(".json"):
            targets.append(
                ValidationTarget(
                    raw_path,
                    _repo_rel_from(repo_root, _fixture_schema(repo_root, path)),
                    "schema",
                )
            )
    return _dedupe_targets(targets)


def should_run_full_validation(paths: list[str]) -> bool:
    return any(path.startswith(SCHEMA_DRIVER_PATHS) or path == "tools/check_json_artifacts.py" for path in paths)


def _collect_full_targets(repo_root: Path) -> list[ValidationTarget]:
    targets: list[ValidationTarget] = []
    for schema in sorted((repo_root / "contracts" / "schemas").rglob("*.json")):
        targets.append(ValidationTarget(_repo_rel_from(repo_root, schema), None, "metaschema"))
    for artifact in sorted((repo_root / "contracts" / "concept-authority").glob("*.json")):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, artifact),
                f"contracts/schemas/concept-authority/{artifact.name}",
                "schema",
            )
        )
    for profile in sorted((repo_root / "contracts" / "profiles" / "semantic").glob("*.json")):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, profile),
                _repo_rel_from(repo_root, _semantic_profile_schema(repo_root, profile)),
                "schema",
            )
        )
    for profile in sorted((repo_root / "contracts" / "profiles" / "backend").glob("*.json")):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, profile),
                _repo_rel_from(repo_root, _backend_profile_schema(repo_root, profile)),
                "schema",
            )
        )
    for profile in sorted((repo_root / "contracts" / "profiles" / "random-stream").glob("*.json")):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, profile),
                _repo_rel_from(repo_root, _random_stream_profile_schema(repo_root, profile)),
                "schema",
            )
        )
    for profile in sorted(
        (repo_root / "contracts" / "profiles" / "participant-information-reconstruction").glob("*.json")
    ):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, profile),
                _repo_rel_from(
                    repo_root,
                    _participant_information_reconstruction_profile_schema(repo_root, profile),
                ),
                "schema",
            )
        )
    for vector in sorted((repo_root / "contracts" / "fixtures" / "random-stream-vectors").rglob("*.json")):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, vector),
                _repo_rel_from(repo_root, _random_stream_vector_schema(repo_root, vector)),
                "schema",
            )
        )
    for fixture in sorted((repo_root / "contracts" / "fixtures").rglob("valid/*.json")):
        targets.append(
            ValidationTarget(
                _repo_rel_from(repo_root, fixture),
                _repo_rel_from(repo_root, _fixture_schema(repo_root, fixture)),
                "schema",
            )
        )
    return _dedupe_targets(targets)


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
    metaschema_paths = sorted(target.path for target in targets if target.mode == "metaschema")
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
    with ThreadPoolExecutor(max_workers=min(worker_count, len(batches)), thread_name_prefix="json-schema") as executor:
        results = list(executor.map(_validate_batch, batches))

    failures: list[str] = []
    for batch, proc in zip(batches, results, strict=True):
        if proc.returncode == 0:
            continue
        details = proc.stderr.strip() or proc.stdout.strip() or "schema validation failed"
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
