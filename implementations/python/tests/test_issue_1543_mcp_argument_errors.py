"""Issue #1543: MCP argument validation errors must not echo rejected values.

Every case drives the real JSON-RPC path through an in-memory MCP client
session, so the lowlevel handler that turns a tool failure into an
``isError`` result is included.
"""

from __future__ import annotations

import asyncio
from typing import Any

import anyio
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import BaseModel
from raes_mcp.server import create_server

_SENTINEL = "do-not-disclose-42"
_SECRET_OBJECT = {"secret": _SENTINEL}
_LEAK_MARKERS = (_SENTINEL, "secret", "input_value", "input_type")

_TOOL_SCHEMAS = {tool.name: tool.inputSchema for tool in asyncio.run(create_server().list_tools())}
_TOOLS_WITH_ARGUMENTS = sorted(name for name, schema in _TOOL_SCHEMAS.items() if schema.get("properties"))


def _call(tool: str, arguments: dict[str, Any], server: FastMCP | None = None) -> tuple[bool, str]:
    async def _run() -> tuple[bool, str]:
        async with create_connected_server_and_client_session(server or create_server()) as client:
            result = await client.call_tool(tool, arguments)
        return bool(result.isError), "\n".join(getattr(block, "text", "") for block in result.content)

    return anyio.run(_run)


def _assert_no_leak(text: str) -> None:
    for marker in _LEAK_MARKERS:
        assert marker not in text


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        pytest.param(
            "sdl_validate",
            {"sdl_content": _SECRET_OBJECT},
            "sdl_content: expected string (string_type)",
            id="sdl-object-argument",
        ),
        pytest.param(
            "experiment_validate",
            {"spec_content": _SECRET_OBJECT},
            "spec_content: expected string (string_type)",
            id="experiment-object-argument",
        ),
        pytest.param(
            "sdl_validate",
            {"unexpected": _SENTINEL},
            "sdl_content: expected string (missing)",
            id="missing-argument-with-extra-key",
        ),
    ],
)
def test_rejected_argument_names_field_and_type_without_value(
    tool: str, arguments: dict[str, Any], expected: str
) -> None:
    is_error, text = _call(tool, arguments)

    assert is_error is True
    assert text == f"Invalid arguments for tool {tool}: {expected}"
    _assert_no_leak(text)


@pytest.mark.parametrize("tool", _TOOLS_WITH_ARGUMENTS)
def test_every_registered_tool_hides_rejected_argument_values(tool: str) -> None:
    properties = _TOOL_SCHEMAS[tool]["properties"]

    is_error, text = _call(tool, dict.fromkeys(properties, _SECRET_OBJECT))

    assert is_error is True
    assert text.startswith(f"Invalid arguments for tool {tool}: ")
    for field, schema in properties.items():
        assert f"{field}: expected {schema['type']} (" in text
    _assert_no_leak(text)


class _ProbeSettings(BaseModel):
    level: int


def _probe(note: str | None, count: int | list[int], settings: _ProbeSettings) -> str:
    return f"{note}{count}{settings.level}"


def test_tool_added_later_reports_union_and_model_arguments_without_values() -> None:
    server = create_server()
    server.add_tool(_probe)

    is_error, text = _call("_probe", {"note": _SECRET_OBJECT, "count": _SECRET_OBJECT, "settings": _SENTINEL}, server)

    assert is_error is True
    assert text == (
        "Invalid arguments for tool _probe: note: expected string or null (string_type); "
        "count: expected integer or array (int_type, list_type); "
        "settings: expected a value matching the tool input schema (model_type)"
    )
    _assert_no_leak(text)


@pytest.mark.parametrize(
    ("tool", "arguments", "is_error_expected", "expected_text"),
    [
        pytest.param("sdl_validate", {"sdl_content": "name: demo\n"}, False, "", id="valid-call"),
        pytest.param("no_such_tool", {}, True, "Unknown tool: no_such_tool", id="unknown-tool"),
    ],
)
def test_non_argument_outcomes_are_unchanged(
    tool: str, arguments: dict[str, Any], is_error_expected: bool, expected_text: str
) -> None:
    is_error, text = _call(tool, arguments)

    assert is_error is is_error_expected
    assert expected_text in text
