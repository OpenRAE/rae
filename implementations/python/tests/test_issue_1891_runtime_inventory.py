"""Check the extraction inventory against Git objects, without copying source."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "docs/decisions/issue-1891-runtime-extraction-inventory.json"


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _inventory() -> dict:
    return json.loads(INVENTORY.read_text())


def _owner_rule(rules: list[dict], path: str) -> dict:
    matches = [r for r in rules if path == r["old_prefix"] or path.startswith(r["old_prefix"] + "/")]
    assert matches, f"unowned path: {path}"
    matches.sort(key=lambda r: len(r["old_prefix"]), reverse=True)
    assert len(matches) == 1 or len(matches[0]["old_prefix"]) != len(matches[1]["old_prefix"])
    return matches[0]


def test_pinned_inventory_covers_every_source_object_once() -> None:
    inventory = _inventory()
    source = inventory["source"]
    raw = _git("ls-tree", "-r", "-z", "--full-tree", source["commit"])
    assert _git("rev-parse", source["commit"] + "^{tree}").decode().strip() == source["tree"]
    assert hashlib.sha256(raw).hexdigest() == source["manifest_sha256"]
    records = raw.split(b"\0")[:-1]
    assert len(records) == source["path_count"]
    groups: dict[str, list[bytes]] = defaultdict(list)
    rules = inventory["rules"]
    assert len({r["old_prefix"] for r in rules}) == len(rules)
    for record in records:
        path = record.split(b"\t", 1)[1].decode()
        groups[_owner_rule(rules, path)["old_prefix"]].append(record + b"\0")
    for rule in rules:
        group = groups[rule["old_prefix"]]
        assert group, f"unused rule: {rule['old_prefix']}"
        assert len(group) == rule["path_count"]
        assert hashlib.sha256(b"".join(group)).hexdigest() == rule["manifest_sha256"]


def test_inventory_destinations_and_provenance_are_unambiguous() -> None:
    inventory = _inventory()
    owners = inventory["owners"]
    destinations: set[tuple[str, str]] = set()
    raw = _git("ls-tree", "-r", "-z", "--full-tree", inventory["source"]["commit"])
    for record in raw.split(b"\0")[:-1]:
        path = record.split(b"\t", 1)[1].decode()
        rule = _owner_rule(inventory["rules"], path)
        assert rule["owner"] in owners
        assert rule["disposition"] in {"retained", "moved", "consumed-by-version", "migration-only"}
        prefix = rule["new_prefix"]
        if rule["disposition"] == "migration-only":
            assert prefix is None
            continue
        assert isinstance(prefix, str)
        destination = prefix + path[len(rule["old_prefix"]) :]
        parsed = PurePosixPath(destination)
        assert not parsed.is_absolute() and ".." not in parsed.parts and str(parsed) == destination
        identity = rule["owner"], destination
        assert identity not in destinations, f"colliding destination: {identity}"
        destinations.add(identity)
    for name, oid in inventory["provenance"].items():
        assert _git("rev-parse", inventory["source"]["commit"] + ":" + name).decode().strip() == oid
        assert _owner_rule(inventory["rules"], name)["owner"] == "rae"


def test_repository_edges_and_executable_publishers_preserve_authority() -> None:
    inventory = _inventory()
    assert inventory["product_imports"] == {"rae": [], "runtime": ["rae"]}
    executables = inventory["executables"]
    assert len({e["name"] for e in executables}) == len(executables)
    assert {e["name"]: e["publisher"] for e in executables} == {"raes": "runtime", "raes-mcp": "rae"}
    for executable in executables:
        publisher = executable["publisher"]
        allowed = {publisher, *inventory["product_imports"][publisher]}
        assert set(executable["implementation_owners"]) <= allowed
    assert inventory["destination"]["transfer_authorized"] is False
    assert inventory["release"]["gate_issue"] == 1804
    assert inventory["release"]["earlier_runtime_launch"] is False


def test_model_binds_inventory_evidence() -> None:
    model = json.loads((ROOT / "implementations/architecture.json").read_text())
    decision = "docs/decisions/issue-1891-runtime-repository-boundary.md"
    content = (ROOT / decision).read_bytes()
    assert model["sources"][decision] == hashlib.sha256(content).hexdigest()
    assert f"<!-- extraction-inventory {hashlib.sha256(INVENTORY.read_bytes()).hexdigest()} -->" in content.decode()


@pytest.mark.parametrize(
    ("path", "owner", "disposition"),
    [
        ("implementations/python/packages/raes/runtime_inventory.py", "rae", "migration-only"),
        ("implementations/python/packages/raes_processor/trial_compiler/__init__.py", "rae", "migration-only"),
        ("implementations/python/packages/raes_runtime/runtime_engine.py", "runtime", "migration-only"),
        ("implementations/python/packages/raes_operations/run_artifacts.py", "runtime", "migration-only"),
        ("implementations/python/packages/raes_conformance/conformance/fixture_suite.py", "rae", "migration-only"),
        ("implementations/python/packages/raes_conformance/conformance/processor.py", "rae", "migration-only"),
        ("implementations/python/packages/raes_conformance/conformance/report.py", "rae", "migration-only"),
        (
            "implementations/python/packages/raes_conformance/conformance/modular_control_report.py",
            "rae",
            "migration-only",
        ),
        (
            "implementations/python/packages/raes_conformance/conformance/modular_control_types.py",
            "rae",
            "migration-only",
        ),
        (
            "implementations/python/packages/raes_conformance/conformance/mixed_backend_types.py",
            "rae",
            "migration-only",
        ),
        ("implementations/python/packages/raes_conformance/conformance/target.py", "runtime", "migration-only"),
        ("contracts/schemas/experiment-core/materialization-archive-record-v1.json", "rae", "consumed-by-version"),
        ("docs/research/execution-architecture/evidence.json", "rae", "retained"),
        ("implementations/go/internal/base/clock/clock.go", "rae", "retained"),
        ("implementations/go/internal/parity/runner-inventory.json", "rae", "migration-only"),
    ],
)
def test_mixed_responsibilities_use_their_semantic_owner(path: str, owner: str, disposition: str) -> None:
    rule = _owner_rule(_inventory()["rules"], path)
    assert (rule["owner"], rule["disposition"]) == (owner, disposition)
