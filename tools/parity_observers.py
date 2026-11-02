"""Typed CI observers that preserve calls at each public parity boundary."""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from tools.parity_support import ARGUMENTS_FILE, PAYLOAD_FILE, REQUEST_FILE, Case, encode

if TYPE_CHECKING:
    import typer
    from click.testing import Result
    from fastapi import FastAPI
    from httpx import AsyncByteStream, AsyncClient, Client, Request, Response, SyncByteStream
    from jsonschema import Draft202012Validator, ValidationError
    from mcp import types as mcp_types
    from mcp.server.fastmcp import FastMCP
    from pydantic import BaseModel
    from raes.materialization import MaterializedScenario
    from raes.scenario import ExpandedScenario, Scenario
    from raes_runtime.control_plane_security import ControlPlaneIdentity
    from starlette.types import Message, Receive, Scope, Send
    from typer.testing import CliRunner

    from tools.parity_inputs import InputCollector


@dataclass
class PublishedModels:
    collector: InputCollector
    published: set[str]
    schema_ids: dict[str, str]

    def contract(self, model: type[BaseModel]) -> str | None:
        if not model.__module__.startswith("raes_contracts"):
            return None
        version = model.model_fields.get("schema_version")
        if version is None:
            return None
        versions = (version.default, *get_args(version.annotation))
        candidates = {value.replace("/", "-") for value in versions if isinstance(value, str)} & self.published
        return next(iter(candidates)) if len(candidates) == 1 else None

    def record(self, contract: str | None, value: object) -> None:
        if contract is not None:
            try:
                content = encode(value)
            except TypeError, ValueError, RecursionError:
                self.collector.non_protocol_tests.add(self.collector.nodeid)
            else:
                self.collector.add(Case("schema", "validate", "", (contract,), {PAYLOAD_FILE: content}))

    def record_json(self, model: type[BaseModel], value: object) -> None:
        contract = self.contract(model)
        if contract is not None and isinstance(value, (str, bytes, bytearray)):
            try:
                content = value.encode() if isinstance(value, str) else bytes(value)
            except UnicodeError:
                self.collector.non_protocol_tests.add(self.collector.nodeid)
            else:
                self.collector.add(Case("schema", "validate", "", (contract,), {PAYLOAD_FILE: content}))

    def record_schema(
        self, validator: Draft202012Validator, value: object, args: tuple[object, ...], kwargs: dict[str, object]
    ) -> None:
        schema = args[0] if args else kwargs.get("_schema", validator.schema)
        schema_id = schema.get("$id") if isinstance(schema, dict) else None
        contract = self.schema_ids.get(schema_id) if isinstance(schema_id, str) else None
        self.record(contract, value)


def published_models(collector: InputCollector) -> PublishedModels:
    schema_ids = {}
    entries = sorted((collector.repo / "contracts/schema-publication/entries").glob("*.json"))
    for entry in entries:
        publication = json.loads(entry.read_bytes())
        schema = json.loads((collector.repo / publication["schema_path"]).read_bytes())
        if "$id" in schema:
            schema_ids[schema["$id"]] = entry.stem
    return PublishedModels(collector, {path.stem for path in entries}, schema_ids)


def install_models(collector: InputCollector, models: PublishedModels) -> None:
    from pydantic import BaseModel

    original_initialize = BaseModel.__init__
    original_validate = BaseModel.model_validate.__func__
    original_validate_json = BaseModel.model_validate_json.__func__

    @functools.wraps(original_initialize)
    def initialize(instance: BaseModel, /, **values: object) -> None:
        models.record(models.contract(type(instance)), values)
        original_initialize(instance, **values)

    @functools.wraps(original_validate)
    def validate(model: type[BaseModel], value: object, *args: object, **kwargs: object) -> BaseModel:
        models.record(models.contract(model), value)
        return original_validate(model, value, *args, **kwargs)

    @functools.wraps(original_validate_json)
    def validate_json(model: type[BaseModel], value: object, *args: object, **kwargs: object) -> BaseModel:
        models.record_json(model, value)
        return original_validate_json(model, value, *args, **kwargs)

    collector.patches.setattr(BaseModel, "__init__", initialize)
    collector.patches.setattr(BaseModel, "model_validate", classmethod(validate))
    collector.patches.setattr(BaseModel, "model_validate_json", classmethod(validate_json))


def install_schema_validation(collector: InputCollector, models: PublishedModels) -> None:
    from jsonschema import Draft202012Validator

    original = Draft202012Validator.iter_errors

    @functools.wraps(original)
    def iter_errors(
        validator: Draft202012Validator, value: object, *args: object, **kwargs: object
    ) -> Iterator[ValidationError]:
        models.record_schema(validator, value, args, kwargs)
        return original(validator, value, *args, **kwargs)

    collector.patches.setattr(Draft202012Validator, "iter_errors", iter_errors)


def analysis_probe[ResultT](
    collector: InputCollector, original: Callable[..., ResultT], command: str
) -> Callable[..., ResultT]:
    @functools.wraps(original)
    def invoke(path: Path, *args: object, **kwargs: object) -> ResultT:
        arguments = ["processor", command, str(path)]
        if "profile" in kwargs:
            arguments.extend(["--profile", kwargs["profile"]])
        collector.cli(arguments, {})
        return original(path, *args, **kwargs)

    return invoke


def install_parsing(collector: InputCollector) -> None:
    from raes import parser
    from raes_processor.exploit_path import analyze_exploit_path_file
    from raes_processor.satisfiability import analyze_scenario_file

    original = parser.parse_sdl

    @functools.wraps(original)
    def parse(content: str, *args: object, **kwargs: object) -> Scenario | ExpandedScenario | MaterializedScenario:
        if isinstance(content, str):
            collector.source(content, **kwargs)
        return original(content, *args, **kwargs)

    collector.patch_aliases(original, parse)
    collector.patch_aliases(analyze_scenario_file, analysis_probe(collector, analyze_scenario_file, "satisfiability"))
    collector.patch_aliases(
        analyze_exploit_path_file, analysis_probe(collector, analyze_exploit_path_file, "exploit-path")
    )


def installed_cli(arguments: object, shell: object) -> bool:
    if not isinstance(arguments, (list, tuple)) or not arguments:
        return False
    return Path(os.fsdecode(arguments[0])).name in {"raes", "raes.exe"} and not shell


def install_cli(collector: InputCollector) -> None:
    import raes_cli.entrypoint as entrypoint
    from raes_cli.main import app
    from typer.testing import CliRunner

    original_cli = CliRunner.invoke
    original_entrypoint = entrypoint.main
    original_run = subprocess.run

    @functools.wraps(original_cli)
    def invoke(
        runner: CliRunner, application: typer.Typer, args: str | Sequence[str] | None = None, **kwargs: object
    ) -> Result:
        if application is app:
            collector.cli(args, kwargs)
        return original_cli(runner, application, args, **kwargs)

    @functools.wraps(original_entrypoint)
    def main(*args: object, **kwargs: object) -> None:
        collector.cli(sys.argv[1:], {})
        return original_entrypoint(*args, **kwargs)

    @functools.wraps(original_run)
    def process_run(
        *popenargs: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        arguments = popenargs[0] if popenargs else kwargs.get("args")
        if installed_cli(arguments, kwargs.get("shell")):
            collector.cli(arguments[1:], kwargs, working_directory=kwargs.get("cwd"))
        return original_run(*popenargs, **kwargs)

    collector.patches.setattr(CliRunner, "invoke", invoke)
    collector.patches.setattr(entrypoint, "main", main)
    collector.aliases_to_restore.append((main, original_entrypoint))
    collector.patches.setattr(subprocess, "run", process_run)


def install_mcp(collector: InputCollector, declared: set[str]) -> None:
    from mcp.server.fastmcp import FastMCP

    original = FastMCP.call_tool

    @functools.wraps(original)
    async def call_tool(
        server: FastMCP, name: str, arguments: dict[str, object]
    ) -> Sequence[mcp_types.ContentBlock] | dict[str, object]:
        if name in declared:
            try:
                content = encode(arguments)
            except TypeError, ValueError, RecursionError:
                collector.non_protocol_tests.add(collector.nodeid)
            else:
                collector.add(Case("mcp", name, "", (), {ARGUMENTS_FILE: content}))
        return await original(server, name, arguments)

    collector.patches.setattr(FastMCP, "call_tool", call_tool)


def identity_fields(
    served: FastAPI, identity: ControlPlaneIdentity, authorization: str, headers: Mapping[str, str]
) -> dict[str, object]:
    policy = served.state.control_plane_api_auth._security
    return {
        "principal": "recorded",
        "identity": identity.identity,
        "roles": sorted(role.value for role in identity.roles),
        "target_bound": identity.target_name is not None
        and "target:" + identity.target_name == served.state.control_plane_api_auth._control_plane._target_scope,
        "verified": authorization.lower().startswith("bearer ")
        or not policy.require_verified_identity
        or headers.get(policy.verified_header, "").lower() == "true",
    }


def authority_fields(served: FastAPI, headers: Mapping[str, str]) -> dict[str, object]:
    policy = served.state.control_plane_api_auth._security
    authorization = headers.get("authorization", "")
    identity = None
    principal = "anonymous"
    if authorization.lower().startswith("bearer "):
        identity = policy.bearer_tokens.get(authorization.split(" ", 1)[1].strip())
        principal = "invalid" if identity is None else "operator"
    elif policy.trust_proxy_identity_headers:
        identity = policy.trusted_identities.get(headers.get(policy.identity_header, ""))
        if identity is not None:
            principal = "operator"
    return {"principal": principal} if identity is None else identity_fields(served, identity, authorization, headers)


def request_specification(served: FastAPI, method: str, path: str, headers: Mapping[str, str]) -> dict[str, object]:
    from tools.parity_surfaces import HTTP_LIMITS

    policy = served.state.control_plane_api_auth._security
    specification = {"method": method, "path": path, **authority_fields(served, headers)}
    specification["limits"] = {name: getattr(policy, name) for name in HTTP_LIMITS}
    for header in ("idempotency-key", "if-match", "content-type", "content-length", "transfer-encoding"):
        if header in headers:
            specification.setdefault("headers", {})[header] = headers[header]
    return specification


@dataclass
class CapturedBody:
    parts: list[bytes] = field(default_factory=list)
    complete: bool = False


def capture_http(
    collector: InputCollector, specification: dict[str, object], body: CapturedBody, routes: list[str]
) -> None:
    from tools.parity_surfaces import route_key

    files = {}
    if body.parts or specification.get("streamed"):
        files["body.bin"] = b"".join(body.parts)
        specification["body_file"] = "body.bin"
        specification["stream_complete"] = body.complete
        specification["chunk_sizes"] = [len(part) for part in body.parts]
    files[REQUEST_FILE] = encode(specification)
    key = route_key(specification["method"], specification["path"].split("?", 1)[0], routes)
    collector.add(Case("http", key, "", (), files))


def observed_stream(original: AsyncByteStream | SyncByteStream, body: CapturedBody) -> AsyncByteStream | SyncByteStream:
    from httpx import AsyncByteStream, SyncByteStream

    class ObservedAsyncStream(AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            async for chunk in original:
                body.parts.append(chunk)
                yield chunk
            body.complete = True

        async def aclose(self) -> None:
            await original.aclose()

    class ObservedStream(SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            for chunk in original:
                body.parts.append(chunk)
                yield chunk
            body.complete = True

        def close(self) -> None:
            original.close()

    return ObservedAsyncStream() if isinstance(original, AsyncByteStream) else ObservedStream()


def observe_http(
    collector: InputCollector, client: Client | AsyncClient, request: Request, routes: list[str]
) -> Callable[[], None] | None:
    from httpx import RequestNotRead

    served = getattr(client, "app", None) or getattr(getattr(client, "_transport", None), "app", None)
    if served is None or not hasattr(getattr(served, "state", None), "control_plane_api_auth"):
        return None
    query = request.url.query.decode("ascii")
    path = request.url.path + ("?" + query if query else "")
    specification = request_specification(served, request.method, path, request.headers)
    body = CapturedBody()
    try:
        content = request.content
    except RequestNotRead:
        specification["streamed"] = True
        request.stream = observed_stream(request.stream, body)
    else:
        body.parts.append(content)
        body.complete = True
    return functools.partial(capture_http, collector, specification, body, routes)


async def observe_asgi(
    collector: InputCollector,
    original: Callable[[FastAPI, Scope, Receive, Send], Awaitable[None]],
    application: FastAPI,
    scope: Scope,
    receive: Receive,
    send: Send,
    routes: list[str],
) -> None:
    from httpx import Headers

    query = scope.get("query_string", b"").decode("ascii")
    path = scope["path"] + ("?" + query if query else "")
    specification = request_specification(
        application, scope["method"], path, Headers(scope["headers"], encoding="latin-1")
    )
    specification.update({"streamed": True, "asgi_more_body": []})
    body = CapturedBody()

    async def observed_receive() -> Message:
        message = await receive()
        if message["type"] == "http.request":
            body.parts.append(message.get("body", b""))
            body.complete = not message.get("more_body", False)
            specification["asgi_more_body"].append(not body.complete)
        elif message["type"] == "http.disconnect":
            specification["stream_disconnected"] = True
        return message

    try:
        return await original(application, scope, observed_receive, send)
    finally:
        capture_http(collector, specification, body, routes)


def install_http(collector: InputCollector, routes: list[str]) -> None:
    from fastapi import FastAPI
    from httpx import AsyncClient, Client

    original_sync, original_async, original_asgi = Client.send, AsyncClient.send, FastAPI.__call__
    observed = ContextVar("parity_http_observed", default=False)

    @functools.wraps(original_sync)
    def send(client: Client, request: Request, **kwargs: object) -> Response:
        finish = observe_http(collector, client, request, routes)
        token = observed.set(finish is not None or observed.get())
        try:
            return original_sync(client, request, **kwargs)
        finally:
            observed.reset(token)
            if finish is not None:
                finish()

    @functools.wraps(original_async)
    async def async_send(client: AsyncClient, request: Request, **kwargs: object) -> Response:
        finish = observe_http(collector, client, request, routes)
        token = observed.set(finish is not None or observed.get())
        try:
            return await original_async(client, request, **kwargs)
        finally:
            observed.reset(token)
            if finish is not None:
                finish()

    @functools.wraps(original_asgi)
    async def asgi(application: FastAPI, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or observed.get() or not hasattr(application.state, "control_plane_api_auth"):
            return await original_asgi(application, scope, receive, send)
        return await observe_asgi(collector, original_asgi, application, scope, receive, send, routes)

    collector.patches.setattr(Client, "send", send)
    collector.patches.setattr(AsyncClient, "send", async_send)
    collector.patches.setattr(FastAPI, "__call__", asgi)
