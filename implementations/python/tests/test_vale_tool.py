"""Tests for the pinned repository-local Vale installer."""

from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.vale_tool as vale_tool  # noqa: E402


def test_vale_binary_uses_versioned_repository_cache(tmp_path: Path) -> None:
    assert vale_tool.vale_binary_path(tmp_path, version="3.15.2") == (
        tmp_path / ".cache" / "raes-sdl" / "tooling" / "vale" / "3.15.2" / "vale"
    )


def test_vale_rejects_an_asset_without_a_repository_pin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def reject_selection(**_kwargs: object) -> object:
        raise RuntimeError("no reviewed lock selection")

    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", reject_selection)

    with pytest.raises(RuntimeError, match="no reviewed lock selection"):
        vale_tool.ensure_vale(tmp_path, version="3.15.2")


def test_vale_extraction_rejects_archive_without_root_binary(tmp_path: Path) -> None:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        info = tarfile.TarInfo("../vale")
        body = b"unsafe"
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))

    archive_bytes = payload.getvalue()
    binary_path = tmp_path / "vale"
    with pytest.raises(RuntimeError, match="root vale binary"):
        vale_tool._extract_binary(archive_bytes, binary_path)
