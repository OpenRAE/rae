"""Debian carriers must use the existing complete-tree admission boundary."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from copy import deepcopy
from pathlib import Path

import pytest
from tools import verified_tree_archive as archive
from tools import verified_tree_installation as installation
from tools.tooling_installed_tree import LockedInstalledTree, locked_installed_tree
from tools.tooling_policy_gate import LockedManifestEntry
from tools.verified_tree_manifest import parse_manifest


@pytest.mark.parametrize("source", ["tools/debian_tree_decoder.py", "tools/bounded_tool_process.py"])
def test_proof_pins_include_decoder_import_dependencies(source: str) -> None:
    from tools.check_participant_opacity_proof import (
        PROOF_TOOL_SOURCE_PATHS,
        ProofEvidenceError,
        _validate_tool_sources,
        load_proof_manifest,
    )

    root = Path(__file__).resolve().parents[3]
    assert source in PROOF_TOOL_SOURCE_PATHS
    toolchain = deepcopy(load_proof_manifest()["toolchain"])
    _validate_tool_sources(toolchain, root)
    selected = next(item for item in toolchain["tool_sources"] if item["path"] == source)
    selected["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ProofEvidenceError, match="source digest"):
        _validate_tool_sources(toolchain, root)


def deb_bytes(name: str = "./usr/bin/checker", *, kind: bytes = tarfile.REGTYPE) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as bundle:
        root = tarfile.TarInfo("./")
        root.type = tarfile.DIRTYPE
        bundle.addfile(root)
        member = tarfile.TarInfo(name)
        member.type = kind
        member.mode = 0o755
        member.linkname = "../../../../escape" if kind == tarfile.SYMTYPE else ""
        member.size = 4 if kind == tarfile.REGTYPE else 0
        bundle.addfile(member, io.BytesIO(b"tool") if member.size else None)
    control = io.BytesIO()
    with tarfile.open(fileobj=control, mode="w:gz"):
        pass
    result = b"!<arch>\n"
    for label, payload in [
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", control.getvalue()),
        ("data.tar.gz", data.getvalue()),
    ]:
        header = f"{label + '/':<16}{0:<12}{0:<6}{0:<6}{0o100644:<8o}{len(payload):<10}`\n"
        result += header.encode("ascii") + payload + (b"\n" if len(payload) % 2 else b"")
    return result


def describe(tmp_path: Path, payload: bytes) -> dict[str, object]:
    carrier = tmp_path / "input.deb"
    carrier.write_bytes(payload)
    entry = LockedManifestEntry("input.deb", hashlib.sha256(payload).hexdigest(), len(payload), False)
    return installation.describe_archive_tree(carrier, entry, archive_format="deb")


def test_debian_format_binds_manifest_and_lock(tmp_path: Path) -> None:
    descriptor = describe(tmp_path, deb_bytes())
    assert descriptor["format"] == "deb"
    assert (descriptor["file_count"], descriptor["directory_count"], descriptor["expanded_bytes"]) == (1, 2, 4)
    locked = locked_installed_tree(descriptor)
    assert locked == LockedInstalledTree(**descriptor)
    entries = [
        archive.TreeEntry("usr", "directory"),
        archive.TreeEntry("usr/bin", "directory"),
        archive.TreeEntry("usr/bin/checker", "file", hashlib.sha256(b"tool").hexdigest(), 4, True),
    ]
    payload = archive.manifest_bytes(entries, archive_format="deb")
    assert set(parse_manifest(payload, locked)) == {entry.path for entry in entries}
    default_payload = archive.manifest_bytes(entries)
    assert default_payload != payload
    with pytest.raises(RuntimeError, match="tree-integrity-failure"):
        parse_manifest(default_payload, locked)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("./../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("./usr/link", tarfile.SYMTYPE),
        ("./usr/pipe", tarfile.FIFOTYPE),
    ],
)
def test_debian_members_still_cross_existing_admission(tmp_path: Path, name: str, kind: bytes) -> None:
    payload = deb_bytes(name, kind=kind)
    with pytest.raises(RuntimeError, match="unsafe-archive-member"):
        describe(tmp_path, payload)


def test_bad_debian_decoder_input_has_no_manifest(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="archive-decoder-failed"):
        describe(tmp_path, b"invalid archive")


def test_unknown_archive_format_is_not_admitted(tmp_path: Path) -> None:
    descriptor = {
        "format": "zip",
        "manifest_sha256": "0" * 64,
        "file_count": 1,
        "directory_count": 1,
        "symlink_count": 0,
        "expanded_bytes": 1,
    }
    with pytest.raises(RuntimeError, match="invalid installed tree"):
        locked_installed_tree(descriptor)
    with pytest.raises(RuntimeError, match="unsupported-archive-format"):
        archive.manifest_bytes([], archive_format="zip")


def test_untyped_manifest_format_has_a_closed_failure() -> None:
    descriptor = LockedInstalledTree("deb", "0" * 64, 1, 1, 0, 1)
    payload = json.dumps({"schema": archive.TREE_MANIFEST_SCHEMA, "format": [], "entries": []}).encode()
    with pytest.raises(RuntimeError, match="tree-integrity-failure"):
        parse_manifest(payload, descriptor)
