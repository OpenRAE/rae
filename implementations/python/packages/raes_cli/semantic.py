"""Offline, read-only command surface for RAES semantic operations."""

from __future__ import annotations

from pathlib import Path

import click
import typer
from raes import (
    SDL_SOURCE_FORMAT,
    SDLMigrationPolicy,
    SDLParserLimits,
)
from raes_conformance.conformance import contract_payload_root
from raes_contracts.operational_logging import get_logger

from ._semantic_portable import PORTABLE_MAX_BYTES, execute_portable
from ._semantic_result import (
    CommandStatus,
    OutputFormat,
    ResultMetadata,
    SemanticCommandResult,
)
from ._semantic_result import (
    command_diagnostic as _diagnostic,
)
from ._semantic_result import (
    command_result as _result,
)
from ._semantic_result import (
    render_result as _render,
)
from ._semantic_sdl import TransformProfile, execute_sdl

app = typer.Typer(
    help="Parse, validate, normalize, resolve, compile, transform, inspect, and check RAES artifacts.",
    no_args_is_help=True,
)

_LOGGER = get_logger(__name__)
_SDL_CONTRACT_ID = SDL_SOURCE_FORMAT
_SDL_MAX_BYTES = SDLParserLimits().max_input_bytes
_SOURCE_HELP = "Input path or '-' for stdin."
_CONTRACT_HELP = "Explicit versioned contract id."


def _read_input(source: str, *, max_bytes: int) -> bytes | None:
    """Return the input bytes, or ``None`` when the input is larger than ``max_bytes``."""

    if source == "-":
        raw = click.get_binary_stream("stdin").read(max_bytes + 1)
    else:
        path = Path(source)
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    return raw if len(raw) <= max_bytes else None


def _execute(
    operation: str,
    source: str,
    *,
    contract_id: str,
    migration_policy: SDLMigrationPolicy,
    transform: TransformProfile | None = None,
) -> SemanticCommandResult:
    if contract_id != _SDL_CONTRACT_ID and contract_payload_root(contract_id) is None:
        result = _result(
            operation,
            status=CommandStatus.USAGE,
            contract_id=None,
            diagnostics=(_diagnostic("cli.selector", "cli", "The contract selector is not supported."),),
        )
    else:
        max_bytes = _SDL_MAX_BYTES if contract_id == _SDL_CONTRACT_ID else PORTABLE_MAX_BYTES
        try:
            raw = _read_input(source, max_bytes=max_bytes)
        except OSError:
            # An absent or unreadable input is a bounded input failure, like an oversized input.
            raw = None
        if raw is None:
            result = _result(
                operation,
                status=CommandStatus.OPERATIONAL,
                contract_id=contract_id,
                diagnostics=(
                    _diagnostic(
                        "cli.input",
                        "cli",
                        "The input could not be read within the configured bounds.",
                    ),
                ),
                metadata=ResultMetadata(migration_policy=migration_policy),
            )
        else:
            try:
                if contract_id == _SDL_CONTRACT_ID:
                    result = execute_sdl(
                        operation,
                        raw,
                        migration_policy=migration_policy,
                        transform=transform,
                    )
                else:
                    result = execute_portable(operation, contract_id, raw)
            except Exception:
                # Boundary of the semantic command: the typed result reports an internal failure, so log the cause once.
                _LOGGER.exception("semantic %s operation stopped after an unexpected error", operation)
                result = _result(
                    operation,
                    status=CommandStatus.INTERNAL,
                    contract_id=contract_id,
                    diagnostics=(
                        _diagnostic(
                            "cli.internal",
                            "cli",
                            "The operation failed unexpectedly.",
                        ),
                    ),
                    metadata=ResultMetadata(migration_policy=migration_policy),
                )
    return result


def _run(
    operation: str,
    source: str,
    contract: str,
    output: OutputFormat,
    migration_policy: SDLMigrationPolicy,
    *,
    transform: TransformProfile | None = None,
) -> None:
    _render(
        _execute(
            operation,
            source,
            contract_id=contract,
            migration_policy=migration_policy,
            transform=transform,
        ),
        output,
    )


@app.command("parse")
def parse_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Perform bounded decoding and typed construction without a validity claim."""

    _run("parse", source, contract, output, migration_policy)


@app.command("validate")
def validate_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Run the owning structural and semantic admission checks."""

    _run("validate", source, contract, output, migration_policy)


@app.command("normalize")
def normalize_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Emit a deterministic normalized representation and provenance."""

    _run("normalize", source, contract, output, migration_policy)


@app.command("resolve")
def resolve_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Resolve and inspect local SDL declarations without acquisition or writes."""

    _run("resolve", source, contract, output, migration_policy)


@app.command("compile")
def compile_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Compile SDL and emit a bounded typed runtime-model summary."""

    _run("compile", source, contract, output, migration_policy)


@app.command("transform")
def transform_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    transform: TransformProfile = typer.Option(..., "--transform", help="Closed transform profile."),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Apply one explicitly selected RAES-owned transformation."""

    _run("transform", source, contract, output, migration_policy, transform=transform)


@app.command("inspect")
def inspect_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Inspect admitted typed artifacts without exposing raw values."""

    _run("inspect", source, contract, output, migration_policy)


@app.command("conformance")
def conformance_command(
    source: str = typer.Argument(..., help=_SOURCE_HELP),
    contract: str = typer.Option(_SDL_CONTRACT_ID, "--contract", help=_CONTRACT_HELP),
    output: OutputFormat = typer.Option(OutputFormat.HUMAN, "--output"),
    migration_policy: SDLMigrationPolicy = typer.Option(SDLMigrationPolicy.REJECT, "--migration-policy"),
) -> None:
    """Run RAES-owned local conformance checks without invoking a target."""

    _run("conformance", source, contract, output, migration_policy)
