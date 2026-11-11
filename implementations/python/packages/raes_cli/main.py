"""Typer application and command registry for the RAES CLI."""

from enum import Enum

import typer
from raes_contracts.operational_logging import set_application_log_level

from raes_cli import conformance, processor, runtime, sdl, semantic
from raes_cli.entrypoint import _distribution_version

app = typer.Typer(
    name="raes",
    help="RAES SDL and runtime CLI",
    no_args_is_help=True,
)

app.add_typer(sdl.app, name="sdl")
app.add_typer(processor.app, name="processor")
app.add_typer(conformance.app, name="conformance")
app.add_typer(semantic.app, name="semantic")
app.add_typer(runtime.app, name="runtime")


class LogLevel(str, Enum):
    """Minimum level of the operational log records on standard error."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"raes {_distribution_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING,
        "--log-level",
        case_sensitive=False,
        help="Minimum level of the operational log records on standard error.",
    ),
) -> None:
    """RAES SDL and runtime CLI."""

    set_application_log_level(log_level.value)
