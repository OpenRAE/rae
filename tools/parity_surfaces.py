"""Public CLI, MCP and HTTP adapters for the golden parity corpus (#1778)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import datetime, tzinfo
from functools import lru_cache
from itertools import chain
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlsplit

import click
import httpx
import yaml
from mcp.server.fastmcp import FastMCP
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
    ARGUMENTS_FILE,
    PAYLOAD_FILE,
    REQUEST_FILE,
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
HTTP_LIMITS = ("max_request_bytes", "max_pending_mutations", "max_pending_rejection_audits")

REPO_PREFIX = "repo/"
FIXTURES_ROOT = "contracts/fixtures"
JSON_FILES = "*.json"
STORE_FILE = "store.sqlite3"
BACKUP_FILE = "backup.sqlite3"
RUN_SCOPE = "run:parity"


def cli_parameter(parameter: click.Parameter) -> dict[str, Any]:
    info = parameter.to_info_dict()
    for key in ("help", "prompt"):
        info.pop(key, None)
    if isinstance(info.get("default"), Path):
        info["default"] = str(info["default"])
    return info


def visit_cli(command: click.Command, prefix: str, commands: dict[str, object]) -> None:
    context = click.Context(command)
    commands[prefix] = [cli_parameter(parameter) for parameter in command.params]
    if isinstance(command, click.Group):
        for name in command.list_commands(context):
            child = command.get_command(context, name)
            if child is None:
                raise ValueError(f"registered CLI command {name} is unavailable")
            visit_cli(child, (prefix + " " + name).strip(), commands)


@lru_cache(maxsize=1)
def cli_registry() -> dict[str, object]:
    """Read command and flag names from the actual Click/Typer registry."""
    commands: dict[str, object] = {}
    visit_cli(get_command(app), "", commands)
    return commands


@lru_cache(maxsize=1)
def mcp_server() -> FastMCP:
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
        **{
            name: authority["limits"][name] for name in HTTP_LIMITS if authority and name in authority.get("limits", {})
        },
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


def source_imports(repo: Path, path: Path, content: bytes) -> Iterator[Path]:
    text = content.decode("utf-8", errors="replace")
    for reference in re.findall(r"source:\s*['\"]?local:([^\s'\"]+)", text):
        dependency = (path.parent / reference).resolve()
        if not dependency.is_relative_to(repo):
            raise ValueError("a parity source import escapes the repository")
        if dependency.exists():
            yield dependency


def source_policies(repo: Path, path: Path) -> Iterator[tuple[str, bytes]]:
    for name in (LOCKFILE_NAME, TRUST_POLICY_NAME):
        candidate = path.parent / name
        if candidate.is_file():
            relative = candidate.relative_to(repo).as_posix()
            if not is_regular_repo_file(repo, relative):
                raise ValueError("a parity source dependency is not a regular file")
            yield REPO_PREFIX + relative, candidate.read_bytes()


def source_files(repo: Path, source: Path) -> dict[str, bytes]:
    """Copy only the source and its local imports, preserving relative paths."""
    files: dict[str, bytes] = {}
    pending = [source]
    while pending:
        path = pending.pop()
        relative = path.relative_to(repo).as_posix()
        name = REPO_PREFIX + relative
        if name in files:
            continue
        if not is_regular_repo_file(repo, relative):
            raise ValueError(f"parity input is not a regular repository file: {relative}")
        files[name] = path.read_bytes()
        pending.extend(source_imports(repo, path, files[name]))
        files.update(source_policies(repo, path))
    return files


def source_cli_cases(repo: Path, sources: list[Path]) -> Iterator[Case]:
    for source in sources:
        name = source.relative_to(repo).as_posix()
        input_name = REPO_PREFIX + name
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


def reference_cli_cases(repo: Path) -> Iterator[Case]:
    for command, arguments in (
        ("processor manifest", ("processor", "manifest")),
        ("conformance backend", ("conformance", "backend", "--format", "json")),
        ("conformance processor", ("conformance", "processor", "--format", "json")),
    ):
        if command == "conformance backend":
            roots = (repo / FIXTURES_ROOT, repo / "contracts/profiles/backend")
            files = {
                REPO_PREFIX + path.relative_to(repo).as_posix(): path.read_bytes()
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


def exploit_cli_cases(repo: Path) -> Iterator[Case]:
    exploit_fixtures = {
        fixture
        for directory in (repo / FIXTURES_ROOT).rglob("*exploit*")
        if directory.is_dir()
        for fixture in directory.rglob(JSON_FILES)
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


def store_cli_cases() -> Iterator[Case]:
    for operation in ("check", "backup", "restore"):
        paths = (STORE_FILE, BACKUP_FILE) if operation != "check" else (STORE_FILE,)
        arguments = ("runtime", "store", operation, *paths, "--target", "stub", "--run-scope", RUN_SCOPE)
        yield Case("cli", "runtime store " + operation, "missing-store", arguments, {})
        setup = {"store": STORE_FILE, "commands": []}
        if operation == "restore":
            setup["commands"] = [
                [
                    "runtime",
                    "store",
                    "backup",
                    STORE_FILE,
                    BACKUP_FILE,
                    "--target",
                    "stub",
                    "--run-scope",
                    RUN_SCOPE,
                ]
            ]
            arguments = (
                "runtime",
                "store",
                "restore",
                BACKUP_FILE,
                "restored.sqlite3",
                "--target",
                "stub",
                "--run-scope",
                RUN_SCOPE,
            )
        yield Case("cli", "runtime store " + operation, "admitted-store", arguments, {"setup.json": encode(setup)})


def extended_cli_cases(repo: Path, sources: list[Path]) -> Iterator[Case]:
    return chain(source_cli_cases(repo, sources), reference_cli_cases(repo), exploit_cli_cases(repo), store_cli_cases())


def mcp_parameters(name: str, specification: dict[str, Any]) -> dict[str, Any]:
    presets = {
        "sdl_section_reference": {"section": "nodes"},
        "sdl_get_example": {"name": "hospital-ransomware-surgery-day"},
        "experiment_get_example": {"name": "smoke"},
        "sdl_validate_section": {"section": "nodes", "section_yaml": "web: {type: compute}"},
        "sdl_get_element": {"element_name": "nodes.web"},
        "sdl_references": {"symbol": "web"},
        "sdl_apply_edit": {"operation": "set", "pointer": "/name", "value_json": '"changed"'},
    }
    parameters = dict(presets.get(name, {}))
    properties = specification["inputSchema"].get("properties", {})
    if "sdl_content" in properties:
        parameters["sdl_content"] = "name: parity\nnodes:\n  web: {type: compute}\n"
    if "spec_content" in properties:
        parameters["spec_content"] = "spec_id: parity\n"
    for required in specification["inputSchema"].get("required", []):
        parameters.setdefault(required, "")
    return parameters


def mcp_sdl_cases(
    repo: Path, sources: list[Path], name: str, properties: dict[str, Any], parameters: dict[str, Any]
) -> Iterator[Case]:
    if "sdl_content" in properties:
        for source in sources:
            invocation = {**parameters, "sdl_content": source.read_text(encoding="utf-8")}
            yield Case("mcp", name, source.relative_to(repo).as_posix(), (), {ARGUMENTS_FILE: encode(invocation)})


def mcp_experiment_cases(repo: Path, name: str) -> Iterator[Case]:
    if name == "experiment_validate":
        for source in sorted((repo / "examples/experiments").glob("*.yaml")):
            yield Case(
                "mcp",
                name,
                source.relative_to(repo).as_posix(),
                (),
                {ARGUMENTS_FILE: encode({"spec_content": source.read_text(encoding="utf-8")})},
            )


def mcp_cases(repo: Path, sources: list[Path], registry: dict[str, object]) -> Iterator[Case]:
    for name, specification in sorted(registry.items()):
        parameters = mcp_parameters(name, specification)
        properties = specification["inputSchema"].get("properties", {})
        base = (
            Case("mcp", name, "reference", (), {ARGUMENTS_FILE: encode(parameters)}),
            Case("mcp", name, "invalid-arguments", (), {ARGUMENTS_FILE: encode({key: [] for key in properties})}),
        )
        yield from chain(
            base, mcp_sdl_cases(repo, sources, name, properties, parameters), mcp_experiment_cases(repo, name)
        )


def http_cases(schema: dict[str, object]) -> Iterator[Case]:
    for key in http_registry(schema):
        method, path = key.split(" ", 1)
        path = re.sub(r"\{[^}]+\}", "missing", path)
        for principal in ("anonymous", "operator", "auditor"):
            request = {"method": method, "path": path, "principal": principal}
            if method not in {"GET", "HEAD"}:
                request["json"] = {}
            yield Case("http", key, principal + "/empty-reference-state", (), {REQUEST_FILE: encode(request)})
    for domain, payload in {
        "provisioning": {"operations": [], "diagnostics": [], "realization_authority": []},
        "orchestration": {"operations": [], "startup_order": [], "diagnostics": []},
        "evaluation": {"operations": [], "startup_order": [], "diagnostics": []},
    }.items():
        request = {"method": "POST", "path": "/operations/" + domain, "principal": "operator", "json": payload}
        yield Case("http", "POST /operations/" + domain, "empty-plan", (), {REQUEST_FILE: encode(request)})


def run_mcp(case: Case) -> dict[str, object]:
    try:
        result = asyncio.run(mcp_server().call_tool(case.command, json.loads(case.files[ARGUMENTS_FILE])))
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


def bound_request(original: dict[str, Any], bindings: dict[str, str]) -> dict[str, Any]:
    step = dict(original)
    for key, value in step.items():
        if isinstance(value, str):
            for name, replacement in bindings.items():
                value = value.replace("${" + name + "}", replacement)
            step[key] = value
    return step


def response_bindings(original: dict[str, Any], response: dict[str, Any]) -> dict[str, str]:
    bindings = {}
    for name, pointer in original.get("save", {}).items():
        value = response
        for component in pointer.strip("/").split("/"):
            value = value[component]
        if not isinstance(value, str):
            raise ValueError("an HTTP trace binding must be a string")
        bindings[name] = value
    return bindings


def run_http(case: Case) -> dict[str, object]:
    request = json.loads(case.files[REQUEST_FILE])
    with http_client(request) as client:
        if "requests" not in request:
            return send_http(client, request, case.files)
        bindings: dict[str, str] = {}
        responses = []
        for original in request["requests"]:
            response = send_http(client, bound_request(original, bindings), case.files)
            responses.append(response)
            bindings.update(response_bindings(original, response))
        return {"responses": responses}


def request_headers(request: dict[str, Any]) -> dict[str, str]:
    principal = request.get("principal", "anonymous")
    headers = dict(request.get("headers", {}))
    if principal != "anonymous":
        headers["x-raes-client-identity"] = principal
        if request.get("verified", True):
            headers["x-raes-client-verified"] = "true"
    if principal == "invalid":
        headers["authorization"] = "Bearer public-parity-invalid"
    return headers


def validated_chunks(request: dict[str, Any], body: bytes) -> list[int]:
    sizes = request["chunk_sizes"]
    if any(type(size) is not int or size < 0 for size in sizes) or sum(sizes) != len(body):
        raise ValueError("invalid recorded HTTP chunk sizes")
    return sizes


def streamed_http(client: TestClient, request: dict[str, Any], headers: dict[str, str], body: bytes) -> httpx.Response:
    sizes = validated_chunks(request, body)

    async def chunks() -> AsyncIterator[bytes]:
        offset = 0
        for size in sizes:
            yield body[offset : offset + size]
            offset += size
        if not request.get("stream_complete", True):
            raise RuntimeError("recorded HTTP stream did not complete")

    async def response() -> httpx.Response:
        transport = httpx.ASGITransport(app=client.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as streamed_client:
            return await streamed_client.request(request["method"], request["path"], headers=headers, content=chunks())

    return client.portal.call(response)


def response_body(text: str) -> object:
    output = json_output(text)
    if isinstance(output, dict) and isinstance(output.get("detail"), str):
        output.pop("detail")
    elif isinstance(output, dict) and isinstance(output.get("detail"), list):
        for detail in output["detail"]:
            if isinstance(detail, dict):
                detail.pop("msg", None)
                detail.pop("ctx", None)
    return output


def recorded_response(response: httpx.Response | None) -> dict[str, object]:
    if response is None:
        return {"status_code": None, "headers": {}, "body": None}
    return {
        "status_code": response.status_code,
        "headers": {
            key: value
            for key, value in response.headers.items()
            if key in {"content-type", "x-raes-snapshot-revision", "retry-after"}
        },
        "body": response_body(response.text),
    }


def send_http(client: TestClient, request: dict[str, Any], files: dict[str, bytes]) -> dict[str, object]:
    headers = request_headers(request)
    payload = {key: request[key] for key in ("json", "content") if key in request}
    if "body_file" in request:
        payload["content"] = files[request["body_file"]]
    if "asgi_more_body" in request:
        response = send_asgi(client, request, headers, payload["content"])
    elif request.get("streamed") or len(request.get("chunk_sizes", [])) > 1:
        response = streamed_http(client, request, headers, payload["content"])
    else:
        response = client.request(request["method"], request["path"], headers=headers, **payload)
    return recorded_response(response)


async def asgi_frames(request: dict[str, Any], body: bytes, sizes: list[int]) -> AsyncIterator[dict[str, Any]]:
    offset = 0
    for size, more in zip(sizes, request["asgi_more_body"], strict=True):
        yield {"type": "http.request", "body": body[offset : offset + size], "more_body": more}
        offset += size
    if not (request.get("stream_disconnected") or request.get("stream_complete")):
        raise ValueError("the application requested an unrecorded ASGI frame")
    while True:
        yield {"type": "http.disconnect"}


def send_asgi(
    client: TestClient, request: dict[str, Any], headers: dict[str, str], body: bytes
) -> httpx.Response | None:
    """Replay the consumed raw ASGI frames, including an observed disconnect."""
    sizes = validated_chunks(request, body)
    if len(sizes) != len(request["asgi_more_body"]):
        raise ValueError("invalid recorded ASGI frames")
    url = urlsplit(request["path"])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": request["method"],
        "scheme": "http",
        "path": url.path,
        "raw_path": url.path.encode(),
        "query_string": url.query.encode("ascii"),
        "root_path": "",
        "headers": [(key.encode("ascii"), value.encode("latin-1")) for key, value in headers.items()],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    messages: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    received = asgi_frames(request, body, sizes)
    try:
        client.portal.call(client.app, scope, received.__anext__, messages.put)
    finally:
        client.portal.call(received.aclose)
    sent = []
    while not messages.empty():
        sent.append(messages.get_nowait())
    start = next((message for message in sent if message["type"] == "http.response.start"), None)
    if start is None:
        return None
    content = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return httpx.Response(start["status"], headers=start.get("headers", []), content=content)


@contextmanager
def recording_context(seed: str) -> Iterator[None]:
    class RecordingDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
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
        for path in sorted((repo / "contracts/schema-publication/entries").glob(JSON_FILES))
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
                {PAYLOAD_FILE: source.read_bytes()},
            )
    for schema_path, contract in sorted(entries.items()):
        for label, payload in (("empty-object", b"{}"), ("malformed-json", b"{")):
            yield Case("schema", "validate", contract + "/" + label, (contract,), {PAYLOAD_FILE: payload})
        yield from minimal_schema_cases(repo, schema_path, contract)


def minimal_schema_cases(repo: Path, schema_path: str, contract: str) -> Iterator[Case]:
    if contract == "sdl-authoring-input-v1":
        yield Case(
            "schema",
            "validate",
            contract + "/minimal-authoring-object",
            (contract,),
            {PAYLOAD_FILE: encode({"name": "parity"})},
        )
    if contract == "raes-semantic-invariants-v1":
        schema = json.loads((repo / schema_path).read_text(encoding="utf-8"))
        payload = {
            name: definition["const"] for name, definition in schema["properties"].items() if "const" in definition
        }
        payload["invariants"] = []
        yield Case("schema", "validate", contract + "/profile", (contract,), {PAYLOAD_FILE: encode(payload)})


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
        "schema": {path.stem for path in (repo / "contracts/schema-publication/entries").glob(JSON_FILES)},
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
    yield Case("http-trace", "participant episodes", "reference", (), {REQUEST_FILE: encode({"requests": requests})})
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
        yield Case("http-trace", "operation " + domain, "reference", (), {REQUEST_FILE: encode({"requests": requests})})


def data_inputs(repo: Path) -> list[Path]:
    """Discover input data without following repository-controlled links."""
    result = []
    for root in (repo / "examples", repo / FIXTURES_ROOT):
        if root.is_symlink() or root.parent.is_symlink():
            raise ValueError("a parity data root must not be a symbolic link")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("parity data discovery refuses symbolic links")
            if path.suffix in {".json", ".yaml", ".yml"} and path.is_file():
                result.append(path)
    return result
