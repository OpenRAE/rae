"""Local backup owns its SQLite destination on every completion path."""

import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
from raes_runtime import control_plane_store_maintenance as maintenance


@pytest.mark.parametrize("fails", [False, True])
def test_backup_closes_the_destination_connection(tmp_path: Path, monkeypatch, fails: bool) -> None:
    destination = tmp_path / "backup.sqlite3"
    connection = sqlite3.connect(destination)
    monkeypatch.setattr(maintenance.sqlite3, "connect", lambda *args, **kwargs: connection)
    source = Mock(spec=sqlite3.Connection)
    try:
        if fails:
            source.backup.side_effect = RuntimeError("backup interrupted")
            with pytest.raises(RuntimeError, match="backup interrupted"):
                maintenance._backup_connection(source, destination)
        else:
            maintenance._backup_connection(source, destination)
        source.backup.assert_called_once_with(connection)
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    finally:
        connection.close()
