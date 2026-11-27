"""RAES SDL MCP Server - tools for understanding, authoring, and validating SDL scenarios.

Launch via:
    python -m raes_mcp
    # or
    raes-mcp
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool
from mcp.types import ContentBlock
from pydantic import ValidationError
from raes_contracts.operational_logging import get_logger, run_application

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
_LOGGER = get_logger(__name__)
_INTERNAL_TOOL_ERROR = "the tool failed with an internal error; the server log records the failure"


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


def _tool_boundary[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Keep the text of an unexpected exception out of the tool result (ADR-116).

    FastMCP puts the text of any exception that a tool raises in the tool
    result. Tools render their expected failures themselves; this boundary
    logs each other failure one time, value-free, and gives the client a
    fixed message.
    """

    @functools.wraps(function)
    def boundary(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except ToolError:
            raise
        except Exception:
            _LOGGER.exception("MCP tool %s stopped after an unexpected error", function.__name__)
            raise ToolError(_INTERNAL_TOOL_ERROR) from None

    return boundary


class _RaesFastMCP(FastMCP):
    """Keep argument values and unexpected exception details out of tool results."""

    def add_tool(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().add_tool(_tool_boundary(fn), *args, **kwargs)

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


def main() -> int:
    """Console-script entry point for the `raes-mcp` command.

    Logging is configured before FastMCP is constructed, so log records go to
    standard error with the value-free formatter and stdout carries only the
    MCP protocol.
    """
    return run_application(lambda: create_server().run())
