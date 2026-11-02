"""Read and retain CI-collected public regression inputs for parity (#1778)."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from tools.parity_storage import read_blob, read_document
from tools.parity_support import Case, digest, encode

FORMAT = "raes-parity-regressions/v1"
FROZEN = Path("implementations/go/internal/parity/testdata/regressions")


def source_identity(repo: Path) -> dict[str, str]:
    paths = {
        "test_tree": "implementations/python/tests",
        "python_tree": "implementations/python/packages",
        "contracts_tree": "contracts",
        "examples_tree": "examples",
    }
    trees = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", *("HEAD:" + path for path in paths.values())], text=True
    ).splitlines()
    collector = {path.name: digest(path.read_bytes()) for path in sorted(Path(__file__).parent.glob("parity_*.py"))}
    environment = {
        name: digest((repo / "implementations/python" / name).read_bytes()) for name in ("uv.lock", "pyproject.toml")
    }
    return {
        **dict(zip(paths, trees, strict=True)),
        "collector_sha256": digest(encode(collector)),
        "environment_sha256": digest(encode(environment)),
    }


def read_inputs(
    root: Path, *, identity: dict[str, str] | None = None
) -> tuple[list[Case], dict[str, object], dict[Path, bytes]]:
    """Validate captured digests, merge worker origins, and freeze the input set."""
    manifest = root / "manifest.json"
    if manifest.is_file():
        document = read_document(root.parent, Path(root.name, "manifest.json"))
        if document.get("schema") != FORMAT:
            raise ValueError("unknown frozen regression input schema")
        if identity is not None and document.get("source_identity") != identity:
            raise ValueError("Python test inputs need a fresh CI capture")
        documents = [document]
        origin_complete = bool(document.get("complete"))
        identity = document.get("source_identity")
    else:
        documents = [json.loads(path.read_bytes()) for path in sorted(root.glob("*.json"))]
        if any(document.get("schema") != "raes-parity-inputs/v1" for document in documents):
            raise ValueError("unknown captured regression input schema")
        if identity is not None and any(document.get("source_identity") != identity for document in documents):
            raise ValueError("captured inputs came from different test or collector source")
        collected = {
            nodeid
            for document in documents
            for nodeid in document.get("expected_tests", document.get("collected_tests", []))
        }
        executed = {nodeid for document in documents for nodeid in document.get("tests", [])}
        origin_complete = bool(collected) and collected <= executed
    records: dict[str, dict[str, object]] = {}
    tests: set[str] = set()
    non_protocol: set[str] = set()
    blobs: dict[str, bytes] = {}
    for document in documents:
        tests.update(document.get("tests", []))
        non_protocol.update(document.get("non_protocol_tests", []))
        for key, record in document.get("inputs", {}).items():
            descriptor = {name: record[name] for name in ("surface", "command", "args", "files")}
            if digest(encode(descriptor)) != key:
                raise ValueError("a captured regression input does not match its digest")
            merged = records.setdefault(key, {**descriptor, "tests": set()})
            merged["tests"].update(record.get("tests", []))
            for reference in descriptor["files"].values():
                if not isinstance(reference, str) or not reference.startswith("sha256:"):
                    raise ValueError("invalid captured input digest")
                value = reference.removeprefix("sha256:")
                if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                    raise ValueError("invalid captured input digest")
                content = read_blob(root.parent, value) if manifest.is_file() else (root / "blobs" / value).read_bytes()
                if digest(content) != value:
                    raise ValueError("a captured input blob does not match its digest")
                blobs[value] = content
    records = {key: {**record, "tests": sorted(record["tests"])} for key, record in sorted(records.items())}
    document = {
        "schema": FORMAT,
        "source_identity": identity,
        "complete": origin_complete,
        "tests": sorted(tests),
        "non_protocol_tests": sorted(non_protocol),
        "inputs": records,
    }
    cases = [
        Case(
            record["surface"],
            record["command"],
            "regression/" + key,
            tuple(record["args"]),
            {name: blobs[value.removeprefix("sha256:")] for name, value in record["files"].items()},
        )
        for key, record in records.items()
    ]
    frozen = {Path("manifest.json"): encode(document), **{Path("blobs", key): value for key, value in blobs.items()}}
    inventory = {
        "complete": origin_complete,
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
    if not (root / "manifest.json").is_file():
        return 1
    document = read_document(root.parent, Path(root.name, "manifest.json"))
    if document.get("source_identity") != source_identity(args.repo_root):
        return 1
    _, inventory, _ = read_inputs(root, identity=document["source_identity"])
    return 0 if inventory["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
