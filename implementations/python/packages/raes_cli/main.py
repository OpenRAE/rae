"""Typer application and command registry for the RAES CLI."""

import typer

from raes_cli import conformance, corpus, libvirt, processor, runtime, sdl, semantic
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
app.add_typer(libvirt.app, name="libvirt")
app.add_typer(corpus.app, name="corpus")
app.add_typer(runtime.app, name="runtime")


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
) -> None:
    """RAES SDL and runtime CLI."""
