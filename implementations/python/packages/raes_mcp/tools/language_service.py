"""MCP wrappers for SDL language-service operations."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from raes.language_service import (
    apply_structured_edit,
    language_completions,
    language_diagnostics,
    language_format,
    language_references,
)

from raes_mcp.tools.operation_support import json_response


def _invalid_edit_value(message: str) -> str:
    return json_response(
        {
            "status": "invalid",
            "stage": "edit",
            "diagnostics": [{"stage": "edit", "severity": "error", "code": "sdl.edit", "message": message}],
        }
    )


def register(mcp: FastMCP) -> None:
    """Register SDL language-service tools on the MCP server."""

    @mcp.tool(
        name="sdl_completions",
        description=(
            "Return structured completion candidates for an SDL document. "
            "Use `cursor_path` as a JSON-pointer-like location such as "
            "'/' for top-level keys or '/nodes/web/features' for feature "
            "reference completions. Optional `prefix` filters candidates."
        ),
    )
    def sdl_completions(
        sdl_content: str,
        cursor_path: str = "",
        prefix: str = "",
    ) -> str:
        return json_response(
            language_completions(
                sdl_content,
                cursor_path=cursor_path,
                prefix=prefix,
            )
        )

    @mcp.tool(
        name="sdl_references",
        description=(
            "Locate SDL symbol definitions and occurrences. Pass a bare symbol "
            "like 'web' or a qualified symbol like 'features.web-app'."
        ),
    )
    def sdl_references(
        sdl_content: str,
        symbol: str,
    ) -> str:
        return json_response(language_references(sdl_content, symbol))

    @mcp.tool(
        name="sdl_format",
        description=(
            "Migrate recognized legacy SDL field spellings and format the result "
            "as canonical sdl-yaml/v1. Returns source-ranged migration advisories "
            "and any diagnostics produced after formatting."
        ),
    )
    def sdl_format(sdl_content: str) -> str:
        return json_response(language_format(sdl_content))

    @mcp.tool(
        name="sdl_diagnostics",
        description=(
            "Return structured SDL parse, structural, and semantic diagnostics "
            "as JSON records with severity, code, stage, and message fields."
        ),
    )
    def sdl_diagnostics(
        sdl_content: str,
        semantic_validation: bool = True,
    ) -> str:
        return json_response(
            language_diagnostics(
                sdl_content,
                semantic_validation=semantic_validation,
            )
        )

    @mcp.tool(
        name="sdl_apply_edit",
        description=(
            "Apply a structured YAML edit addressed by JSON pointer, then "
            "return the updated content plus validation diagnostics. Supported "
            "operations are 'set', 'delete', and 'append'. `value_json` is used "
            "for set and append."
        ),
    )
    def sdl_apply_edit(
        sdl_content: str,
        operation: str,
        pointer: str,
        value_json: str = "null",
    ) -> str:
        try:
            value = json.loads(value_json)
        except json.JSONDecodeError as exc:
            return _invalid_edit_value(f"Invalid JSON in value_json: {exc}")
        except ValueError, RecursionError:
            # The decoder raises a plain ValueError beyond the integer digit limit and RecursionError beyond its depth.
            return _invalid_edit_value("Invalid JSON in value_json: the document exceeds the decoder limits.")
        return json_response(
            apply_structured_edit(
                sdl_content,
                operation=operation,
                pointer=pointer,
                value=value,
            )
        )
