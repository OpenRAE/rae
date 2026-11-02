"""Black-box parity recording keeps complete interfaces and exact input values."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from tools import parity_corpus as pc
from tools import parity_regressions as regressions
from tools import parity_surfaces as surfaces
from tools.parity_inputs import InputCollector
from tools.parity_support import Case, deterministic_ids, digest, encode, machine_payload, machine_schema


def test_schema_normalization_preserves_property_names_and_authored_defaults() -> None:
    schema = {
        "description": "free schema prose",
        "properties": {
            "description": {"type": "string", "description": "free field prose"},
            "title": {"default": {"description": "authored data"}},
        },
        "$defs": {"description": {"type": "number", "title": "free definition prose"}},
    }
    assert machine_schema(schema) == {
        "properties": {"description": {"type": "string"}, "title": {"default": {"description": "authored data"}}},
        "$defs": {"description": {"type": "number"}},
    }


def test_diagnostic_normalization_keeps_authored_payloads() -> None:
    payload = {
        "diagnostics": [{"code": "sdl.parse", "message": "free wording", "address": "/a"}],
        "payload": {"diagnostics": [{"message": "authored content"}]},
    }
    assert machine_payload(payload) == {
        "diagnostics": [{"code": "sdl.parse", "address": "/a"}],
        "payload": payload["payload"],
    }


def test_generated_ids_repeat_per_case_and_remain_unique_within_a_case() -> None:
    with deterministic_ids("first"):
        first = [uuid.uuid4(), uuid.uuid4()]
    with deterministic_ids("first"):
        repeated = [uuid.uuid4(), uuid.uuid4()]
    with deterministic_ids("second"):
        other = uuid.uuid4()
    assert first == repeated
    assert len(set(first)) == 2
    assert other not in first
    assert all(value.version == 4 for value in first)


def test_http_route_inventory_uses_templates_and_preserves_unknown_routes() -> None:
    routes = ["GET /operations/{operation_id}", "POST /workflows/{workflow_address}/cancel"]
    assert surfaces.route_key("GET", "/operations/a", routes) == routes[0]
    assert surfaces.route_key("POST", "/workflows/example/cancel", routes) == routes[1]
    assert surfaces.route_key("POST", "/operations/a", routes) == "POST unmatched"


@pytest.mark.parametrize("case", list(surfaces.http_trace_cases()), ids=lambda case: case.command)
def test_http_reference_traces_include_successful_state_changes(case: Case) -> None:
    output = pc.run(Path(__file__).resolve().parents[3], case)
    assert output["responses"][0]["status_code"] == 200
    assert output["responses"][0]["body"]["accepted"] is True
    assert all("status_code" in response for response in output["responses"])


def test_cli_registry_includes_nested_commands_and_real_flag_names() -> None:
    registry = surfaces.cli_registry()
    assert "runtime store restore" in registry
    assert "processor exploit-path" in registry
    flags = {option for parameter in registry["semantic parse"] for option in parameter["opts"]}
    assert {"--output", "--contract", "--migration-policy"} <= flags


def test_input_collector_preserves_local_imports_and_sandbox_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "root.yaml").write_text("name: root\nimports:\n  - source: local:module.yaml\n    namespace: kit\n")
    (repo / "module.yaml").write_text("name: module\n")
    collector = InputCollector(tmp_path / "capture", repo)
    collector.nodeid = "tests/test_example.py::test_imports"
    collector.cli(["sdl", "format", str(repo / "root.yaml")], {})
    record = next(iter(collector.records.values()))
    assert record["args"] == ["sdl", "format", "input/root.yaml"]
    assert set(record["files"]) == {"input/root.yaml", "input/module.yaml"}
    assert collector.blobs[record["files"]["input/module.yaml"]] == b"name: module\n"


def test_input_collector_refuses_links_and_does_not_inspect_external_paths(tmp_path: Path, monkeypatch) -> None:
    collector = InputCollector(tmp_path / "capture", tmp_path)
    link = tmp_path / "link.yaml"
    link.symlink_to("unavailable.yaml")
    with pytest.raises(ValueError, match="symbolic links"):
        collector.candidate_input(link)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", lambda path: pytest.fail("must not inspect an external path"))
        assert collector.candidate_input(Path("/outside-parity-input-roots/file")) == (None, None)


def test_regression_capture_deduplicates_inputs_and_binds_test_origins(tmp_path: Path, monkeypatch) -> None:
    identity = {"test_tree": "a" * 40, "collector_sha256": "b" * 64}
    monkeypatch.setattr(regressions, "source_identity", lambda repo: identity)
    collector = InputCollector(tmp_path, tmp_path)
    case = Case("mcp", "sdl_parse", "", (), {"arguments.json": encode({"sdl_content": "name: parity\n"})})
    for nodeid in ("tests/test_one.py::test_first", "tests/test_two.py::test_second"):
        collector.nodeid = nodeid
        collector.tests.add(nodeid)
        collector.collected_tests.add(nodeid)
        collector.add(case)
    collector.write("worker")
    cases, inventory, frozen = regressions.read_inputs(tmp_path, identity=identity)
    assert len(cases) == 1
    assert inventory["complete"] is True
    assert inventory["test_count"] == 2
    assert cases[0].files == case.files
    assert json.loads(frozen[Path("manifest.json")])["tests"] == sorted(collector.tests)
    blob = tmp_path / "blobs" / digest(case.files["arguments.json"])
    blob.write_bytes(b"changed")
    with pytest.raises(ValueError, match="does not match its digest"):
        regressions.read_inputs(tmp_path, identity=identity)


def test_incomplete_collection_cannot_claim_regression_coverage(tmp_path: Path, monkeypatch) -> None:
    identity = {"test_tree": "a" * 40, "collector_sha256": "b" * 64}
    monkeypatch.setattr(regressions, "source_identity", lambda repo: identity)
    collector = InputCollector(tmp_path, tmp_path)
    collector.collected_tests.add("tests/test_one.py::test_missing")
    collector.write("worker")
    _, inventory, _ = regressions.read_inputs(tmp_path, identity=identity)
    assert inventory["complete"] is False
