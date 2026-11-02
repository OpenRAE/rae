"""Read and retain CI-collected public regression inputs for parity (#1778)."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.parity_storage import read_blob, read_document
from tools.parity_support import MANIFEST_FILE, SHA256_PREFIX, Case, digest, encode

FORMAT = "raes-parity-regressions/v1"
FROZEN = Path("implementations/go/internal/parity/testdata/regressions")


def source_identity(repo: Path) -> dict[str, str]:
    trees = subprocess.check_output(
        [
            "git",
            "rev-parse",
            "HEAD:implementations/python/tests",
            "HEAD:implementations/python/packages",
            "HEAD:contracts",
            "HEAD:examples",
        ],
        cwd=repo,
        text=True,
    ).splitlines()
    collector = {path.name: digest(path.read_bytes()) for path in sorted(Path(__file__).parent.glob("parity_*.py"))}
    environment = {
        name: digest((repo / "implementations/python" / name).read_bytes()) for name in ("uv.lock", "pyproject.toml")
    }
    return {
        **dict(zip(("test_tree", "python_tree", "contracts_tree", "examples_tree"), trees, strict=True)),
        "collector_sha256": digest(encode(collector)),
        "environment_sha256": digest(encode(environment)),
    }


def frozen_document(root: Path, identity: dict[str, str] | None) -> dict[str, Any]:
    document = read_document(root.parent, Path(root.name, MANIFEST_FILE))
    if document.get("schema") != FORMAT:
        raise ValueError("unknown frozen regression input schema")
    if identity is not None and document.get("source_identity") != identity:
        raise ValueError("Python test inputs need a fresh CI capture")
    return document


def worker_documents(root: Path, identity: dict[str, str] | None) -> list[dict[str, Any]]:
    documents = [json.loads(path.read_bytes()) for path in sorted(root.glob("*.json"))]
    if any(document.get("schema") != "raes-parity-inputs/v1" for document in documents):
        raise ValueError("unknown captured regression input schema")
    if identity is not None and any(document.get("source_identity") != identity for document in documents):
        raise ValueError("captured inputs came from different test or collector source")
    return documents


def capture_complete(documents: list[dict[str, Any]]) -> bool:
    collected = {
        nodeid
        for document in documents
        for nodeid in document.get("expected_tests", document.get("collected_tests", []))
    }
    executed = {nodeid for document in documents for nodeid in document.get("tests", [])}
    return bool(collected) and collected <= executed


def input_documents(
    root: Path, identity: dict[str, str] | None
) -> tuple[list[dict[str, Any]], bool, dict[str, str] | None]:
    if (root / MANIFEST_FILE).is_file():
        document = frozen_document(root, identity)
        return [document], bool(document.get("complete")), document.get("source_identity")
    documents = worker_documents(root, identity)
    return documents, capture_complete(documents), identity


def input_blob(root: Path, reference: str, *, frozen: bool) -> tuple[str, bytes]:
    if not isinstance(reference, str) or not reference.startswith(SHA256_PREFIX):
        raise ValueError("invalid captured input digest")
    identity = reference.removeprefix(SHA256_PREFIX)
    if len(identity) != 64 or any(character not in "0123456789abcdef" for character in identity):
        raise ValueError("invalid captured input digest")
    content = read_blob(root.parent, identity) if frozen else (root / "blobs" / identity).read_bytes()
    if digest(content) != identity:
        raise ValueError("a captured input blob does not match its digest")
    return identity, content


def merge_input_records(root: Path, documents: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, bytes]]:
    records: dict[str, Any] = {}
    blobs: dict[str, bytes] = {}
    frozen = (root / MANIFEST_FILE).is_file()
    for document in documents:
        for key, record in document.get("inputs", {}).items():
            descriptor = {name: record[name] for name in ("surface", "command", "args", "files")}
            if digest(encode(descriptor)) != key:
                raise ValueError("a captured regression input does not match its digest")
            merged = records.setdefault(key, {**descriptor, "tests": set()})
            merged["tests"].update(record.get("tests", []))
            for reference in descriptor["files"].values():
                identity, content = input_blob(root, reference, frozen=frozen)
                blobs[identity] = content
    return {key: {**record, "tests": sorted(record["tests"])} for key, record in sorted(records.items())}, blobs


def regression_case(key: str, record: dict[str, Any], blobs: dict[str, bytes]) -> Case:
    return Case(
        record["surface"],
        record["command"],
        "regression/" + key,
        tuple(record["args"]),
        {name: blobs[value.removeprefix(SHA256_PREFIX)] for name, value in record["files"].items()},
    )


def read_inputs(
    root: Path, *, identity: dict[str, str] | None = None
) -> tuple[list[Case], dict[str, object], dict[Path, bytes]]:
    """Validate captured digests, merge worker origins, and freeze the input set."""
    documents, complete, identity = input_documents(root, identity)
    tests = {test for document in documents for test in document.get("tests", [])}
    non_protocol = {test for document in documents for test in document.get("non_protocol_tests", [])}
    records, blobs = merge_input_records(root, documents)
    document = {
        "schema": FORMAT,
        "source_identity": identity,
        "complete": complete,
        "tests": sorted(tests),
        "non_protocol_tests": sorted(non_protocol),
        "inputs": records,
    }
    cases = [regression_case(key, record, blobs) for key, record in records.items()]
    frozen = {Path(MANIFEST_FILE): encode(document), **{Path("blobs", key): value for key, value in blobs.items()}}
    inventory = {
        "complete": complete,
        "test_count": len(tests),
        "input_count": len(cases),
        "non_protocol_tests": sorted(non_protocol),
        "source_identity": identity,
        "origins": {key: value["tests"] for key, value in records.items()},
    }
    return cases, inventory, frozen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("current",))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.repo_root / FROZEN
    if not (root / MANIFEST_FILE).is_file():
        return 1
    document = read_document(root.parent, Path(root.name, MANIFEST_FILE))
    if document.get("source_identity") != source_identity(args.repo_root):
        return 1
    _, inventory, _ = read_inputs(root, identity=document["source_identity"])
    return 0 if inventory["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
