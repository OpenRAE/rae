"""Public CLI, MCP and HTTP adapters for the golden parity corpus (#1778)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import click
import yaml
from mcp.server.fastmcp.exceptions import ToolError
from raes.module_registry import LOCKFILE_NAME, TRUST_POLICY_NAME
from raes_backend_stubs.stubs import create_stub_target
from raes_cli.main import app
from raes_mcp.server import create_server
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from starlette.testclient import TestClient
from typer.main import get_command

from tools.parity_support import (
    Case,
    deterministic_ids,
    digest,
    encode,
    fixed_clock,
    json_output,
    machine_payload,
    machine_schema,
)
from tools.tooling_artifact_policy_common import is_regular_repo_file

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


@lru_cache(maxsize=1)
def cli_registry() -> dict[str, object]:
    """Read command and flag names from the actual Click/Typer registry."""
    commands: dict[str, object] = {}

    def visit(command: click.Command, prefix: str) -> None:
        context = click.Context(command)
        parameters = []
        for parameter in command.params:
            info = parameter.to_info_dict()
            for key in ("help", "prompt"):
                info.pop(key, None)
            if isinstance(info.get("default"), Path):
                info["default"] = str(info["default"])
            parameters.append(info)
        commands[prefix] = parameters
        if isinstance(command, click.Group):
            for name in command.list_commands(context):
                child = command.get_command(context, name)
                if child is None:
                    raise ValueError(f"registered CLI command {name} is unavailable")
                visit(child, (prefix + " " + name).strip())

    visit(get_command(app), "")
    return commands


@lru_cache(maxsize=1)
def mcp_server():
    return create_server()


def mcp_registry() -> dict[str, object]:
    return {
        tool.name: machine_schema(tool.model_dump(mode="json", exclude_none=True))
        for tool in asyncio.run(mcp_server().list_tools())
    }


@contextmanager
def http_client(authority: dict[str, object] | None = None) -> Iterator[TestClient]:
    """The portable HTTP fixture: an empty in-memory stub and a fixed clock."""
    target = create_stub_target(wall_clock=fixed_clock)
    plane = RuntimeControlPlane(target, wall_clock=fixed_clock)
    principals = {
        name: ControlPlaneIdentity(identity=name, target_name=target.name, roles=frozenset(roles))
        for name, roles in {
            "operator": {ControlPlaneRole.OPERATOR, ControlPlaneRole.AUDITOR, ControlPlaneRole.BACKEND},
            "auditor": {ControlPlaneRole.AUDITOR},
        }.items()
    }
    if authority is not None and "roles" in authority:
        principals["recorded"] = ControlPlaneIdentity(
            identity=authority.get("identity", "recorded"),
            target_name=target.name if authority.get("target_bound", True) else "other-target",
            roles=frozenset(ControlPlaneRole(role) for role in authority["roles"]),
        )
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities=principals,
    )
    served = create_control_plane_app(plane, security=security)
    with TestClient(served, raise_server_exceptions=False) as client:
        yield client


def http_schema() -> dict[str, object]:
    with http_client() as client:
        return machine_schema(client.app.openapi())


def http_registry(schema: dict[str, object]) -> list[str]:
    return sorted(
        method.upper() + " " + path
        for path, operations in schema["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    )


def route_key(method: str, path: str, registry: list[str]) -> str:
    for key in registry:
        declared_method, template = key.split(" ", 1)
        pattern = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(template))
        if declared_method == method.upper() and re.fullmatch(pattern, path):
            return key
    return method.upper() + " unmatched"


def source_files(repo: Path, source: Path) -> dict[str, bytes]:
    """Copy only the source and its local imports, preserving relative paths."""
    files: dict[str, bytes] = {}

    def add(path: Path) -> None:
        relative = path.relative_to(repo).as_posix()
        name = "repo/" + relative
        if name in files:
            return
        if not is_regular_repo_file(repo, relative):
            raise ValueError(f"parity input is not a regular repository file: {relative}")
        files[name] = path.read_bytes()
        text = files[name].decode("utf-8", errors="replace")
        for reference in re.findall(r"source:\s*['\"]?local:([^\s'\"]+)", text):
            dependency = (path.parent / reference).resolve()
            if not dependency.is_relative_to(repo):
                raise ValueError("a parity source import escapes the repository")
            if dependency.exists():
                add(dependency)
        for name in (LOCKFILE_NAME, TRUST_POLICY_NAME):
            candidate = path.parent / name
            if candidate.is_file():
                relative = candidate.relative_to(repo).as_posix()
                if not is_regular_repo_file(repo, relative):
                    raise ValueError("a parity source dependency is not a regular file")
                files["repo/" + relative] = candidate.read_bytes()

    add(source)
    return files


def extended_cli_cases(repo: Path, sources: list[Path]) -> Iterator[Case]:
    for source in sources:
        name = source.relative_to(repo).as_posix()
        input_name = "repo/" + name
        files = source_files(repo, source)
        for command, arguments in (
            ("sdl format", ("sdl", "format", input_name)),
            ("sdl resolve", ("sdl", "resolve", input_name)),
            ("sdl verify-imports", ("sdl", "verify-imports", input_name)),
            ("sdl publish", ("sdl", "publish", input_name, "--output-dir", "layout")),
            ("processor plan", ("processor", "plan", input_name, "--format", "json")),
            ("processor reconcile", ("processor", "reconcile", input_name, input_name, "--format", "json")),
            ("processor satisfiability", ("processor", "satisfiability", input_name)),
        ):
            yield Case("cli", command, name, arguments, files)
        setup = encode({"commands": [["sdl", "resolve", input_name]]})
        yield Case(
            "cli",
            "sdl verify-imports",
            name + "/resolved",
            ("sdl", "verify-imports", input_name),
            {**files, "setup.json": setup},
        )
    for command, arguments in (
        ("processor manifest", ("processor", "manifest")),
        ("conformance backend", ("conformance", "backend", "--format", "json")),
        ("conformance processor", ("conformance", "processor", "--format", "json")),
    ):
        if command == "conformance backend":
            roots = (repo / "contracts/fixtures", repo / "contracts/profiles/backend")
            files = {
                "repo/" + path.relative_to(repo).as_posix(): path.read_bytes()
                for root in roots
                for path in sorted(root.rglob("*"))
                if path.suffix in {".json", ".yaml", ".yml"} and path.is_file()
            }
            arguments = (
                *arguments,
                "--fixtures-root",
                "repo/contracts/fixtures",
                "--profiles-root",
                "repo/contracts/profiles/backend",
            )
            yield Case("cli", command, "reference", arguments, files)
        else:
            yield Case("cli", command, "reference", arguments, {})
    yield Case("cli", "root", "version", ("--version",), {})
    exploit_fixtures = {
        fixture
        for directory in (repo / "contracts/fixtures").rglob("*exploit*")
        if directory.is_dir()
        for fixture in directory.rglob("*.json")
    }
    for fixture in sorted(exploit_fixtures):
        name = fixture.relative_to(repo).as_posix()
        yield Case(
            "cli",
            "processor exploit-path",
            name,
            ("processor", "exploit-path", "input.json"),
            {"input.json": fixture.read_bytes()},
        )
    for operation in ("check", "backup", "restore"):
        paths = ("store.sqlite3", "backup.sqlite3") if operation != "check" else ("store.sqlite3",)
        arguments = ("runtime", "store", operation, *paths, "--target", "stub", "--run-scope", "run:parity")
        yield Case("cli", "runtime store " + operation, "missing-store", arguments, {})
        setup = {"store": "store.sqlite3", "commands": []}
        if operation == "restore":
            setup["commands"] = [
                [
                    "runtime",
                    "store",
                    "backup",
                    "store.sqlite3",
                    "backup.sqlite3",
                    "--target",
                    "stub",
                    "--run-scope",
                    "run:parity",
                ]
            ]
            arguments = (
                "runtime",
                "store",
                "restore",
                "backup.sqlite3",
                "restored.sqlite3",
                "--target",
                "stub",
                "--run-scope",
                "run:parity",
            )
        yield Case("cli", "runtime store " + operation, "admitted-store", arguments, {"setup.json": encode(setup)})


def mcp_cases(repo: Path, sources: list[Path], registry: dict[str, object]) -> Iterator[Case]:
    presets = {
        "sdl_section_reference": {"section": "nodes"},
        "sdl_get_example": {"name": "hospital-ransomware-surgery-day"},
        "experiment_get_example": {"name": "smoke"},
        "sdl_validate_section": {"section": "nodes", "section_yaml": "web: {type: compute}"},
        "sdl_get_element": {"element_name": "nodes.web"},
        "sdl_references": {"symbol": "web"},
        "sdl_apply_edit": {"operation": "set", "pointer": "/name", "value_json": '"changed"'},
    }
    for name, specification in sorted(registry.items()):
        parameters = dict(presets.get(name, {}))
        properties = specification["inputSchema"].get("properties", {})
        if "sdl_content" in properties:
            parameters["sdl_content"] = "name: parity\nnodes:\n  web: {type: compute}\n"
        if "spec_content" in properties:
            parameters["spec_content"] = "spec_id: parity\n"
        for required in specification["inputSchema"].get("required", []):
            parameters.setdefault(required, "")
        yield Case("mcp", name, "reference", (), {"arguments.json": encode(parameters)})
        yield Case("mcp", name, "invalid-arguments", (), {"arguments.json": encode({key: [] for key in properties})})
        if "sdl_content" in properties:
            for source in sources:
                invocation = {**parameters, "sdl_content": source.read_text(encoding="utf-8")}
                yield Case("mcp", name, source.relative_to(repo).as_posix(), (), {"arguments.json": encode(invocation)})
        if name == "experiment_validate":
            for source in sorted((repo / "examples/experiments").glob("*.yaml")):
                yield Case(
                    "mcp",
                    name,
                    source.relative_to(repo).as_posix(),
                    (),
                    {"arguments.json": encode({"spec_content": source.read_text(encoding="utf-8")})},
                )


def http_cases(schema: dict[str, object]) -> Iterator[Case]:
    for key in http_registry(schema):
        method, path = key.split(" ", 1)
        path = re.sub(r"\{[^}]+\}", "missing", path)
        for principal in ("anonymous", "operator", "auditor"):
            request = {"method": method, "path": path, "principal": principal}
            if method not in {"GET", "HEAD"}:
                request["json"] = {}
            yield Case("http", key, principal + "/empty-reference-state", (), {"request.json": encode(request)})
    for domain, payload in {
        "provisioning": {"operations": [], "diagnostics": [], "realization_authority": []},
        "orchestration": {"operations": [], "startup_order": [], "diagnostics": []},
        "evaluation": {"operations": [], "startup_order": [], "diagnostics": []},
    }.items():
        request = {"method": "POST", "path": "/operations/" + domain, "principal": "operator", "json": payload}
        yield Case("http", "POST /operations/" + domain, "empty-plan", (), {"request.json": encode(request)})


def run_mcp(case: Case) -> dict[str, object]:
    try:
        result = asyncio.run(mcp_server().call_tool(case.command, json.loads(case.files["arguments.json"])))
    except ToolError:
        return {"is_error": True}
    content, structured = result
    blocks = []
    for block in content:
        document = block.model_dump(mode="json", exclude_none=True)
        if document.get("type") == "text":
            document["text"] = machine_text(document["text"])
        blocks.append(document)
    structured = machine_payload(structured)
    if isinstance(structured, dict) and isinstance(structured.get("result"), str):
        structured["result"] = machine_text(structured["result"])
    return {"is_error": False, "content": blocks, "structured_content": structured}


def machine_text(text: str) -> object:
    result = json_output(text)
    if result is not None:
        return result
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return value if isinstance(value, (dict, list)) else None


def run_http(case: Case) -> dict[str, object]:
    request = json.loads(case.files["request.json"])
    with http_client(request) as client:
        if "requests" not in request:
            return send_http(client, request, case.files)
        bindings = {}
        responses = []
        for original in request["requests"]:
            step = dict(original)
            for key, value in step.items():
                if isinstance(value, str):
                    for name, replacement in bindings.items():
                        value = value.replace("${" + name + "}", replacement)
                    step[key] = value
            response = send_http(client, step, case.files)
            responses.append(response)
            for name, pointer in original.get("save", {}).items():
                value = response
                for component in pointer.strip("/").split("/"):
                    value = value[component]
                if not isinstance(value, str):
                    raise ValueError("an HTTP trace binding must be a string")
                bindings[name] = value
        return {"responses": responses}


def send_http(client: TestClient, request: dict[str, object], files: dict[str, bytes]) -> dict[str, object]:
    principal = request.get("principal", "anonymous")
    headers = dict(request.get("headers", {}))
    if principal != "anonymous":
        headers["x-raes-client-identity"] = principal
        if request.get("verified", True):
            headers["x-raes-client-verified"] = "true"
    payload = {key: request[key] for key in ("json", "content") if key in request}
    if "body_file" in request:
        payload["content"] = files[request["body_file"]]
    response = client.request(
        request["method"],
        request["path"],
        headers=headers,
        **payload,
    )
    output = json_output(response.text)
    if isinstance(output, dict) and isinstance(output.get("detail"), str):
        output.pop("detail")
    elif isinstance(output, dict) and isinstance(output.get("detail"), list):
        for detail in output["detail"]:
            if isinstance(detail, dict):
                detail.pop("msg", None)
                detail.pop("ctx", None)
    return {
        "status_code": response.status_code,
        "headers": {
            key: value
            for key, value in response.headers.items()
            if key in {"content-type", "x-raes-snapshot-revision", "retry-after"}
        },
        "body": output,
    }


@contextmanager
def recording_context(seed: str) -> Iterator[None]:
    class RecordingDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = fixed_clock()
            return instant.replace(tzinfo=None) if tz is None else instant.astimezone(tz)

    with (
        deterministic_ids(seed),
        patch("raes_contracts.timestamps.datetime", RecordingDateTime),
        patch("raes.module_registry.urlopen", side_effect=URLError("offline parity fixture")),
    ):
        yield


def schema_source_cases(repo: Path) -> Iterator[Case]:
    """Reuse the governed artifact router, including non-fixture publications."""
    from tools.check_json_artifacts import collect_validation_targets

    entries = {
        json.loads(path.read_text(encoding="utf-8"))["schema_path"]: path.stem
        for path in sorted((repo / "contracts/schema-publication/entries").glob("*.json"))
    }
    for target in collect_validation_targets(repo):
        if target.schema_path in entries and target.mode == "schema":
            contract = entries[target.schema_path]
            source = repo / target.path
            yield Case(
                "schema",
                "validate",
                contract + "/routed/" + target.path,
                (contract,),
                {"payload.json": source.read_bytes()},
            )
    for schema_path, contract in sorted(entries.items()):
        for label, payload in (("empty-object", b"{}"), ("malformed-json", b"{")):
            yield Case("schema", "validate", contract + "/" + label, (contract,), {"payload.json": payload})
        if contract == "sdl-authoring-input-v1":
            yield Case(
                "schema",
                "validate",
                contract + "/minimal-authoring-object",
                (contract,),
                {"payload.json": encode({"name": "parity"})},
            )
        if contract == "raes-semantic-invariants-v1":
            schema = json.loads((repo / schema_path).read_text(encoding="utf-8"))
            payload = {
                name: definition["const"] for name, definition in schema["properties"].items() if "const" in definition
            }
            payload["invariants"] = []
            yield Case("schema", "validate", contract + "/profile", (contract,), {"payload.json": encode(payload)})


def complete_inventory(repo: Path, cases: list[Case], regressions: dict[str, object]) -> dict[str, object]:
    """Compare the declared registries and input inventory with actual cases."""
    registry = cli_registry()
    leaves = {
        command for command in registry if command and not any(other.startswith(command + " ") for other in registry)
    }
    expected = {
        "cli": leaves,
        "canonical": {"encode"},
        "randstream": {"vector"},
        "primitive": {"ingress", "ingress-exception", "uri", "pointer", "tokens", "address", "render", "plan-root"},
        "mcp": set(mcp_registry()),
        "http": set(http_registry(http_schema())),
        "schema": {path.stem for path in (repo / "contracts/schema-publication/entries").glob("*.json")},
    }
    observed = {surface: set() for surface in expected}
    covered_inputs = {digest(content) for case in cases for content in case.files.values()}
    for case in cases:
        if case.surface in observed:
            observed[case.surface].add(case.args[0] if case.surface == "schema" else case.command)
    inputs = [path.relative_to(repo).as_posix() for path in data_inputs(repo)]
    missing_inputs = [name for name in inputs if digest((repo / name).read_bytes()) not in covered_inputs]
    missing = {surface: sorted(keys - observed[surface]) for surface, keys in expected.items()}
    return {
        "surfaces": {surface: sorted(keys) for surface, keys in expected.items()},
        "inputs": inputs,
        "input_digests": {name: "sha256:" + digest((repo / name).read_bytes()) for name in inputs},
        "regressions": regressions,
        "missing_surfaces": missing,
        "missing_inputs": missing_inputs,
        "complete": not any(missing.values()) and not missing_inputs and bool(regressions.get("complete")),
    }


def local_dependencies(source: Path, content: bytes) -> list[Path]:
    """Discover explicit local source dependencies without parsing or executing SDL."""
    text = content.decode("utf-8", errors="replace")
    paths = [
        Path(os.path.abspath(source.parent / reference))
        for reference in re.findall(r"source:\s*['\"]?local:([^\s'\"]+)", text)
    ]
    paths.extend(source.parent / name for name in (LOCKFILE_NAME, TRUST_POLICY_NAME))
    return paths


def http_trace_cases() -> Iterator[Case]:
    base = "/participants/participant.parity"
    requests = [
        {
            "method": "POST",
            "path": base + "/episodes/initialize",
            "principal": "operator",
            "json": {"episode_id": "parity-episode"},
        },
        {"method": "GET", "path": base + "/status", "principal": "operator"},
        {"method": "GET", "path": base + "/episodes/parity-episode/history", "principal": "operator"},
        {"method": "GET", "path": base + "/context", "principal": "operator"},
        {
            "method": "POST",
            "path": base + "/episodes/reset",
            "principal": "operator",
            "json": {"reason": "parity reset"},
        },
        {
            "method": "POST",
            "path": base + "/episodes/terminate",
            "principal": "operator",
            "json": {"terminal_reason": "completed"},
        },
        {"method": "POST", "path": base + "/episodes/restart", "principal": "operator", "json": {}},
        {"method": "GET", "path": "/snapshot", "principal": "operator"},
    ]
    yield Case("http-trace", "participant episodes", "reference", (), {"request.json": encode({"requests": requests})})
    for domain, payload in {
        "provisioning": {"operations": [], "diagnostics": [], "realization_authority": []},
        "orchestration": {"operations": [], "startup_order": [], "diagnostics": []},
        "evaluation": {"operations": [], "startup_order": [], "diagnostics": []},
    }.items():
        requests = [
            {
                "method": "POST",
                "path": "/operations/" + domain,
                "principal": "operator",
                "json": payload,
                "save": {"operation_id": "/body/operation_id"},
            },
            {"method": "GET", "path": "/operations/${operation_id}", "principal": "operator"},
            {"method": "GET", "path": "/snapshot", "principal": "operator"},
        ]
        yield Case(
            "http-trace", "operation " + domain, "reference", (), {"request.json": encode({"requests": requests})}
        )


def data_inputs(repo: Path) -> list[Path]:
    """Discover input data without following repository-controlled links."""
    result = []
    for root in (repo / "examples", repo / "contracts/fixtures"):
        if root.is_symlink() or root.parent.is_symlink():
            raise ValueError("a parity data root must not be a symbolic link")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("parity data discovery refuses symbolic links")
            if path.suffix in {".json", ".yaml", ".yml"} and path.is_file():
                result.append(path)
    return result
