"""Admission of the native analysis solver's ZIP carrier."""

from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from tools import verified_tool_installation as installation


def selection(payload=b"solver"):
    return SimpleNamespace(
        installed_manifest=(
            SimpleNamespace(
                path="release/bin/z3",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                executable=True,
            ),
        )
    )


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        for name, payload in entries:
            output.writestr(name, payload)
    return stream.getvalue()


def test_zip_materializes_only_verified_manifest():
    raw = archive([("release/bin/z3", b"solver"), ("release/unused", b"unused")])
    assert installation.materialize_zip(raw, selection()) == {"release/bin/z3": b"solver"}
    different = selection(b"different")
    with pytest.raises(installation.ToolInstallationError, match="installed-manifest-mismatch"):
        installation.materialize_zip(raw, different)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "bad\\name", "a//b", "a/../b"])
def test_zip_rejects_unselected_unsafe_path(name):
    raw = archive([("release/bin/z3", b"solver"), (name, b"unselected")])
    selected = selection()
    with pytest.raises(installation.ToolInstallationError, match="unsafe-archive-member"):
        installation.materialize_zip(raw, selected)


def test_zip_rejects_duplicates_links_and_file_parent():
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for entries in [[("a", b""), ("a", b"")], [(link, b"target")], [("a/b", b""), ("a", b"")]]:
        with pytest.warns(UserWarning) if entries[0][0] == "a" else nullcontext():
            raw = archive([("release/bin/z3", b"solver"), *entries])
        selected = selection()
        with pytest.raises(installation.ToolInstallationError, match="unsafe-archive-member"):
            installation.materialize_zip(raw, selected)


def test_zip_limits_and_corruption(monkeypatch):
    raw = archive([("release/bin/z3", b"solver")])
    monkeypatch.setattr(installation, "MAX_ARCHIVE_MEMBER_BYTES", 5)
    selected = selection()
    with pytest.raises(installation.ToolInstallationError, match="archive-size-limit"):
        installation.materialize_zip(raw, selected)
    with pytest.raises(installation.ToolInstallationError, match="unsafe-archive"):
        installation.materialize_zip(b"not a zip", selected)


def test_z3_installer_uses_locked_acquisition_and_verified_tree(tmp_path, monkeypatch):
    from tools import tooling_policy_gate, z3_tool

    payload = b"solver"
    raw = archive([("release/bin/z3", payload)])
    selected = selection(payload)
    selected.artifact_id = "z3-analysis"
    selected.platform_id = "linux-x86_64"
    selected.policy_refs = ("artifact-integrity-v1",)
    selected.source_urls = ("https://example.invalid/locked.zip",)
    selected.raw_manifest = (
        SimpleNamespace(path="solver.zip", size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), executable=False),
    )
    monkeypatch.setattr(tooling_policy_gate, "load_tooling_artifact_selection", lambda **kwargs: selected)
    # Portable locking is qualified in the tooling closure. This unit test
    # checks acquisition and verified materialization in the runtime closure.
    monkeypatch.setattr(installation, "_portable_lock", lambda _path: nullcontext())
    calls = []
    monkeypatch.setattr(z3_tool, "acquire_locked_bytes", lambda **kwargs: calls.append(kwargs) or raw)
    path = z3_tool.ensure_z3(tmp_path)
    assert path.read_bytes() == payload
    assert path.stat().st_mode & 0o777 == 0o500
    assert z3_tool.ensure_z3(tmp_path) == path
    assert len(calls) == 1
    assert calls[0]["expected"] == selected.raw_manifest[0]
