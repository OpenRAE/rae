"""Opaque corpus storage preserves malformed input bytes and bounds decoding."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest
from tools import parity_storage as storage
from tools.parity_support import digest, encode


def write_files(root: Path, files: dict[Path, bytes]) -> None:
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def test_storage_preserves_opaque_bytes_and_dereferences_large_documents(tmp_path: Path) -> None:
    content = b"\xff\x00 significant trailing spaces  \nwithout newline"
    document = {"payload": "x" * (storage.INLINE_BYTES + 1)}
    files = {Path("inputs", digest(content)): content, Path("cases/large.json"): encode(document)}
    packed, raw = storage.pack(files)
    assert raw[digest(content)] == content
    assert all(len(value) <= storage.INLINE_BYTES + 1 for value in packed.values())
    assert packed == storage.pack(files)[0]
    write_files(tmp_path, packed)
    assert storage.read_blob(tmp_path, digest(content)) == content
    assert storage.read_document(tmp_path, Path("cases/large.json")) == document
    assert set(json.loads(packed[Path("cases/large.json")])) == {"document_ref"}


def test_storage_splits_incompressible_streams_and_detects_corruption(tmp_path: Path) -> None:
    content = hashlib.shake_256(b"public incompressible fixture").digest(storage.INLINE_BYTES * 2)
    identity = digest(content)
    packed, _ = storage.pack({Path("inputs", identity): content})
    assert json.loads(packed[Path("inputs", identity)])["parts"] >= 2
    write_files(tmp_path, packed)
    assert storage.read_blob(tmp_path, identity) == content
    first_piece = tmp_path / "pieces" / identity / "0"
    first_piece.write_bytes(b"wrong marker")
    with pytest.raises(ValueError, match="invalid parity input piece"):
        storage.read_blob(tmp_path, identity)


@pytest.mark.parametrize("index", [{"parts": 0}, {"parts": 513}, {"parts": True}, {"parts": 1, "other": 1}])
def test_storage_rejects_invalid_piece_counts(tmp_path: Path, index: dict) -> None:
    identity = digest(b"input")
    write_files(tmp_path, {Path("inputs", identity): encode(index)})
    with pytest.raises(ValueError, match="piece index"):
        storage.read_blob(tmp_path, identity)


def test_storage_rejects_oversized_and_wrong_digest_blobs(tmp_path: Path, monkeypatch) -> None:
    content = b"12345"
    identity = digest(content)
    write_files(tmp_path, {Path("inputs", identity): gzip.compress(content, mtime=0)})
    monkeypatch.setattr(storage, "MAX_BLOB_BYTES", 4)
    with pytest.raises(ValueError, match="oversized"):
        storage.read_blob(tmp_path, identity)
    with pytest.raises(ValueError, match="storage limit"):
        storage.pack({Path("inputs", identity): content})
    monkeypatch.setattr(storage, "MAX_BLOB_BYTES", 5)
    assert storage.read_blob(tmp_path, identity) == content
    (tmp_path / "inputs" / identity).write_bytes(gzip.compress(b"wrong", mtime=0))
    with pytest.raises(ValueError, match="digest"):
        storage.read_blob(tmp_path, identity)


@pytest.mark.parametrize("identity", ["../escape", "A" * 64, "g" * 64, None])
def test_storage_rejects_references_before_opening_paths(tmp_path: Path, identity: object, monkeypatch) -> None:
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: pytest.fail("must reject before opening a path"))
    with pytest.raises(ValueError, match="identity"):
        storage.read_blob(tmp_path, identity)


def test_scan_keeps_option_like_directory_names_out_of_scanner_options(tmp_path: Path, monkeypatch) -> None:
    from tools import gitleaks_tool

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(tmp_path / "modules")
    Path("--help").mkdir()
    qualified = tmp_path / "qualified-gitleaks"
    monkeypatch.setattr(gitleaks_tool, "ensure_gitleaks", lambda repo: qualified)
    calls = []

    def scanner(command, *, cwd):
        calls.append((command, cwd))
        return 0

    monkeypatch.setattr(storage.subprocess, "call", scanner)
    repo = tmp_path / "repo"
    assert storage.scan(Path("--help"), repo) == 0
    command, directory = calls[0]
    assert command[0] == str(qualified)
    assert command[-2:] == ["--", "./--help"]
    assert directory == tmp_path
    assert command[command.index("--config") + 1] == str(repo / ".gitleaks.toml")
