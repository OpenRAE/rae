"""Runtime control-plane operator commands."""

from __future__ import annotations

from pathlib import Path

import typer
from raes_runtime.control_plane_store_maintenance import (
    DestinationConflictPolicy,
    LocalStoreMaintenanceOperation,
    maintain_local_control_plane_store,
)

app = typer.Typer(help="Runtime control-plane operations.")
store_app = typer.Typer(help="Offline local control-plane store maintenance.")
app.add_typer(store_app, name="store")


def _run_maintenance(
    *,
    operation: LocalStoreMaintenanceOperation,
    store_path: Path,
    target: str,
    run_scope: str,
    backup_path: Path | None = None,
    replace: bool = False,
) -> None:
    try:
        maintain_local_control_plane_store(
            operation=operation,
            store_path=store_path,
            target_name=target,
            run_scope=run_scope,
            backup_path=backup_path,
            conflict_policy=(DestinationConflictPolicy.REPLACE if replace else DestinationConflictPolicy.REFUSE),
        )
    except Exception:
        typer.echo(f"control-plane-store-{operation.value}-failed")
        raise typer.Exit(code=1) from None
    typer.echo(f"control-plane-store-{operation.value}-succeeded")


@store_app.command("check")
def check_store(
    store_path: Path,
    target: str = typer.Option(..., "--target"),
    run_scope: str = typer.Option(..., "--run-scope"),
) -> None:
    """Validate one offline local store under its exclusive lease."""

    _run_maintenance(
        operation=LocalStoreMaintenanceOperation.CHECK,
        store_path=store_path,
        target=target,
        run_scope=run_scope,
    )


@store_app.command("backup")
def backup_store(
    store_path: Path,
    backup_path: Path,
    target: str = typer.Option(..., "--target"),
    run_scope: str = typer.Option(..., "--run-scope"),
    replace: bool = typer.Option(False, "--replace", help="Replace an existing backup destination."),
) -> None:
    """Create one consistent offline SQLite backup."""

    _run_maintenance(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=store_path,
        backup_path=backup_path,
        target=target,
        run_scope=run_scope,
        replace=replace,
    )


@store_app.command("restore")
def restore_store(
    backup_path: Path,
    store_path: Path,
    target: str = typer.Option(..., "--target"),
    run_scope: str = typer.Option(..., "--run-scope"),
    replace: bool = typer.Option(False, "--replace", help="Replace an existing destination store."),
) -> None:
    """Restore one validated backup into an offline local store."""

    _run_maintenance(
        operation=LocalStoreMaintenanceOperation.RESTORE,
        store_path=store_path,
        backup_path=backup_path,
        target=target,
        run_scope=run_scope,
        replace=replace,
    )


__all__ = ("app",)
