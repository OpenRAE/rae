"""RAES SDL MCP Server - tools for understanding, authoring, and validating SDL scenarios.

Launch via:
    python -m raes_mcp
    # or
    raes-mcp
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool
from mcp.types import ContentBlock
from pydantic import ValidationError

from raes_mcp.tools.authoring import register as register_authoring_tools
from raes_mcp.tools.completeness import register as register_completeness_tools
from raes_mcp.tools.experiment_authoring import register as register_experiment_authoring_tools
from raes_mcp.tools.inspection import register as register_inspection_tools
from raes_mcp.tools.language_service import register as register_language_service_tools
from raes_mcp.tools.operations import register as register_operation_tools
from raes_mcp.tools.reference import register as register_reference_tools

_INSTRUCTIONS = """\
You are connected to the Reproducible Agentic Environments System (RAES)
authoring server. RAES supports agentic environments; RAES SDL is its authored scenario
language.

The SDL is a YAML-based language for specifying scenarios — \
who (entities, accounts, agents), what (nodes, features, \
content), when (scripts, stories, events), and declarative experiment \
semantics (objectives, scoring, conditions, relationships, workflows, \
variables).

Start with `raes_tool_surface` to understand the available tool families, \
then use `raes_agent_guidance` for scope boundaries, invariants, review \
priorities, and safe-operating expectations. Use `raes_intended_use_profiles` \
to select the claim scope and inspect current RAES delivery blockers. Use \
`sdl_overview` to orient \
yourself. Use `sdl_section_reference` for any section you need to understand. \
Use `sdl_get_example` to see real-world annotated scenarios. Use \
`sdl_completions`, `sdl_references`, \
`sdl_format`, `sdl_diagnostics`, and `sdl_apply_edit` for language-service \
workflows. Use `sdl_validate`, `sdl_design_assessment`, `sdl_plan`, and \
`sdl_claims_assessment` to check SDL YAML and avoid overstating what a \
scenario or dry run can prove.

To author an *experiment* (the pre-run specification that binds a task to a \
run plan — selection policies, stochastic controls, episode controls, and replication — \
distinct from the archival run/study records), use `experiment_scaffold` to \
start, `experiment_get_example` to see a worked design, and `experiment_validate` \
to check it.\
"""


_UNTYPED_EXPECTATION = "a value matching the tool input schema"
_UNMATCHED_ARGUMENTS = "arguments do not match the tool input schema"


def _expected_type(schema: Mapping[str, Any]) -> str:
    """Render the expected type of one argument from the tool's static input schema."""
    members = schema.get("anyOf") or schema.get("oneOf") or ()
    declared = schema.get("type") or [_expected_type(member) for member in members]
    names = [declared] if isinstance(declared, str) else list(dict.fromkeys(map(str, declared)))
    return " or ".join(names) or _UNTYPED_EXPECTATION


def _argument_error_message(tool: Tool, error: ValidationError) -> str:
    """Name each rejected argument and its expected type, never its value.

    Only the top-level location (a declared parameter name or alias) and the
    pydantic error code are used; pydantic messages and nested locations can
    carry client-supplied text, so they are dropped.
    """
    properties = tool.parameters.get("properties", {})
    kinds: dict[str, dict[str, None]] = {}
    for detail in error.errors(include_url=False, include_context=False, include_input=False):
        kinds.setdefault(str(next(iter(detail["loc"]), "")), {})[detail["type"]] = None
    lines = [
        f"{field}: expected {_expected_type(schema)} ({', '.join(kinds[field])})"
        for field, schema in properties.items()
        if field in kinds
    ]
    return f"Invalid arguments for tool {tool.name}: " + ("; ".join(lines) or _UNMATCHED_ARGUMENTS)


class _RaesFastMCP(FastMCP):
    """FastMCP server whose argument validation errors never echo argument values."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Sequence[ContentBlock] | dict[str, Any]:
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            cause = exc.__cause__
            tool = self._tool_manager.get_tool(name)
            if tool is None or not isinstance(cause, ValidationError):
                raise
            if cause.title != tool.fn_metadata.arg_model.__name__:
                raise
            raise ToolError(_argument_error_message(tool, cause)) from None


def create_server() -> FastMCP:
    """Build and return the configured MCP server instance."""
    mcp = _RaesFastMCP(
        name="raes",
        instructions=_INSTRUCTIONS,
    )
    register_reference_tools(mcp)
    register_completeness_tools(mcp)
    register_authoring_tools(mcp)
    register_experiment_authoring_tools(mcp)
    register_language_service_tools(mcp)
    register_inspection_tools(mcp)
    register_operation_tools(mcp)
    return mcp


def main() -> None:
    """Console-script entry point for the `raes-mcp` command."""
    create_server().run()
