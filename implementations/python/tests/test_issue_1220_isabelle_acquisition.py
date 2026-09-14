"""Acceptance tests for issue #1220's native-client Isabelle inputs."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import tools.isabelle_tool as isabelle_tool
from tools import maintained_client_acquisition as client
from tools import verified_tool_installation as installation
from tools import verified_tree_archive as tree_archive
from tools import verified_tree_installation as tree_installation
from tools import verified_tree_validation as tree_validation
from tools.tooling_policy_gate import LockedArtifactSelection, LockedInstalledTree, LockedManifestEntry

REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = f"Isabelle{isabelle_tool.ISABELLE_VERSION}"
BINARY = b"#!/bin/sh\nexit 0\n"
LIBRARY = b"reviewed library bytes\n"
LICENSE = b"reviewed license\n"
PRIMARY_URL = "https://primary.example.invalid/Isabelle.tar.gz"
MIRROR_URL = "https://mirror.example.invalid/Isabelle.tar.gz"


def _file(name: str, payload: bytes, mode: int = 0o644) -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    member.mode = mode
    return member, payload


def _directory(name: str) -> tuple[tarfile.TarInfo, None]:
    member = tarfile.TarInfo(name)
    member.type = tarfile.DIRTYPE
    member.mode = 0o755
    return member, None


def _symlink(name: str, target: str) -> tuple[tarfile.TarInfo, None]:
    member = tarfile.TarInfo(name)
    member.type = tarfile.SYMTYPE
    member.linkname = target
    return member, None


def _default_members() -> list[tuple[tarfile.TarInfo, bytes | None]]:
    return [
        _directory(ROOT),
        _file(f"{ROOT}/bin/isabelle", BINARY, 0o755),
        _file(f"{ROOT}/lib/library.jar", LIBRARY),
        _file(f"{ROOT}/legal/base/LICENSE", LICENSE),
        _directory(f"{ROOT}/legal/module"),
        _symlink(f"{ROOT}/legal/module/LICENSE", "../base/LICENSE"),
        _symlink(f"{ROOT}/src/lib/ABSENT.a", "../ABSENT/ABSENT.a"),
    ]


def _archive(members: list[tuple[tarfile.TarInfo, bytes | None]] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for member, payload in members if members is not None else _default_members():
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
    return buffer.getvalue()


def _raw_entry(archive_bytes: bytes) -> LockedManifestEntry:
    return LockedManifestEntry("Isabelle.tar.gz", hashlib.sha256(archive_bytes).hexdigest(), len(archive_bytes))


def _described(tmp_path: Path, archive_bytes: bytes) -> LockedInstalledTree:
    carrier = tmp_path / f"describe-{hashlib.sha256(archive_bytes).hexdigest()[:12]}.tar.gz"
    carrier.write_bytes(archive_bytes)
    return LockedInstalledTree(**tree_installation.describe_archive_tree(carrier, _raw_entry(archive_bytes)))


def _selection(archive_bytes: bytes, installed_tree: LockedInstalledTree | None) -> LockedArtifactSelection:
    return LockedArtifactSelection(
        artifact_id="isabelle",
        artifact_class="native-tool",
        version=isabelle_tool.ISABELLE_VERSION,
        platform_id="linux-x86_64",
        profile_id="proof-linux-x86_64",
        repository="https://example.invalid/isabelle",
        release=ROOT,
        source_urls=(PRIMARY_URL, MIRROR_URL),
        locator_refs=("official-primary", "official-mirror"),
        raw_manifest=(_raw_entry(archive_bytes),),
        installed_manifest=(
            LockedManifestEntry(f"{ROOT}/bin/isabelle", hashlib.sha256(BINARY).hexdigest(), len(BINARY), True),
        ),
        installed_tree=installed_tree,
    )


@pytest.fixture(autouse=True)
def _removable_immutable_trees(tmp_path: Path) -> Iterator[None]:
    """Restore owner write access so pytest can remove sealed installations."""

    yield
    for current, directories, _files in os.walk(tmp_path, followlinks=False):
        for name in directories:
            directory = Path(current) / name
            if not directory.is_symlink():
                directory.chmod(0o700)


@contextmanager
def _unlocked(_path: Path, timeout: float | None = None) -> Iterator[None]:
    assert timeout == tree_installation.TREE_LOCK_TIMEOUT_SECONDS
    yield


class _Lock:
    """Install one reviewed synthetic selection and record every network use.

    The project test environment has no portable-lock dependency; the real
    native lock and crash behavior run in the frozen tooling closure through
    the issue harness.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, archive_bytes: bytes | None = None) -> None:
        self.archive_bytes = archive_bytes if archive_bytes is not None else _archive()
        self.selection = _selection(self.archive_bytes, _described(tmp_path, self.archive_bytes))
        self.transfers: list[tuple[str, str]] = []
        self.served = self.archive_bytes
        monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", self._select)
        monkeypatch.setattr(isabelle_tool.platform, "system", lambda: "Linux")
        monkeypatch.setattr(isabelle_tool.platform, "machine", lambda: "x86_64")
        monkeypatch.setattr(client, "run_curl_transfer", self._transfer)
        monkeypatch.setattr(installation, "_portable_lock", _unlocked)

    def _select(self, **_kwargs: object) -> LockedArtifactSelection:
        return self.selection

    def _transfer(
        self,
        _executable: Path,
        url: str,
        output: Path,
        *,
        ca_cert: Path | None,
        max_bytes: int,
        max_time_seconds: int | None = None,
        budget: client.TransferBudget = client.GENERIC_TRANSFER_BUDGET,
    ) -> dict[str, str]:
        assert ca_cert is None
        assert max_time_seconds is None
        assert max_bytes == self.selection.raw_manifest[0].size
        self.transfers.append((url, budget.budget_id))
        output.write_bytes(self.served)
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}


def _writable(path: Path) -> None:
    for parent in reversed((path, *path.parents)):
        if parent.is_dir() and not parent.is_symlink() and parent.stat().st_uid == os.geteuid():
            parent.chmod(parent.stat().st_mode | stat.S_IWUSR)
    if path.is_file() and not path.is_symlink():
        path.chmod(0o600)


def _target(repo_root: Path, lock: _Lock) -> Path:
    return tree_installation.tree_installation_path(installation.default_installation_root(repo_root), lock.selection)


def test_installed_tree_tampering_outside_the_executable_is_not_trusted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)

    home = isabelle_tool.acquire_isabelle(tmp_path)
    library = home / "lib" / "library.jar"
    _writable(library)
    library.write_bytes(b"tampered library bytes\n")

    with pytest.raises(isabelle_tool.IsabelleToolError, match="cache-integrity-failure"):
        isabelle_tool.require_isabelle(tmp_path)
    assert lock.transfers == [(PRIMARY_URL, "large-object")]


def test_acquisition_uses_the_large_object_client_budget_and_publishes_an_immutable_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)

    home = isabelle_tool.acquire_isabelle(tmp_path)

    assert lock.transfers == [(PRIMARY_URL, "large-object")]
    assert home == isabelle_tool.require_isabelle(tmp_path)
    assert (home / "bin" / "isabelle").read_bytes() == BINARY
    assert (home / "bin" / "isabelle").stat().st_mode & 0o777 == 0o500
    assert (home / "lib" / "library.jar").stat().st_mode & 0o777 == 0o400
    assert (home / "legal" / "module" / "LICENSE").read_bytes() == LICENSE
    assert os.readlink(home / "src" / "lib" / "ABSENT.a") == "../ABSENT/ABSENT.a"
    target = _target(tmp_path, lock)
    assert home == target / tree_installation.TREE_CONTENT_NAME / ROOT
    assert target.stat().st_mode & 0o777 == 0o500
    manifest = (target / tree_installation.TREE_MANIFEST_NAME).read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == lock.selection.installed_tree.manifest_sha256
    assert json.loads(manifest)["schema"] == "raes-installed-tree/v1"
    raw_object = target.parents[2] / tree_installation.RAW_OBJECT_NAME
    assert raw_object.read_bytes() == lock.archive_bytes
    assert raw_object.stat().st_mode & 0o777 == 0o400
    assert not list(target.parents[2].glob(".stage-*"))

    assert isabelle_tool.acquire_isabelle(tmp_path) == home
    assert len(lock.transfers) == 1


def test_an_explicit_approved_locator_is_selected_without_a_failover_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)

    def unavailable(*_args: object, **_kwargs: object) -> dict[str, str]:
        lock.transfers.append(("attempt", "failed"))
        return {"outcome": "failed", "reason_code": "curl-transfer-failed"}

    monkeypatch.setattr(client, "run_curl_transfer", unavailable)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="acquisition failed: curl-transfer-failed"):
        isabelle_tool.acquire_isabelle(tmp_path)
    assert lock.transfers == [("attempt", "failed")]

    monkeypatch.setattr(client, "run_curl_transfer", lock._transfer)
    lock.transfers.clear()
    isabelle_tool.acquire_isabelle(tmp_path, locator_ref="official-mirror")
    assert lock.transfers == [(MIRROR_URL, "large-object")]

    with pytest.raises(isabelle_tool.IsabelleToolError, match="not approved"):
        isabelle_tool.acquire_isabelle(tmp_path, locator_ref="unreviewed-mirror")


def test_verified_local_input_is_admitted_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    local_input = tmp_path / "seed" / "Isabelle.tar.gz"
    local_input.parent.mkdir()
    local_input.write_bytes(lock.archive_bytes)
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o700)

    home = isabelle_tool.acquire_isabelle(repo_root, local_input=local_input)

    assert lock.transfers == []
    assert (home / "bin" / "isabelle").read_bytes() == BINARY
    assert local_input.read_bytes() == lock.archive_bytes


@pytest.mark.parametrize(
    "carrier",
    [
        lambda archive: archive[:-1],
        lambda archive: archive + b"x",
        lambda archive: bytes([archive[0] ^ 1]) + archive[1:],
    ],
)
def test_corrupt_local_input_fails_terminally_without_network_or_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    carrier,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    local_input = tmp_path / "Isabelle.tar.gz"
    local_input.write_bytes(carrier(lock.archive_bytes))
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o700)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="local input failed locked identity validation"):
        isabelle_tool.acquire_isabelle(repo_root, local_input=local_input)

    target = _target(repo_root, lock)
    assert lock.transfers == []
    assert not target.exists()
    assert not (target.parents[2] / tree_installation.RAW_OBJECT_NAME).exists()
    assert not list(target.parents[2].glob(".stage-*"))


def test_symlinked_local_input_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    real_input = tmp_path / "real.tar.gz"
    real_input.write_bytes(lock.archive_bytes)
    link = tmp_path / "link.tar.gz"
    link.symlink_to(real_input)
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o700)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="local input failed"):
        isabelle_tool.acquire_isabelle(repo_root, local_input=link)
    assert lock.transfers == []


def test_downloaded_bytes_that_differ_from_the_lock_are_not_published(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    middle = len(lock.archive_bytes) // 2
    lock.served = (
        lock.archive_bytes[:middle] + bytes([lock.archive_bytes[middle] ^ 1]) + lock.archive_bytes[middle + 1 :]
    )

    with pytest.raises(isabelle_tool.IsabelleToolError, match="acquired bytes differ from the reviewed lock"):
        isabelle_tool.acquire_isabelle(tmp_path)

    target = _target(tmp_path, lock)
    assert not target.exists()
    assert not (target.parents[2] / tree_installation.RAW_OBJECT_NAME).exists()
    assert not list(target.parents[2].glob(".stage-*"))


@pytest.mark.parametrize(
    "tamper",
    [
        "modify-file",
        "add-file",
        "remove-file",
        "retarget-symlink",
        "widen-mode",
        "replace-manifest",
    ],
)
def test_tampered_installation_is_quarantined_then_rebuilt_only_from_the_retained_raw_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tamper: str,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    home = isabelle_tool.acquire_isabelle(tmp_path)
    target = _target(tmp_path, lock)
    library = home / "lib" / "library.jar"
    if tamper == "modify-file":
        _writable(library)
        library.write_bytes(b"tampered library bytes\n")
    elif tamper == "add-file":
        _writable(home / "lib")
        (home / "lib" / "extra.jar").write_bytes(b"extra")
    elif tamper == "remove-file":
        _writable(home / "lib")
        library.unlink()
    elif tamper == "retarget-symlink":
        link = home / "legal" / "module" / "LICENSE"
        _writable(link.parent)
        link.unlink()
        link.symlink_to("/etc/passwd")
    elif tamper == "widen-mode":
        library.chmod(0o644)
    else:
        manifest = target / tree_installation.TREE_MANIFEST_NAME
        _writable(manifest)
        manifest.write_bytes(manifest.read_bytes().replace(b"library.jar", b"library.jaz"))

    with pytest.raises(isabelle_tool.IsabelleToolError, match="cache-integrity-failure"):
        isabelle_tool.require_isabelle(tmp_path)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="cache-integrity-failure"):
        isabelle_tool.acquire_isabelle(tmp_path)
    quarantine = installation.default_installation_root(tmp_path) / "isabelle" / ".quarantine"
    assert [path.name.split("-")[0] for path in quarantine.iterdir()] == ["cache"]
    assert not target.exists()
    assert len(lock.transfers) == 1

    rebuilt = isabelle_tool.acquire_isabelle(tmp_path)
    assert rebuilt == home
    assert (rebuilt / "lib" / "library.jar").read_bytes() == LIBRARY
    assert len(lock.transfers) == 1


def test_tampered_retained_raw_object_is_quarantined_without_reacquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    home = isabelle_tool.acquire_isabelle(tmp_path)
    target = _target(tmp_path, lock)
    raw_object = target.parents[2] / tree_installation.RAW_OBJECT_NAME
    _writable(home / "lib" / "library.jar")
    (home / "lib" / "library.jar").write_bytes(b"x")
    with pytest.raises(isabelle_tool.IsabelleToolError, match="cache-integrity-failure"):
        isabelle_tool.acquire_isabelle(tmp_path)
    _writable(raw_object)
    corrupted = bytearray(raw_object.read_bytes())
    corrupted[len(corrupted) // 2] ^= 1
    raw_object.write_bytes(bytes(corrupted))
    raw_object.chmod(0o400)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="raw-integrity-failure"):
        isabelle_tool.acquire_isabelle(tmp_path)

    assert not raw_object.exists()
    assert len(lock.transfers) == 1


def test_missing_installation_is_reported_without_acquisition(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock = _Lock(monkeypatch, tmp_path)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="not acquired; run the acquire command first"):
        isabelle_tool.require_isabelle(tmp_path)
    assert lock.transfers == []


def test_legacy_archive_is_a_verified_carrier_and_legacy_tree_is_never_trusted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    legacy_archive = isabelle_tool.isabelle_archive_path(tmp_path)
    legacy_archive.parent.mkdir(parents=True)
    legacy_archive.write_bytes(lock.archive_bytes)
    legacy_home = isabelle_tool._legacy_home(tmp_path)
    (legacy_home / "bin").mkdir(parents=True)
    (legacy_home / "bin" / "isabelle").write_bytes(b"#!/bin/sh\necho untrusted\n")
    legacy_marker = isabelle_tool._legacy_marker(tmp_path)
    legacy_marker.write_text(f"{lock.selection.raw_manifest[0].sha256}\n", encoding="ascii")

    home = isabelle_tool.acquire_isabelle(tmp_path)

    assert lock.transfers == []
    assert (home / "bin" / "isabelle").read_bytes() == BINARY
    assert not legacy_archive.exists()
    assert not legacy_home.exists()
    assert not legacy_marker.exists()
    quarantine = installation.default_installation_root(tmp_path) / "isabelle" / ".quarantine"
    assert sorted(path.name.split("-")[0] for path in quarantine.iterdir()) == ["legacy", "legacy"]
    for path in quarantine.rglob("*"):
        if path.is_file() and not path.is_symlink():
            assert path.stat().st_mode & 0o111 == 0


def test_invalid_legacy_archive_is_quarantined_and_terminal_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    legacy_archive = isabelle_tool.isabelle_archive_path(tmp_path)
    legacy_archive.parent.mkdir(parents=True)
    legacy_archive.write_bytes(lock.archive_bytes[:-1])

    with pytest.raises(isabelle_tool.IsabelleToolError, match="legacy-integrity-failure"):
        isabelle_tool.acquire_isabelle(tmp_path)

    assert lock.transfers == []
    assert not legacy_archive.exists()
    target = _target(tmp_path, lock)
    assert not (target.parents[2] / tree_installation.RAW_OBJECT_NAME).exists()


@pytest.mark.parametrize(
    ("members", "reason"),
    [
        ([_symlink(f"{ROOT}/escape", "/etc/passwd")], "unsafe-archive-member"),
        ([_symlink(f"{ROOT}/escape", "../../outside")], "unsafe-archive-member"),
        (
            [
                _directory(f"{ROOT}/a/b"),
                _symlink(f"{ROOT}/a/b/up", "../.."),
                _symlink(f"{ROOT}/escape", "a/b/up/../.."),
            ],
            "unsafe-archive-member",
        ),
        ([_symlink(f"{ROOT}/self", ".")], "unsafe-archive-member"),
        ([_symlink(f"{ROOT}/link", "lib"), _file(f"{ROOT}/link/payload", b"x")], "conflicting-archive-member"),
        ([_file(f"{ROOT}/lib/library.jar", LIBRARY)], "duplicate-archive-member"),
        ([_file(f"{ROOT}/../outside", b"x")], "unsafe-archive-member"),
        ([_file("/absolute", b"x")], "unsafe-archive-member"),
    ],
)
def test_archive_admission_rejects_unsafe_tree_shapes(
    tmp_path: Path,
    members: list[tuple[tarfile.TarInfo, bytes | None]],
    reason: str,
) -> None:
    archive_bytes = _archive([*_default_members(), *members])
    carrier = tmp_path / "archive.tar.gz"
    carrier.write_bytes(archive_bytes)

    raw_entry = _raw_entry(archive_bytes)
    with pytest.raises(RuntimeError, match=reason):
        tree_installation.describe_archive_tree(carrier, raw_entry)


@pytest.mark.parametrize("member_type", [tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE])
def test_archive_admission_rejects_hardlinks_and_special_members(tmp_path: Path, member_type: bytes) -> None:
    special = tarfile.TarInfo(f"{ROOT}/special")
    special.type = member_type
    special.linkname = f"{ROOT}/lib/library.jar"
    archive_bytes = _archive([*_default_members(), (special, None)])
    carrier = tmp_path / "archive.tar.gz"
    carrier.write_bytes(archive_bytes)

    raw_entry = _raw_entry(archive_bytes)
    with pytest.raises(RuntimeError, match="unsafe-archive-member"):
        tree_installation.describe_archive_tree(carrier, raw_entry)


def test_describe_rejects_an_archive_that_is_not_the_locked_raw_object(tmp_path: Path) -> None:
    archive_bytes = _archive()
    carrier = tmp_path / "archive.tar.gz"
    carrier.write_bytes(archive_bytes + b"x")

    raw_entry = _raw_entry(archive_bytes)
    with pytest.raises(RuntimeError, match="raw-manifest-mismatch"):
        tree_installation.describe_archive_tree(carrier, raw_entry)


@pytest.mark.parametrize(
    "drift",
    [
        {"file_count": 2},
        {"directory_count": 99},
        {"symlink_count": 0},
        {"expanded_bytes": 1},
        {"manifest_sha256": "0" * 64},
    ],
)
def test_archive_that_differs_from_the_reviewed_tree_identity_is_not_published(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    drift: dict[str, object],
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    lock.selection = replace(lock.selection, installed_tree=replace(lock.selection.installed_tree, **drift))

    with pytest.raises(
        isabelle_tool.IsabelleToolError, match="archive-member-limit|archive-size-limit|installed-manifest-mismatch"
    ):
        isabelle_tool.acquire_isabelle(tmp_path)

    target = _target(tmp_path, lock)
    assert not target.exists()
    assert not list(target.parent.glob(".stage-*"))


def test_executable_lock_entry_must_match_the_installed_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    executable = replace(lock.selection.installed_manifest[0], sha256="1" * 64)
    lock.selection = replace(lock.selection, installed_manifest=(executable,))

    with pytest.raises(isabelle_tool.IsabelleToolError, match="installed-manifest-mismatch"):
        isabelle_tool.acquire_isabelle(tmp_path)


def test_selection_without_a_reviewed_installed_tree_is_rejected_before_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    lock.selection = replace(lock.selection, installed_tree=None)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="installed tree"):
        isabelle_tool.acquire_isabelle(tmp_path)
    assert lock.transfers == []


@pytest.mark.parametrize(("system", "machine"), [("Darwin", "arm64"), ("Linux", "aarch64"), ("Windows", "AMD64")])
def test_unsupported_platforms_fail_explicitly_before_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    system: str,
    machine: str,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    monkeypatch.setattr(isabelle_tool.platform, "system", lambda: system)
    monkeypatch.setattr(isabelle_tool.platform, "machine", lambda: machine)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="supports Linux x86_64 only"):
        isabelle_tool.acquire_isabelle(tmp_path)
    assert lock.transfers == []
    assert not (tmp_path / ".cache").exists()


def test_proof_preflight_lists_every_missing_prerequisite_without_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _Lock(monkeypatch, tmp_path)

    def must_not_execute(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preflight must not execute a prover or native client")

    monkeypatch.setattr(isabelle_tool.subprocess, "run", must_not_execute)
    monkeypatch.setattr(isabelle_tool, "ISABELLE_REQUIRED_FONTCONFIG_PATHS", (tmp_path / "absent-fonts",))

    result = isabelle_tool.proof_host_preflight(
        tmp_path,
        bwrap=tmp_path / "absent-bwrap",
        font_query=lambda: False,
        locale_query=lambda: False,
    )

    assert result == {
        "missing": ["bubblewrap", "fontconfig", "fonts", "locale-c-utf-8", "isabelle-installation"],
        "outcome": "failed",
        "platform_boundary": "linux-x86_64",
    }


def test_proof_preflight_passes_only_with_a_complete_verified_closure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    isabelle_tool.acquire_isabelle(tmp_path)
    bwrap = tmp_path / "bwrap"
    bwrap.write_bytes(b"")
    placeholder = isabelle_tool.proof_host_preflight(
        tmp_path, bwrap=bwrap, font_query=lambda: True, locale_query=lambda: True
    )
    assert "bubblewrap" in placeholder["missing"]
    bwrap.chmod(0o700)
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    monkeypatch.setattr(isabelle_tool, "ISABELLE_REQUIRED_FONTCONFIG_PATHS", (fonts,))
    monkeypatch.setattr(isabelle_tool, "ISABELLE_FONTCONFIG_LIST", Path(sys.executable))

    result = isabelle_tool.proof_host_preflight(
        tmp_path, bwrap=bwrap, font_query=lambda: True, locale_query=lambda: True
    )

    assert result["outcome"] == "passed"
    assert result["missing"] == []
    assert len(lock.transfers) == 1


def test_locale_query_uses_a_fixed_minimal_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    locale_list = tmp_path / "locale"
    locale_list.write_bytes(b"")
    locale_list.chmod(0o700)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def completed(stdout: bytes, returncode: int = 0):
        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, returncode, stdout=stdout)

        return run

    monkeypatch.setattr(isabelle_tool.subprocess, "run", completed(b"C\nC.utf8\nPOSIX\n"))
    assert isabelle_tool._locale_is_available(locale_list) is True
    assert calls[0][0] == [str(locale_list), "-a"]
    assert calls[0][1]["env"] == {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    assert calls[0][1]["stdin"] is subprocess.DEVNULL
    monkeypatch.setattr(isabelle_tool.subprocess, "run", completed(b"C\nPOSIX\n"))
    assert isabelle_tool._locale_is_available(locale_list) is False
    monkeypatch.setattr(isabelle_tool.subprocess, "run", completed(b"C.utf8\n", returncode=1))
    assert isabelle_tool._locale_is_available(locale_list) is False
    assert isabelle_tool._locale_is_available(tmp_path / "absent") is False


def test_replay_requires_the_locale_before_resolving_the_distribution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bwrap = tmp_path / "bwrap"
    bwrap.write_bytes(b"")
    bwrap.chmod(0o700)
    monkeypatch.setattr(isabelle_tool, "_require_fontconfig_runtime", lambda: None)
    monkeypatch.setattr(isabelle_tool, "_locale_is_available", lambda: False)

    def must_not_resolve(_repo_root: Path) -> Path:
        raise AssertionError("distribution resolved before the locale capability")

    monkeypatch.setattr(isabelle_tool, "require_isabelle", must_not_resolve)
    with pytest.raises(isabelle_tool.IsabelleToolError, match=r"C\.UTF-8 locale is required"):
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=bwrap)


def test_large_object_budget_is_separately_bounded_native_configuration(tmp_path: Path) -> None:
    budget = client.LARGE_OBJECT_TRANSFER_BUDGET
    argv = client.curl_transfer_argv(
        client.SYSTEM_CURL,
        PRIMARY_URL,
        tmp_path / "raw",
        ca_cert=None,
        max_bytes=1_228_480_874,
        budget=budget,
    )

    assert argv[argv.index("--max-filesize") + 1] == "1228480874"
    assert argv[argv.index("--max-time") + 1] == "3600"
    assert argv[argv.index("--speed-limit") + 1] == str(64 * 1024)
    assert argv[argv.index("--speed-time") + 1] == "120"
    assert argv[argv.index("--retry") + 1] == "2"
    assert argv[argv.index("--proto") + 1] == "=https"
    assert argv[argv.index("--proto-redir") + 1] == "=https"
    assert "--disable" in argv
    assert not {"--insecure", "--retry-all-errors", "--location-trusted"} & set(argv)
    generic = client.curl_transfer_argv(client.SYSTEM_CURL, PRIMARY_URL, tmp_path / "raw", ca_cert=None, max_bytes=1024)
    assert "--speed-limit" not in generic
    assert generic[generic.index("--max-time") + 1] == "30"
    with pytest.raises(ValueError, match="outside the large-object artifact budget"):
        client.curl_transfer_argv(
            client.SYSTEM_CURL,
            PRIMARY_URL,
            tmp_path / "raw",
            ca_cert=None,
            max_bytes=budget.max_bytes + 1,
            budget=budget,
        )
    with pytest.raises(ValueError, match="between 1 and 3600 seconds"):
        client.curl_transfer_argv(
            client.SYSTEM_CURL,
            PRIMARY_URL,
            tmp_path / "raw",
            ca_cert=None,
            max_bytes=1024,
            max_time_seconds=3601,
            budget=budget,
        )
    with pytest.raises(ValueError, match="outside the generic artifact budget"):
        client.curl_transfer_argv(
            client.SYSTEM_CURL, PRIMARY_URL, tmp_path / "raw", ca_cert=None, max_bytes=1_228_480_874
        )


def test_large_object_wall_deadline_covers_the_native_retry_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}
    monkeypatch.setattr(client, "_curl_preflight_failure", lambda _executable: None)

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        observed.update(kwargs)
        raise subprocess.TimeoutExpired(argv, float(kwargs["timeout"]))

    monkeypatch.setattr(client.subprocess, "run", fake_run)
    output = tmp_path / "raw"
    output.write_bytes(b"partial")

    result = client.run_curl_transfer(
        client.SYSTEM_CURL,
        PRIMARY_URL,
        output,
        ca_cert=None,
        max_bytes=1024,
        budget=client.LARGE_OBJECT_TRANSFER_BUDGET,
    )

    budget = client.LARGE_OBJECT_TRANSFER_BUDGET
    assert result == {"outcome": "failed", "reason_code": "curl-wall-deadline"}
    assert observed["timeout"] == budget.max_time_seconds + budget.wall_grace_seconds
    assert budget.wall_grace_seconds > budget.retry_max_time_seconds
    assert observed["env"] == {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
    assert not output.exists()


def test_isabelle_acquisition_has_no_repository_http_transport() -> None:
    from tools.tooling_artifact_policy_discovery import python_scan

    for relative in ("tools/isabelle_tool.py", "tools/verified_tree_installation.py"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "urllib" not in source
        assert "http.client" not in source
        assert python_scan(source).network_call_count == 0


def test_cli_describe_tree_reports_the_reviewable_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    carrier = tmp_path / "Isabelle.tar.gz"
    carrier.write_bytes(lock.archive_bytes)
    monkeypatch.setattr(sys, "argv", ["isabelle_tool", "describe-tree", "--local-input", str(carrier)])

    assert isabelle_tool.main() == 0
    described = json.loads(capsys.readouterr().out)
    assert described == {
        "directory_count": lock.selection.installed_tree.directory_count,
        "expanded_bytes": lock.selection.installed_tree.expanded_bytes,
        "file_count": lock.selection.installed_tree.file_count,
        "format": "tar.gz",
        "manifest_sha256": lock.selection.installed_tree.manifest_sha256,
        "symlink_count": lock.selection.installed_tree.symlink_count,
    }
    assert described["symlink_count"] == 2


def _large_object_transfer(
    server_port: int,
    path: str,
    output: Path,
    *,
    ca_cert: Path,
    budget: client.TransferBudget = client.LARGE_OBJECT_TRANSFER_BUDGET,
    max_time_seconds: int | None = None,
) -> dict[str, str]:
    return client.run_curl_transfer(
        client.SYSTEM_CURL,
        f"https://127.0.0.1:{server_port}{path}",
        output,
        ca_cert=ca_cert,
        max_bytes=1024,
        max_time_seconds=max_time_seconds,
        budget=budget,
    )


@pytest.mark.integration
def test_real_curl_large_object_budget_keeps_size_redirect_tls_and_disconnect_enforcement(tmp_path: Path) -> None:
    from test_issue_1217_bootstrap_profiles import _https_fixture

    server, ca_cert = _https_fixture(tmp_path)
    port = server.server_port
    try:
        assert _large_object_transfer(port, "/oversize", tmp_path / "oversize", ca_cert=ca_cert) == {
            "outcome": "failed",
            "reason_code": "curl-size-limit-enforced",
        }
        assert not (tmp_path / "oversize").exists()
        assert _large_object_transfer(port, "/redirect", tmp_path / "redirect", ca_cert=ca_cert) == {
            "outcome": "passed",
            "reason_code": "curl-transfer-qualified",
        }
        assert _large_object_transfer(port, "/small", tmp_path / "tls", ca_cert=tmp_path / "wrong-ca.pem") == {
            "outcome": "failed",
            "reason_code": "curl-tls-rejected",
        }
        assert _large_object_transfer(port, "/disconnect", tmp_path / "disconnect", ca_cert=ca_cert) == {
            "outcome": "failed",
            "reason_code": "curl-transfer-failed",
        }
    finally:
        server.shutdown()


@pytest.mark.integration
def test_real_curl_large_object_budget_uses_native_bounded_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import test_issue_1217_bootstrap_profiles as curl_fixture

    server, ca_cert = curl_fixture._https_fixture(tmp_path)
    monkeypatch.setattr(curl_fixture._CurlFixture, "retries", {})
    try:
        result = _large_object_transfer(server.server_port, "/retry503", tmp_path / "retry", ca_cert=ca_cert)
    finally:
        server.shutdown()

    assert result == {"outcome": "passed", "reason_code": "curl-transfer-qualified"}
    assert curl_fixture._CurlFixture.retries["/retry503"] == 1


@pytest.mark.integration
def test_real_curl_large_object_budget_aborts_stalled_and_overdue_transfers(tmp_path: Path) -> None:
    from test_issue_1217_bootstrap_profiles import _https_fixture

    server, ca_cert = _https_fixture(tmp_path)
    stalled_budget = replace(
        client.LARGE_OBJECT_TRANSFER_BUDGET,
        low_speed_bytes_per_second=1024 * 1024,
        low_speed_seconds=1,
        retries=0,
    )
    try:
        began = time.monotonic()
        stalled = _large_object_transfer(
            server.server_port,
            "/trickle",
            tmp_path / "stalled",
            ca_cert=ca_cert,
            budget=stalled_budget,
            max_time_seconds=30,
        )
        stalled_seconds = time.monotonic() - began
        overdue = _large_object_transfer(
            server.server_port,
            "/slow",
            tmp_path / "overdue",
            ca_cert=ca_cert,
            max_time_seconds=1,
        )
    finally:
        server.shutdown()

    assert stalled == {"outcome": "failed", "reason_code": "curl-transfer-deadline"}
    assert stalled_seconds < 15
    assert overdue == {"outcome": "failed", "reason_code": "curl-transfer-deadline"}


_TREE_POLICY = {
    "format": "tar.gz",
    "manifest_sha256": "a" * 64,
    "file_count": 1,
    "directory_count": 1,
    "symlink_count": 0,
    "expanded_bytes": 1,
}


def test_native_tool_installation_requires_a_reviewed_bounded_installed_tree(tmp_path: Path) -> None:
    from test_tooling_artifact_policy import ARTIFACT_LOCK_PATH, _failures, _load, _seed_policy, _write_json

    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    artifact = lock["artifacts"][0]
    platform = artifact["platforms"][0]
    tree_rules = {"tooling-installed-tree-class", "tooling-installed-tree-required", "tooling-installed-tree-bounds"}

    platform["installed_tree"] = dict(_TREE_POLICY)
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-installed-tree-class" in _failures(root)

    artifact["artifact_class"] = "native-tool"
    platform.pop("installed_tree")
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-installed-tree-required" in _failures(root)

    for drift in (
        {"expanded_bytes": tree_archive.MAX_TREE_EXPANDED_BYTES + 1},
        {"file_count": tree_archive.MAX_TREE_MEMBERS},
    ):
        platform["installed_tree"] = {**_TREE_POLICY, **drift}
        _write_json(root, ARTIFACT_LOCK_PATH, lock)
        assert "tooling-installed-tree-bounds" in _failures(root)
    platform["raw_manifest"][0]["size"] = tree_validation.MAX_TREE_RAW_BYTES + 1
    platform["installed_tree"] = dict(_TREE_POLICY)
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert "tooling-installed-tree-bounds" in _failures(root)

    platform["raw_manifest"][0]["size"] = 1
    _write_json(root, ARTIFACT_LOCK_PATH, lock)
    assert not tree_rules & _failures(root)


def test_ordered_locator_references_must_match_source_urls(tmp_path: Path) -> None:
    from test_tooling_artifact_policy import ARTIFACT_LOCK_PATH, _failures, _load, _seed_policy, _write_json

    root = _seed_policy(tmp_path)
    lock = _load(root, ARTIFACT_LOCK_PATH)
    lock["artifacts"][0]["platforms"][0]["source_urls"].append("https://mirror.example.invalid/tool-a.tar.gz")
    _write_json(root, ARTIFACT_LOCK_PATH, lock)

    assert "tooling-locator-arity" in _failures(root)


def test_proof_host_offline_kit_must_carry_the_native_proof_closure(tmp_path: Path) -> None:
    from test_tooling_artifact_policy import PROFILES_PATH, _failures, _load, _seed_policy, _write_json

    root = _seed_policy(tmp_path)
    profiles = _load(root, PROFILES_PATH)
    host = profiles["host_profiles"][0]
    host["proof_support"] = "linux-x86_64-required"
    host["required_capability_ids"] = ["git", "bubblewrap", "fontconfig", "fonts", "locale-c-utf-8"]
    host["offline_kit"]["host_prerequisite_package_ids"] = ["git", "bubblewrap", "fontconfig", "fonts-dejavu-core"]
    _write_json(root, PROFILES_PATH, profiles)
    assert "tooling-host-proof-closure" in _failures(root)

    host["offline_kit"]["host_prerequisite_package_ids"].append("libc-bin")
    _write_json(root, PROFILES_PATH, profiles)
    assert "tooling-host-proof-closure" not in _failures(root)

    host["native_family"] = "unreviewed-family"
    _write_json(root, PROFILES_PATH, profiles)
    assert "tooling-host-proof-closure" in _failures(root)


@pytest.mark.parametrize(("disposition", "rejected"), [("governed", True), ("legacy-remediation", False)])
def test_governed_acquisition_paths_cannot_keep_repository_http(
    tmp_path: Path,
    disposition: str,
    rejected: bool,
) -> None:
    from test_tooling_artifact_policy import INVENTORY_COVERAGE_PATH, _failures, _load, _seed_policy, _write_json

    root = _seed_policy(tmp_path)
    relative_path = "tools/fetch_proof.py"
    (root / relative_path).write_text(
        "from urllib.request import urlopen\nurlopen('https://example.invalid/proof.tar.gz')\n",
        encoding="utf-8",
    )
    coverage = _load(root, INVENTORY_COVERAGE_PATH)
    coverage["acquisition_paths"].append(
        {"path": relative_path, "inventory_id": "I09", "disposition": disposition, "site_count": 1}
    )
    _write_json(root, INVENTORY_COVERAGE_PATH, coverage)

    failures = _failures(root, tracked_paths=[relative_path])
    assert ("tooling-governed-repository-http" in failures) is rejected
    assert "tooling-acquisition-drift" not in failures


def test_checked_in_isabelle_authority_binds_the_reviewed_complete_tree() -> None:
    from tools.tooling_installed_tree import locked_installed_tree

    lock = json.loads((REPO_ROOT / "implementations/tooling/artifacts.lock.json").read_text(encoding="utf-8"))
    isabelle = next(item for item in lock["artifacts"] if item["artifact_id"] == "isabelle")
    platform = isabelle["platforms"][0]
    tree = locked_installed_tree(platform["installed_tree"])

    assert isabelle["artifact_class"] == "native-tool"
    assert platform["raw_manifest"] == [
        {
            "path": "Isabelle2025-2_linux.tar.gz",
            "sha256": "a20a507bc7c1270d8be96a9f3fbec06345387789d2dc2c4d3df6260d47bfb33c",
            "size": 1228480874,
        }
    ]
    assert tree == LockedInstalledTree(
        format="tar.gz",
        manifest_sha256="a1a818fc3fd41b3f60a34154c0871469619bc826d8238f1349e73e92355e4bb1",
        file_count=24079,
        directory_count=2589,
        symlink_count=457,
        expanded_bytes=2301957383,
    )
    assert len(isabelle["source"]["locator_refs"]) == len(platform["source_urls"]) == 2
    coverage = json.loads((REPO_ROOT / "implementations/tooling/inventory-coverage.json").read_text(encoding="utf-8"))
    dispositions = {item["path"]: item["disposition"] for item in coverage["acquisition_paths"]}
    assert dispositions["tools/isabelle_tool.py"] == "governed"
    from tools.tooling_artifact_policy_discovery import python_scan

    for path, disposition in dispositions.items():
        if disposition == "governed" and path.endswith(".py"):
            assert python_scan((REPO_ROOT / path).read_text(encoding="utf-8")).network_call_count == 0, path
    profiles = json.loads(
        (REPO_ROOT / "implementations/tooling/profiles/development-profiles.json").read_text(encoding="utf-8")
    )
    proof_host = next(
        item for item in profiles["host_profiles"] if item["host_profile_id"] == "proof-ubuntu-22.04-x86_64"
    )
    assert {"bubblewrap", "fontconfig", "fonts-dejavu-core", "libc-bin"} <= set(
        proof_host["offline_kit"]["host_prerequisite_package_ids"]
    )


@pytest.mark.parametrize(
    ("tree", "locators", "message"),
    [
        ({**_TREE_POLICY, "format": "zip"}, ["primary"], "invalid installed tree"),
        ({**_TREE_POLICY, "unexpected": True}, ["primary"], "invalid installed tree"),
        ({**_TREE_POLICY, "file_count": True}, ["primary"], "invalid installed tree"),
        (dict(_TREE_POLICY), ["primary", "mirror"], "invalid selection response"),
    ],
)
def test_selection_projection_rejects_invalid_tree_and_locator_shapes(
    tree: dict[str, object],
    locators: list[str],
    message: str,
) -> None:
    from tools.tooling_policy_gate import _selection_from_document

    document = {
        "artifact_id": "isabelle",
        "artifact_class": "native-tool",
        "version": "2025-2",
        "policy_refs": ["artifact-integrity-v1"],
        "source": {"repository": "https://example.invalid", "release": "r", "locator_refs": locators},
        "platform": {
            "platform_id": "linux-x86_64",
            "source_urls": ["https://example.invalid/a.tar.gz"],
            "raw_manifest": [{"path": "a.tar.gz", "sha256": "b" * 64, "size": 1}],
            "installed_manifest": [{"path": "a/bin/tool", "sha256": "c" * 64, "size": 1, "executable": True}],
            "installed_tree": tree,
            "profile_ids": ["proof-linux-x86_64"],
        },
    }

    with pytest.raises(RuntimeError, match=message):
        _selection_from_document(document, "proof-linux-x86_64")


def test_offline_kit_fetch_uses_the_primary_locator_and_large_object_budget_for_proof_archives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tools import bootstrap_profile

    payload = b"locked-proof-archive"
    selection = {
        "host_profile": {"host_profile_id": "proof-host", "offline_kit": {"artifact_ids": ["isabelle"]}},
        "artifacts": [
            {
                "artifact_id": "isabelle",
                "artifact_class": "native-tool",
                "version": "2025-2",
                "platform": {
                    "source_urls": [PRIMARY_URL, MIRROR_URL],
                    "raw_manifest": [
                        {"path": "Isabelle.tar.gz", "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
                    ],
                },
            }
        ],
        "policy_sha256": "a" * 64,
    }
    observed: dict[str, object] = {}

    def fake_transfer(_executable: Path, url: str, output: Path, **kwargs: object) -> dict[str, str]:
        observed.update(kwargs, url=url)
        output.write_bytes(payload)
        return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}

    monkeypatch.setattr(bootstrap_profile, "load_tooling_host_profile_selection", lambda _host_id: selection)
    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", fake_transfer)
    kit_root = tmp_path / "kit"
    kit_root.mkdir()

    result = bootstrap_profile.fetch_offline_kit_payloads("proof-host", kit_root, ("isabelle",))

    assert result[0]["path"] == "archives/isabelle/Isabelle.tar.gz"
    assert observed["url"] == PRIMARY_URL
    assert observed["budget"] is client.LARGE_OBJECT_TRANSFER_BUDGET
    assert observed["max_bytes"] == len(payload)


def test_offline_kit_verification_probes_the_proof_native_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    probed: list[list[str]] = []

    def native_results(host: dict[str, object]) -> list[dict[str, str]]:
        probed.append(list(host["required_capability_ids"]))
        return [
            {"capability_id": capability, "outcome": "failed" if capability == "fonts" else "passed"}
            for capability in host["required_capability_ids"]
        ]

    monkeypatch.setattr(bootstrap_profile, "_native_client_results", native_results)

    assert bootstrap_profile._proof_native_closure_result({"proof_support": "unsupported"}) == {
        "outcome": "not-run",
        "results": [],
    }
    failed = bootstrap_profile._proof_native_closure_result({"proof_support": "linux-x86_64-required"})
    assert failed["outcome"] == "failed"
    assert probed == [["bubblewrap", "fontconfig", "fonts", "locale-c-utf-8"]]
    monkeypatch.setattr(
        bootstrap_profile,
        "_native_client_results",
        lambda host: [{"capability_id": item, "outcome": "passed"} for item in host["required_capability_ids"]],
    )
    assert bootstrap_profile._proof_native_closure_result({"proof_support": "linux-x86_64-required"})["outcome"] == (
        "passed"
    )


def test_archive_member_may_precede_its_explicit_directory_but_a_directory_cannot_repeat(tmp_path: Path) -> None:
    ordered = _archive([_file(f"{ROOT}/bin/isabelle", BINARY, 0o755), _directory(f"{ROOT}/bin"), _directory(ROOT)])
    carrier = tmp_path / "ordered.tar.gz"
    carrier.write_bytes(ordered)
    described = tree_installation.describe_archive_tree(carrier, _raw_entry(ordered))
    assert (described["file_count"], described["directory_count"]) == (1, 2)

    repeated = _archive([_directory(ROOT), _directory(ROOT)])
    carrier.write_bytes(repeated)
    raw_entry = _raw_entry(repeated)
    with pytest.raises(RuntimeError, match="duplicate-archive-member"):
        tree_installation.describe_archive_tree(carrier, raw_entry)


@pytest.mark.parametrize(
    "damage",
    [
        lambda archive: archive[:-4],
        lambda archive: archive[:-8] + bytes([archive[-8] ^ 1]) + archive[-7:],
        lambda archive: archive + b"trailing-garbage",
    ],
)
def test_gzip_trailer_and_trailing_bytes_are_validated(tmp_path: Path, damage) -> None:
    damaged = damage(_archive())
    carrier = tmp_path / "damaged.tar.gz"
    carrier.write_bytes(damaged)

    raw_entry = _raw_entry(damaged)
    with pytest.raises(RuntimeError, match="unsafe-archive"):
        tree_installation.describe_archive_tree(carrier, raw_entry)


def test_decompressed_padding_after_the_tar_end_is_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as archive:
        for member, payload in _default_members():
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
    archive_bytes = gzip.compress(tar_buffer.getvalue() + bytes(256 * 1024))
    carrier = tmp_path / "padded.tar.gz"
    carrier.write_bytes(archive_bytes)
    monkeypatch.setattr(tree_archive, "MAX_TREE_TRAILER_BYTES", 16)

    raw_entry = _raw_entry(archive_bytes)
    with pytest.raises(RuntimeError, match="archive-size-limit"):
        tree_installation.describe_archive_tree(carrier, raw_entry)


def _manifest_descriptor(entries: list[tree_archive.TreeEntry]) -> LockedInstalledTree:
    return LockedInstalledTree(**tree_archive.tree_descriptor(entries))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.replace(b'"schema":', b'"schema":"x","schema":', 1),
        lambda payload: payload.replace(b"raes-installed-tree/v1", b"raes-installed-tree/v0"),
        lambda payload: payload.replace(b'"kind":"directory"', b'"kind":"socket"', 1),
        lambda payload: payload.replace(b'"format":"tar.gz"', b'"format":"tar.gz","extra":1'),
        lambda payload: payload + b" ",
        lambda payload: b"\xff" + payload,
    ],
)
def test_retained_manifest_parsing_is_closed_and_canonical(mutation) -> None:
    entries = [
        tree_archive.TreeEntry(ROOT, "directory"),
        tree_archive.TreeEntry(f"{ROOT}/tool", "file", "a" * 64, 1, True),
    ]
    payload = tree_archive.manifest_bytes(entries)
    descriptor = _manifest_descriptor(entries)
    assert set(tree_archive.parse_manifest(payload, descriptor)) == {ROOT, f"{ROOT}/tool"}

    mutated = mutation(payload)
    with pytest.raises(RuntimeError, match="tree-integrity-failure"):
        tree_archive.parse_manifest(mutated, descriptor)


@pytest.mark.parametrize(
    "entries",
    [
        [tree_archive.TreeEntry(f"{ROOT}/tool", "file", "a" * 64, 1, True)],
        [
            tree_archive.TreeEntry(ROOT, "directory"),
            tree_archive.TreeEntry(f"{ROOT}/escape", "symlink", target="../../outside"),
        ],
    ],
)
def test_retained_manifest_requires_real_parents_and_confined_links(entries: list[tree_archive.TreeEntry]) -> None:
    payload = tree_archive.manifest_bytes(entries)
    descriptor = _manifest_descriptor(entries)

    with pytest.raises(RuntimeError, match="tree-integrity-failure"):
        tree_archive.parse_manifest(payload, descriptor)


@pytest.mark.parametrize(
    "change",
    [
        {"installed_tree": None},
        {"tree": {"format": "zip"}},
        {"tree": {"symlink_count": -1}},
        {"tree": {"file_count": True}},
        {"tree": {"file_count": tree_archive.MAX_TREE_MEMBERS}},
        {"tree": {"expanded_bytes": tree_archive.MAX_TREE_EXPANDED_BYTES + 1}},
        {"tree": {"manifest_sha256": "not-a-digest"}},
        {"raw_size": tree_validation.MAX_TREE_RAW_BYTES + 1},
        {"executables": 2},
        {"policy_refs": ()},
        {"installed_path": "../escape"},
    ],
)
def test_tree_selection_must_be_closed_and_bounded(tmp_path: Path, change: dict[str, object]) -> None:
    archive_bytes = _archive()
    selection = _selection(archive_bytes, _described(tmp_path, archive_bytes))
    if "installed_tree" in change:
        selection = replace(selection, installed_tree=None)
    if "tree" in change:
        selection = replace(selection, installed_tree=replace(selection.installed_tree, **change["tree"]))
    if "raw_size" in change:
        selection = replace(selection, raw_manifest=(replace(selection.raw_manifest[0], size=change["raw_size"]),))
    if "executables" in change:
        extra = LockedManifestEntry(f"{ROOT}/lib/library.jar", hashlib.sha256(LIBRARY).hexdigest(), len(LIBRARY), True)
        selection = replace(selection, installed_manifest=(*selection.installed_manifest, extra))
    if "policy_refs" in change:
        selection = replace(selection, policy_refs=())
    if "installed_path" in change:
        selection = replace(
            selection, installed_manifest=(replace(selection.installed_manifest[0], path=change["installed_path"]),)
        )

    with pytest.raises(RuntimeError, match="invalid-selection|unsafe-archive-member"):
        tree_installation.tree_installation_path(tmp_path, selection)


def test_non_linux_durability_synchronizes_every_staged_file_and_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    synchronized_files: list[Path] = []
    synchronized_directories: list[Path] = []
    monkeypatch.setattr(tree_installation, "platform", SimpleNamespace(system=lambda: "Darwin"))
    monkeypatch.setattr(tree_installation, "_fsync_file", synchronized_files.append)
    monkeypatch.setattr(installation, "_fsync_directory", synchronized_directories.append)

    def unexpected_global_sync() -> None:
        raise AssertionError("non-Linux durability must not rely on sync(2)")

    monkeypatch.setattr(tree_installation.os, "sync", unexpected_global_sync)
    home = isabelle_tool.acquire_isabelle(tmp_path)

    staged_files = {path.name for path in synchronized_files}
    assert {"isabelle", "library.jar", "LICENSE", tree_installation.TREE_MANIFEST_NAME} <= staged_files
    assert any(name.startswith(".stage-raw-") for name in staged_files)
    assert any(path.name == "legal" for path in synchronized_directories)
    assert home.parent.parent in synchronized_directories
    assert len(lock.transfers) == 1


def test_linux_durability_uses_one_blocking_sync_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _Lock(monkeypatch, tmp_path)
    events: list[str] = []
    monkeypatch.setattr(tree_installation, "platform", SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setattr(tree_installation.os, "sync", lambda: events.append("sync"))
    original_checkpoint = installation._publication_checkpoint
    monkeypatch.setattr(
        installation,
        "_publication_checkpoint",
        lambda name, path: (events.append(name), original_checkpoint(name, path)),
    )

    isabelle_tool.acquire_isabelle(tmp_path)

    assert events.index("sync") < events.index("staged-durable") < events.index("published")


def test_symlinked_legacy_archive_is_quarantined_without_being_followed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    outside = tmp_path / "outside.tar.gz"
    outside.write_bytes(lock.archive_bytes)
    legacy_archive = isabelle_tool.isabelle_archive_path(tmp_path)
    legacy_archive.parent.mkdir(parents=True)
    legacy_archive.symlink_to(outside)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="legacy-integrity-failure"):
        isabelle_tool.acquire_isabelle(tmp_path)

    assert lock.transfers == []
    assert not legacy_archive.is_symlink()
    assert outside.read_bytes() == lock.archive_bytes


def test_retained_raw_object_quarantines_redundant_legacy_carriers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    home = isabelle_tool.acquire_isabelle(tmp_path)
    target = _target(tmp_path, lock)
    _writable(home / "lib" / "library.jar")
    (home / "lib" / "library.jar").write_bytes(b"x")
    with pytest.raises(isabelle_tool.IsabelleToolError, match="cache-integrity-failure"):
        isabelle_tool.acquire_isabelle(tmp_path)
    carrier = target.parents[2] / f"{tree_installation.LEGACY_CARRIER_PREFIX}redundant"
    carrier.write_bytes(b"stale")

    rebuilt = isabelle_tool.acquire_isabelle(tmp_path)

    assert (rebuilt / "lib" / "library.jar").read_bytes() == LIBRARY
    assert not carrier.exists()
    assert len(lock.transfers) == 1


def test_special_file_inside_the_installed_tree_is_not_trusted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _Lock(monkeypatch, tmp_path)
    home = isabelle_tool.acquire_isabelle(tmp_path)
    _writable(home / "lib")
    (home / "lib" / "library.jar").unlink()
    os.mkfifo(home / "lib" / "library.jar", 0o400)

    with pytest.raises(isabelle_tool.IsabelleToolError, match="cache-integrity-failure"):
        isabelle_tool.require_isabelle(tmp_path)


def test_storage_exhaustion_during_tree_extraction_is_terminal_and_leaves_no_partial_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import errno

    lock = _Lock(monkeypatch, tmp_path)

    def disk_full(*_args: object) -> str:
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr(tree_archive.StageSink, "file", disk_full)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="storage-exhausted"):
        isabelle_tool.acquire_isabelle(tmp_path)

    target = _target(tmp_path, lock)
    assert not target.exists()
    assert not list(target.parent.glob(".stage-*"))


@pytest.mark.parametrize(
    ("argv", "patched", "expected_exit", "expected_output"),
    [
        (["acquire", "--local-input", "seed.tar.gz", "--locator-ref", "official-mirror"], "acquire", 0, "acquired"),
        (["preflight"], "preflight-failed", 1, '"outcome": "failed"'),
        (["preflight"], "preflight-passed", 0, '"outcome": "passed"'),
        (["verify"], "verify", 0, '"result": "kernel-checked"'),
        (["acquire"], "policy-failure", 1, "isabelle-tool: development artifact policy failed"),
    ],
)
def test_cli_dispatches_each_operation_with_bounded_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    patched: str,
    expected_exit: int,
    expected_output: str,
) -> None:
    observed: dict[str, object] = {}

    def acquire(**kwargs: object) -> Path:
        observed.update(kwargs)
        if patched == "policy-failure":
            raise RuntimeError("development artifact policy failed before acquisition")
        return Path("unused")

    monkeypatch.setattr(isabelle_tool, "acquire_isabelle", acquire)
    monkeypatch.setattr(
        isabelle_tool,
        "proof_host_preflight",
        lambda: {"outcome": "passed" if patched == "preflight-passed" else "failed", "missing": []},
    )
    monkeypatch.setattr(isabelle_tool, "run_isabelle_build", lambda: {"result": "kernel-checked"})
    monkeypatch.setattr(sys, "argv", ["isabelle_tool", *argv])

    assert isabelle_tool.main() == expected_exit
    captured = capsys.readouterr()
    assert expected_output in captured.out + captured.err
    if patched == "acquire":
        assert observed == {"local_input": Path("seed.tar.gz"), "locator_ref": "official-mirror"}


@pytest.mark.parametrize("rename_requires_writable_source", [False, True])
def test_tree_root_is_sealed_before_it_becomes_visible_except_where_apfs_requires_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rename_requires_writable_source: bool,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    target = _target(tmp_path, lock)
    events: list[str] = []
    real_rename = os.rename
    monkeypatch.setattr(
        installation,
        "_directory_rename_requires_writable_source",
        lambda: rename_requires_writable_source,
    )

    def rename(source: Path, destination: Path) -> None:
        if Path(destination) == target:
            expected_mode = 0o700 if rename_requires_writable_source else 0o500
            assert Path(source).stat().st_mode & 0o777 == expected_mode
            events.append("rename")
        real_rename(source, destination)

    monkeypatch.setattr(installation.os, "rename", rename)
    monkeypatch.setattr(tree_installation.os, "rename", rename)
    original_checkpoint = installation._publication_checkpoint
    monkeypatch.setattr(
        installation,
        "_publication_checkpoint",
        lambda name, path: (events.append(name), original_checkpoint(name, path)),
    )

    isabelle_tool.acquire_isabelle(tmp_path)

    tree_events = events[events.index("staged-written") :]
    expected = ["staged-written", "staged-durable", "rename", "published", "parent-durable"]
    if rename_requires_writable_source:
        expected.insert(3, "renamed-unsealed")
    assert tree_events == expected
    assert target.stat().st_mode & 0o777 == 0o500


def test_apfs_tree_publication_interrupted_before_its_seal_recovers_without_quarantine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    home = isabelle_tool.acquire_isabelle(tmp_path)
    target = _target(tmp_path, lock)
    target.chmod(0o700)
    monkeypatch.setattr(installation, "_directory_rename_requires_writable_source", lambda: True)

    assert isabelle_tool.acquire_isabelle(tmp_path) == home

    assert target.stat().st_mode & 0o777 == 0o500
    assert not (installation.default_installation_root(tmp_path) / "isabelle" / ".quarantine").exists() or not list(
        (installation.default_installation_root(tmp_path) / "isabelle" / ".quarantine").iterdir()
    )
    assert len(lock.transfers) == 1


def test_non_executable_bubblewrap_placeholder_fails_before_distribution_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    placeholder = tmp_path / "bwrap"
    placeholder.write_bytes(b"#!/bin/sh\n")

    def must_not_resolve(_repo_root: Path) -> Path:
        raise AssertionError("distribution resolved without a runnable isolation boundary")

    monkeypatch.setattr(isabelle_tool, "require_isabelle", must_not_resolve)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="bubblewrap is required"):
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=placeholder)


def _proof_slice_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "issue-1220-proof-input-qualification/v1",
        "passed_cases": ["T05-cold-convergence", "T13-malicious-archive"],
        "not_run_cases": {"T11-egress-denied-admission": "bubblewrap-network-namespace-unavailable"},
        "elapsed_seconds": {"T05-cold-convergence": 2.5, "T13-malicious-archive": 0.25},
        "coverage": {"canonical_outcome_recorded": False},
    }
    document.update(changes)
    return document


def test_proof_slice_evidence_is_bound_to_the_exact_harness_without_canonical_cases(tmp_path: Path) -> None:
    from tools import bootstrap_profile

    evidence = tmp_path / "proof-input-qualification.json"
    evidence.write_text(json.dumps(_proof_slice_document()), encoding="utf-8")

    results = bootstrap_profile._load_slice_results(REPO_ROOT, (evidence,))

    harness = "implementations/python/tests/issue_1220_proof_input_harness.py"
    digest = hashlib.sha256((REPO_ROOT / harness).read_bytes()).hexdigest()
    assert results == [
        {
            "slice_id": "T05-cold-convergence",
            "canonical_case_id": "T05",
            "harness_path": harness,
            "harness_sha256": digest,
            "outcome": "passed",
            "elapsed_seconds": 2.5,
        },
        {
            "slice_id": "T11-egress-denied-admission",
            "canonical_case_id": "T11",
            "harness_path": harness,
            "harness_sha256": digest,
            "outcome": "not-run",
            "reason_code": "bubblewrap-network-namespace-unavailable",
        },
        {
            "slice_id": "T13-malicious-archive",
            "canonical_case_id": "T13",
            "harness_path": harness,
            "harness_sha256": digest,
            "outcome": "passed",
            "elapsed_seconds": 0.25,
        },
    ]
    schema = json.loads(
        (REPO_ROOT / "implementations/tooling/schemas/profiles.schema.json").read_text(encoding="utf-8")
    )
    import jsonschema

    for result in results:
        jsonschema.validate(
            result, {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/sliceResult"}
        )
    assert not {"T05", "T11", "T13"} & bootstrap_profile._CASE_IDS


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (_proof_slice_document(schema="issue-9999-unknown/v1"), "unknown harness"),
        (_proof_slice_document(coverage={"canonical_outcome_recorded": True}), "closed shape"),
        (_proof_slice_document(passed_cases=[]), "closed shape"),
        (_proof_slice_document(elapsed_seconds={"T05-cold-convergence": 1}), "closed shape"),
        (_proof_slice_document(passed_cases=["cold-convergence"], elapsed_seconds={"cold-convergence": 1}), "outside"),
        (_proof_slice_document(passed_cases=["T01-forged-proof"], elapsed_seconds={"T01-forged-proof": 1}), "outside"),
        (_proof_slice_document(not_run_cases={"T24-forged-release": "not-run"}), "outside"),
        (_proof_slice_document(not_run_cases={"T11-egress-denied-admission": "Not A Reason"}), "not-run reason"),
        (
            _proof_slice_document(
                passed_cases=["T05-cold-convergence"],
                elapsed_seconds={"T05-cold-convergence": -1},
                not_run_cases={},
            ),
            "invalid duration",
        ),
        (
            {
                "schema": "issue-1219-local-installation-qualification/v1",
                "passed_cases": ["unmapped-case"],
                "elapsed_seconds": {"unmapped-case": 1},
                "coverage": {"canonical_outcome_recorded": False},
            },
            "outside",
        ),
    ],
)
def test_proof_slice_evidence_rejects_overclaims_and_unbound_shapes(
    tmp_path: Path,
    document: dict[str, object],
    message: str,
) -> None:
    from tools import bootstrap_profile

    evidence = tmp_path / "slices.json"
    evidence.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        bootstrap_profile._load_slice_results(REPO_ROOT, (evidence,))


def test_repeated_slice_evidence_is_rejected(tmp_path: Path) -> None:
    from tools import bootstrap_profile

    evidence = tmp_path / "slices.json"
    evidence.write_text(json.dumps(_proof_slice_document()), encoding="utf-8")

    with pytest.raises(ValueError, match="repeats a slice"):
        bootstrap_profile._load_slice_results(REPO_ROOT, (evidence, evidence))


@pytest.mark.integration
def test_real_proof_input_qualification_harness(tmp_path: Path) -> None:
    output = tmp_path / "proof-input-qualification.json"
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT / "implementations" / "tooling" / "python"),
            "--frozen",
            "--no-default-groups",
            "python",
            str(Path(__file__).with_name("issue_1220_proof_input_harness.py")),
            str(tmp_path / "root"),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    for current, directories, _files in os.walk(tmp_path, followlinks=False):
        for name in directories:
            if not (Path(current) / name).is_symlink():
                (Path(current) / name).chmod(0o700)

    assert completed.returncode == 0, completed.stderr[-4000:]
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["schema"] == "issue-1220-proof-input-qualification/v1"
    assert evidence["installation_policy"] == tree_installation.INSTALLATION_TREE_POLICY_ID
    assert evidence["coverage"]["canonical_outcome_recorded"] is False
    assert evidence["cold_processes"] == 32
    mechanism = {
        "T05-bounded-lock-timeout",
        "T05-cold-convergence",
        "T05-crash-recovery",
        "T05-live-publisher-exclusion",
        "T05-quota-failure-recovery",
        "T05-warm-validation",
        "T13-corrupt-local-input",
        "T13-malicious-archive",
        "T13-missing-native-closure",
    }
    assert mechanism <= set(evidence["passed_cases"])
    assert set(evidence["passed_cases"]) | set(evidence["not_run_cases"]) == mechanism | {"T11-egress-denied-admission"}


def _drift_digest(bound: str):
    def tamper(sources: list[dict[str, str]]) -> list[dict[str, str]]:
        return [{**item, "digest": "sha256:" + "0" * 64} if item["path"] == bound else item for item in sources]

    return tamper


@pytest.mark.integration
@pytest.mark.parametrize(
    "tamper",
    [
        lambda sources: sources[:3],
        _drift_digest("tools/maintained_client_acquisition.py"),
        _drift_digest("tools/tooling_policy_gate.py"),
        _drift_digest("tools/verified_tool_installation.py"),
        _drift_digest("tools/verified_tree_installation.py"),
    ],
)
def test_proof_evidence_binds_every_prover_admission_source(tamper) -> None:
    from copy import deepcopy

    from tools.check_participant_opacity_proof import (
        PROOF_TOOL_SOURCE_PATHS,
        ProofEvidenceError,
        load_proof_manifest,
        validate_proof_manifest,
    )

    manifest = load_proof_manifest()
    assert [item["path"] for item in manifest["toolchain"]["tool_sources"]] == list(PROOF_TOOL_SOURCE_PATHS)
    assert {
        "tools/maintained_client_acquisition.py",
        "tools/tooling_policy_gate.py",
        "tools/verified_tool_installation.py",
        "tools/verified_tree_installation.py",
    } <= set(PROOF_TOOL_SOURCE_PATHS)
    tampered = deepcopy(manifest)
    tampered["toolchain"]["tool_sources"] = tamper(tampered["toolchain"]["tool_sources"])

    with pytest.raises(ProofEvidenceError):
        validate_proof_manifest(tampered, run_prover=False)


@pytest.mark.parametrize(
    ("schema", "harness_module"),
    [
        ("issue-1219-local-installation-qualification/v1", "issue_1219_installation_harness"),
        ("issue-1220-proof-input-qualification/v1", "issue_1220_proof_input_harness"),
    ],
)
def test_slice_registry_is_closed_to_exactly_what_each_harness_emits(schema: str, harness_module: str) -> None:
    import importlib

    from tools import bootstrap_profile

    harness_path, case_mapping = bootstrap_profile._SLICE_HARNESSES[schema]
    harness = importlib.import_module(harness_module)

    assert Path(harness.__file__).resolve() == (REPO_ROOT / harness_path).resolve()
    assert set(case_mapping) == set(harness.SLICE_CASE_NAMES)


@pytest.mark.parametrize(("system", "machine"), [("Darwin", "arm64"), ("Linux", "aarch64")])
def test_replay_and_resolution_fail_explicitly_on_unsupported_platforms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    system: str,
    machine: str,
) -> None:
    _Lock(monkeypatch, tmp_path)
    isabelle_tool.acquire_isabelle(tmp_path)
    monkeypatch.setattr(isabelle_tool.platform, "system", lambda: system)
    monkeypatch.setattr(isabelle_tool.platform, "machine", lambda: machine)

    def must_not_execute(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an unsupported platform attempted replay")

    monkeypatch.setattr(isabelle_tool.subprocess, "run", must_not_execute)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="supports Linux x86_64 only"):
        isabelle_tool.require_isabelle(tmp_path)
    runnable_bwrap = Path(sys.executable)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="supports Linux x86_64 only"):
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=runnable_bwrap)


def test_manifest_bound_is_enforced_when_describing_and_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = _Lock(monkeypatch, tmp_path)
    carrier = tmp_path / "bounded.tar.gz"
    carrier.write_bytes(lock.archive_bytes)
    payload = tree_archive.manifest_bytes(
        tree_archive.admit_archive_stream(io.BytesIO(lock.archive_bytes), tree_archive.CEILING_LIMITS, None)
    )
    monkeypatch.setattr(tree_archive, "MAX_TREE_MANIFEST_BYTES", len(payload) - 1)

    with pytest.raises(RuntimeError, match="archive-size-limit"):
        tree_installation.describe_archive_tree(carrier, lock.selection.raw_manifest[0])
    with pytest.raises(isabelle_tool.IsabelleToolError, match="archive-size-limit"):
        isabelle_tool.acquire_isabelle(tmp_path)

    target = _target(tmp_path, lock)
    assert not target.exists()
    assert not list(target.parent.glob(".stage-*"))
    monkeypatch.setattr(tree_archive, "MAX_TREE_MANIFEST_BYTES", len(payload))
    assert tree_installation.describe_archive_tree(carrier, lock.selection.raw_manifest[0])["manifest_sha256"] == (
        lock.selection.installed_tree.manifest_sha256
    )
