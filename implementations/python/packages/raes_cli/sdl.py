"""SDL composition and packaging commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import typer
from pydantic import ValidationError
from raes import SDLError, SDLParseError, format_sdl_source
from raes.module_registry import (
    LOCKFILE_NAME,
    load_lockfile,
    publish_module_to_oci_layout,
    resolve_lock_records,
)
from raes.parser import parse_sdl_file
from raes_contracts.errors import ConflictError, OperationalError

app = typer.Typer(help="SDL composition and packaging.")


def _refuse(action: str, path: Path, error: Exception) -> NoReturn:
    """Write one value-free failure line to stderr and exit with status 1 (ADR-116).

    The line names the failure kind and its public exception class, never the
    exception text, which can carry registry URLs, host paths or authored content.
    """

    if isinstance(error, SDLError | ValidationError):
        kind = "the input was rejected"
    elif isinstance(error, ConflictError):
        kind = "the request conflicts with the existing layout"
    else:
        kind = "a module registry, cache or layout operation failed"
    name = next(item.__name__ for item in type(error).__mro__ if not item.__name__.startswith("_"))
    typer.echo(f"error: could not {action} {path}: {kind} ({name})", err=True)
    raise typer.Exit(code=1) from error


@app.command("format")
def format_source(
    path: Path = typer.Argument(..., exists=True, readable=True),
    write: bool = typer.Option(False, "--write", help="Replace the source file with canonical SDL YAML."),
    check: bool = typer.Option(False, "--check", help="Fail when the source is not already canonical."),
) -> None:
    """Migrate recognized legacy syntax and emit canonical sdl-yaml/v1."""
    if write and check:
        raise typer.BadParameter("--write and --check are mutually exclusive")
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise typer.BadParameter("SDL source must be valid UTF-8") from exc
    try:
        result = format_sdl_source(original, path=path)
    except SDLParseError as exc:
        raise typer.BadParameter(exc.details) from exc
    # Composition of imports can refuse the source or fail to fetch an OCI module.
    except (SDLError, OperationalError) as exc:
        _refuse("format", path, exc)

    for diagnostic in result.diagnostics:
        start = diagnostic.primary_range.start
        typer.echo(
            f"{path}:{start.line}:{start.column}: {diagnostic.severity} [{diagnostic.code}] {diagnostic.message}",
            err=True,
        )
    if check:
        if result.content != original:
            typer.echo(f"{path}: not canonical", err=True)
            raise typer.Exit(code=1)
        return
    if write:
        path.write_text(result.content, encoding="utf-8")
        typer.echo(str(path))
        return
    typer.echo(result.content, nl=False)


@app.command("resolve")
def resolve(
    path: Path = typer.Argument(..., exists=True, readable=True),
    lockfile: Path | None = typer.Option(
        None,
        "--lockfile",
        help=f"Override lockfile path (default: alongside SDL as {LOCKFILE_NAME}).",
    ),
) -> None:
    """Resolve SDL imports and write/update the lockfile."""
    try:
        resolved = resolve_lock_records(path)
    except (SDLError, ValidationError, OperationalError) as exc:
        _refuse("resolve the imports of", path, exc)
    output_path = lockfile or (path.parent / LOCKFILE_NAME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(resolved.model_dump(mode="python"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(str(output_path))


@app.command("verify-imports")
def verify_imports(
    path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Verify lockfile, trust policy, and import expansion."""
    try:
        existing = load_lockfile(path.parent)
        if existing is None:
            raise typer.BadParameter(f"No {LOCKFILE_NAME} found next to {path}; run `raes sdl resolve` first.")
        expected = resolve_lock_records(path)
        if expected.model_dump(mode="python") != existing.model_dump(mode="python"):
            raise typer.BadParameter("Import lockfile is stale or does not match current resolution.")
        parse_sdl_file(path)
    except (SDLError, ValidationError, OperationalError) as exc:
        _refuse("verify the imports of", path, exc)
    typer.echo("imports verified")


@app.command("publish")
def publish(
    path: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(
        Path("dist"),
        "--output-dir",
        help="Directory for the versioned OCI layout slot; result layout_dir is the usable immutable layout.",
    ),
    signer_id: str = typer.Option("", "--signer-id", help="Signer identity label."),
    private_key: Path | None = typer.Option(
        None,
        "--private-key",
        exists=True,
        readable=True,
        help="Optional Ed25519 PEM private key used to sign the module bundle.",
    ),
) -> None:
    """Package an SDL module and report its usable immutable OCI layout."""
    try:
        result = publish_module_to_oci_layout(
            path,
            output_dir=output_dir,
            signer_id=signer_id,
            private_key_path=private_key,
        )
    except (SDLError, ConflictError, OperationalError) as exc:
        _refuse("publish", path, exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
