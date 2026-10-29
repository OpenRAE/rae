"""MCP tools report unexpected failures without exception values (issue #1678)."""

import asyncio
import logging

import pytest
import raes_mcp.tools.authoring.tools as authoring_tools
from mcp.server.fastmcp.exceptions import ToolError
from raes_mcp.server import create_server

SENTINEL = "sentinel-9d2b-value"


def test_unexpected_tool_failure_returns_a_fixed_error_and_a_value_free_record(monkeypatch, caplog):
    def _fail(*_args, **_kwargs):
        raise RuntimeError(f"defect with {SENTINEL}")

    monkeypatch.setattr(authoring_tools, "_run_sdl_validate", _fail)
    server = create_server()

    with caplog.at_level(logging.ERROR), pytest.raises(ToolError) as raised:
        asyncio.run(server.call_tool("sdl_validate", {"sdl_content": "name: probe\n"}))

    assert SENTINEL not in str(raised.value)
    assert "internal error" in str(raised.value)
    records = [record for record in caplog.records if record.name.startswith("raes_mcp")]
    assert len(records) == 1
    assert SENTINEL not in records[0].getMessage()
    assert SENTINEL not in (records[0].exc_text or "")
    assert "RuntimeError" in (records[0].exc_text or "")


def test_tool_boundary_keeps_the_tool_schema():
    server = create_server()

    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    assert set(tools["sdl_validate"].inputSchema["properties"]) == {
        "sdl_content",
        "structural_only",
        "accept_migration_syntax",
    }
    assert tools["sdl_validate"].inputSchema["required"] == ["sdl_content"]
