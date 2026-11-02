"""Black-box parity recording keeps complete interfaces and exact input values."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from starlette.requests import Request
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


def test_http_replay_delivers_recorded_chunks_to_the_application() -> None:
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()

    @app.post("/chunks")
    async def chunks(request: Request):
        return [len(chunk) async for chunk in request.stream()]

    request = {
        "method": "POST",
        "path": "/chunks",
        "body_file": "body.bin",
        "chunk_sizes": [2, 3],
        "streamed": True,
        "stream_complete": True,
    }
    with TestClient(app) as client:
        result = surfaces.send_http(client, request, {"body.bin": b"abcde"})
        with pytest.raises(ValueError, match="chunk sizes"):
            surfaces.send_http(client, {**request, "chunk_sizes": [2, 2]}, {"body.bin": b"abcde"})
    assert result["status_code"] == 200
    assert result["body"] == [2, 3, 0]


def test_http_replay_preserves_size_limits_and_invalid_content_length() -> None:
    request = {
        "method": "POST",
        "path": "/operations/provisioning",
        "principal": "operator",
        "limits": {"max_request_bytes": 32},
        "headers": {"content-type": "application/json"},
        "body_file": "body.bin",
        "chunk_sizes": [16, 32, 16],
        "streamed": True,
        "stream_complete": True,
    }
    with surfaces.http_client(request) as client:
        result = surfaces.send_http(client, request, {"body.bin": b"x" * 64})
        assert result["status_code"] == 413
        malformed = {**request, "streamed": False, "chunk_sizes": [], "headers": {"content-length": "invalid"}}
        assert surfaces.send_http(client, malformed, {"body.bin": b"{}"})["status_code"] == 400
        assert (
            surfaces.send_http(client, {"method": "GET", "path": "/snapshot", "principal": "invalid"}, {})[
                "status_code"
            ]
            == 401
        )


def test_direct_asgi_capture_replays_the_consumed_oversized_stream(tmp_path: Path) -> None:
    import asyncio

    collector = InputCollector(tmp_path, Path(__file__).resolve().parents[3])
    collector.nodeid = "tests/test_ingress.py::test_raw_asgi"
    collector.install()
    sent = []
    delivered = 0

    async def receive():
        nonlocal delivered
        delivered += 1
        return {"type": "http.request", "body": b"x" * 32, "more_body": True}

    async def send(message):
        sent.append(message)

    try:
        with surfaces.http_client({"limits": {"max_request_bytes": 64}}) as client:
            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/operations/provisioning",
                "raw_path": b"/operations/provisioning",
                "query_string": b"",
                "root_path": "",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1),
                "server": ("testserver", 80),
            }
            asyncio.run(client.app(scope, receive, send))
    finally:
        collector.close()
    assert delivered == 3
    assert any(message.get("status") == 413 for message in sent)
    records = [record for record in collector.records.values() if record["surface"] == "http"]
    assert len(records) == 1
    files = {name: collector.blobs[value.removeprefix("sha256:")] for name, value in records[0]["files"].items()}
    request = json.loads(files["request.json"])
    assert request["chunk_sizes"] == [32, 32, 32]
    assert request["stream_complete"] is False
    with surfaces.http_client(request) as client:
        assert surfaces.send_http(client, request, files)["status_code"] == 413


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
    assert collector.blobs[record["files"]["input/module.yaml"].removeprefix("sha256:")] == b"name: module\n"


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


@pytest.mark.parametrize("name", ["file/child", "x" * 300])
def test_input_collector_leaves_invalid_host_paths_to_the_original_call(tmp_path: Path, name: str) -> None:
    (tmp_path / "file").write_bytes(b"regular file")
    collector = InputCollector(tmp_path / "capture", tmp_path)
    assert collector.candidate_input(tmp_path / name) == (None, None)


def test_input_observers_preserve_results_logging_and_profile(tmp_path: Path, monkeypatch) -> None:
    import asyncio
    import logging
    import sys
    from types import ModuleType

    from hypothesis import settings
    from jsonschema import Draft202012Validator
    from pydantic import ValidationError
    from raes_cli.main import app
    from raes_contracts.execution_policy import ExecutionPolicy
    from raes_contracts.observation_demand import ObservationDemandDocument
    from typer.testing import CliRunner

    repo = Path(__file__).resolve().parents[3]
    collector = InputCollector(tmp_path / "capture", repo)
    collector.nodeid = "tests/test_observers.py::test_all_boundaries"
    root = logging.root
    handlers, level = root.handlers[:], root.level
    profile = settings.get_current_profile_name()
    original_uuid = uuid.uuid4
    collector.install()
    late_module = ModuleType("raes_parity_collector_lazy")
    monkeypatch.setitem(sys.modules, late_module.__name__, late_module)
    late_module.uuid4 = uuid.uuid4
    try:
        assert root.handlers == handlers
        assert root.level == level
        source = tmp_path / "source.yaml"
        source.write_text("name: parity\n")
        result = CliRunner().invoke(app, ["semantic", "validate", str(source)])
        assert result.exit_code == 0
        tool_result = asyncio.run(surfaces.mcp_server().call_tool("sdl_parse", {"sdl_content": "name: parity\n"}))
        assert tool_result is not None
        with surfaces.http_client({"limits": {"max_request_bytes": 32}}) as client:
            response = client.get("/participants/participant.parity/status")
        assert response.status_code == 401
        http_record = next(record for record in collector.records.values() if record["surface"] == "http")
        request = json.loads(collector.blobs[http_record["files"]["request.json"].removeprefix("sha256:")])
        assert request["limits"]["max_request_bytes"] == 32
        with pytest.raises(ValidationError):
            ExecutionPolicy.model_validate({"schema_version": "invalid"})
        with pytest.raises(ValidationError):
            ObservationDemandDocument(schema_version="invalid")
        entry = json.loads((repo / "contracts/schema-publication/entries/observation-demand-v1.json").read_bytes())
        schema = json.loads((repo / entry["schema_path"]).read_bytes())
        assert list(Draft202012Validator(schema).iter_errors({"schema_probe": "json-schema"}))
        observed = [
            json.loads(collector.blobs[record["files"]["payload.json"].removeprefix("sha256:")])
            for record in collector.records.values()
            if record["surface"] == "schema" and record["args"] == ["observation-demand-v1"]
        ]
        assert {"schema_version": "invalid"} in observed
        assert {"schema_probe": "json-schema"} in observed
        assert {record["surface"] for record in collector.records.values()} >= {"cli", "mcp", "http", "schema"}
    finally:
        collector.close()
    assert settings.get_current_profile_name() == profile
    assert late_module.uuid4 is original_uuid


def test_regression_identity_binds_product_data_and_environment(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def git_output(command, *, text):
        calls.append(command)
        return "\n".join(character * 40 for character in "abcd") + "\n"

    monkeypatch.setattr(regressions.subprocess, "check_output", git_output)
    environment = tmp_path / "implementations/python"
    environment.mkdir(parents=True)
    (environment / "uv.lock").write_text("locked dependencies")
    (environment / "pyproject.toml").write_text("test configuration")
    identity = regressions.source_identity(tmp_path)
    assert {key: identity[key] for key in ("test_tree", "python_tree", "contracts_tree", "examples_tree")} == {
        "test_tree": "a" * 40,
        "python_tree": "b" * 40,
        "contracts_tree": "c" * 40,
        "examples_tree": "d" * 40,
    }
    assert calls[0][-4:] == [
        "HEAD:implementations/python/tests",
        "HEAD:implementations/python/packages",
        "HEAD:contracts",
        "HEAD:examples",
    ]
    assert len(identity["collector_sha256"]) == len(identity["environment_sha256"]) == 64
    (environment / "uv.lock").write_text("updated dependencies")
    assert regressions.source_identity(tmp_path)["environment_sha256"] != identity["environment_sha256"]


def test_deterministic_ids_restore_aliases_created_by_lazy_imports(monkeypatch) -> None:
    import sys
    from types import ModuleType

    module = ModuleType("raes_parity_lazy_fixture")
    original_uuid = uuid.uuid4
    with deterministic_ids("lazy-import"):
        monkeypatch.setitem(sys.modules, module.__name__, module)
        module.uuid4 = uuid.uuid4
        assert module.uuid4 is not original_uuid
    assert module.uuid4 is original_uuid


def test_cli_collector_captures_conformance_directories_and_option_assignments(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    fixtures = repo / "contracts/fixtures"
    profiles = repo / "contracts/profiles/backend"
    (fixtures / "sample/valid").mkdir(parents=True)
    profiles.mkdir(parents=True)
    (fixtures / "sample/valid/input.json").write_text('{"value": 1}')
    collector = InputCollector(tmp_path / "capture", repo)
    collector.nodeid = "tests/test_example.py::test_conformance"
    collector.cli(["conformance", "backend", "--format=json", f"--fixtures-root={fixtures}"], {})
    record = next(iter(collector.records.values()))
    assert record["command"] == "conformance backend"
    assert record["args"][:4] == ["conformance", "backend", "--format", "json"]
    assert not any(argument.startswith(str(tmp_path)) for argument in record["args"])
    assert any(name.endswith("sample/valid/input.json") for name in record["files"])
    assert all(reference.startswith("sha256:") for reference in record["files"].values())
    setup = json.loads(collector.blobs[record["files"]["setup.json"].removeprefix("sha256:")])
    assert len(setup["directories"]) == 2
    assert any(directory.endswith("profiles/backend") for directory in setup["directories"])


def test_cli_command_identity_follows_command_position_and_root_options() -> None:
    assert InputCollector.command(["semantic", "validate", "runtime", "store", "check"]) == "semantic validate"
    assert (
        InputCollector.command(["--log-level", "warning", "runtime", "store", "check", "file"]) == "runtime store check"
    )
    assert InputCollector.command(["--version", "runtime", "store", "check"]) == "root"


def test_capture_reducer_requires_every_partition_of_the_full_collection(tmp_path: Path, monkeypatch) -> None:
    identity = {"test_tree": "a" * 40, "collector_sha256": "b" * 64}
    monkeypatch.setattr(regressions, "source_identity", lambda repo: identity)
    expected = {"tests/test_one.py::test_first", "tests/test_two.py::test_second"}
    for index, nodeid in enumerate(sorted(expected)):
        collector = InputCollector(tmp_path, tmp_path)
        collector.expected_tests = expected
        collector.collected_tests = {nodeid}
        collector.tests = {nodeid}
        collector.write("shard-" + str(index))
        _, inventory, _ = regressions.read_inputs(tmp_path, identity=identity)
        assert inventory["complete"] is (index == 1)


def test_cli_observers_cover_console_entrypoint_and_subprocess_inputs(tmp_path: Path, monkeypatch) -> None:
    import subprocess
    import sys

    import raes_cli.entrypoint as entrypoint

    source = tmp_path / "source.yaml"
    source.write_text("name: subprocess-input\n")
    outcome = object()
    calls = []

    def original_run(*args, **kwargs):
        calls.append((args, kwargs))
        return outcome

    monkeypatch.setattr(subprocess, "run", original_run)
    collector = InputCollector(tmp_path / "capture", Path(__file__).resolve().parents[3])
    collector.nodeid = "tests/test_observers.py::test_console"
    collector.install()
    try:
        monkeypatch.setattr(sys, "argv", ["raes", "-V"])
        entrypoint.main()
        assert (
            subprocess.run(["raes", "semantic", "validate", "source.yaml"], cwd=tmp_path, input="standard input")
            is outcome
        )
    finally:
        collector.close()
    records = list(collector.records.values())
    assert any(record["args"] == ["-V"] for record in records)
    invocation = next(record for record in records if record["command"] == "semantic validate")
    assert invocation["args"] == ["semantic", "validate", "input/source.yaml"]
    assert set(invocation["files"]) == {"input/source.yaml", "stdin.bin"}
    assert collector.blobs[invocation["files"]["stdin.bin"].removeprefix("sha256:")] == b"standard input"
    assert calls[-1][1] == {"cwd": tmp_path, "input": "standard input"}
