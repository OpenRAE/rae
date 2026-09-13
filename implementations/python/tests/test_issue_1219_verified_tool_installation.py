"""Acceptance tests for issue #1219's verified local installation boundary."""

from __future__ import annotations

import hashlib
import io
import json
import os
import plistlib
import subprocess
import tarfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import bootstrap_profile, gitleaks_tool, osv_scanner_tool, vale_tool
from tools import verified_tool_installation as installation
from tools.policy import conftest_tool

REPO_ROOT = Path(__file__).resolve().parents[3]


def _entry(path: str, payload: bytes, *, executable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        executable=executable,
    )


def _selection(
    payload: bytes = b"reviewed tool",
    *,
    artifact_id: str = "conftest",
    version: str = "0.68.0",
    platform_id: str = "linux-x86_64",
) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_id=artifact_id,
        artifact_class="generic-cli",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
        policy_refs=("artifact-integrity-v1",),
        source_urls=("https://example.invalid/tool.tar.gz",),
        raw_manifest=(_entry("tool.tar.gz", payload, executable=False),),
        installed_manifest=(_entry("bin/tool", payload),),
    )


def _tar(entries: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for member, body in entries:
            archive.addfile(member, io.BytesIO(body) if body is not None else None)
    return payload.getvalue()


@contextmanager
def _unlocked(_path: Path) -> Iterator[None]:
    yield


def _direct_install(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    selection: SimpleNamespace,
    payload: bytes,
    *,
    legacy_path: Path | None = None,
    immutable_seed_root: Path | None = None,
    acquire=None,
) -> Path:
    monkeypatch.setattr(installation, "_portable_lock", _unlocked)
    return installation.ensure_verified_installation(
        repo_root,
        selection,
        acquire=acquire or (lambda: payload),
        materialize=installation.materialize_direct,
        legacy_path=legacy_path,
        immutable_seed_root=immutable_seed_root,
    )


def _make_private_cache_chain(path: Path, stop: Path) -> None:
    current = path
    while current != stop:
        current.chmod(0o700)
        current = current.parent


def test_installation_identity_is_raw_platform_policy_and_manifest_scoped(tmp_path: Path) -> None:
    selection = _selection()

    path = installation.installation_tree_path(tmp_path, selection)

    assert selection.version not in path.parts
    assert selection.platform_id in path.parts
    assert selection.raw_manifest[0].sha256 in path.parts
    assert installation.INSTALLATION_POLICY_ID in path.parts
    assert path.name == installation.installed_manifest_identity(selection.installed_manifest)


@pytest.mark.parametrize(
    "member",
    [
        tarfile.TarInfo("../bin/tool"),
        tarfile.TarInfo("/bin/tool"),
        tarfile.TarInfo("bin/../../tool"),
    ],
)
def test_archive_admission_rejects_traversal_before_selected_member_read(
    member: tarfile.TarInfo,
) -> None:
    member.size = 0
    selection = _selection()

    with pytest.raises(RuntimeError, match="unsafe-archive-member"):
        installation.materialize_tar_gz(_tar([(member, b"")]), selection)


@pytest.mark.parametrize("member_type", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE])
def test_archive_admission_rejects_links_and_special_members(member_type: bytes) -> None:
    member = tarfile.TarInfo("unselected")
    member.type = member_type
    member.linkname = "bin/tool"
    selection = _selection()

    with pytest.raises(RuntimeError, match="unsafe-archive-member"):
        installation.materialize_tar_gz(_tar([(member, None)]), selection)


def test_archive_admission_rejects_duplicate_members() -> None:
    first = tarfile.TarInfo("bin/tool")
    first.size = len(b"reviewed tool")
    duplicate = tarfile.TarInfo("bin/tool")
    duplicate.size = len(b"reviewed tool")
    selection = _selection()

    with pytest.raises(RuntimeError, match="duplicate-archive-member"):
        installation.materialize_tar_gz(
            _tar([(first, b"reviewed tool"), (duplicate, b"reviewed tool")]),
            selection,
        )


def test_archive_admission_rejects_parent_after_descendant() -> None:
    descendant = tarfile.TarInfo("bin/tool")
    descendant.size = len(b"reviewed tool")
    conflicting_parent = tarfile.TarInfo("bin")
    conflicting_parent.size = len(b"xx")

    with pytest.raises(RuntimeError, match="conflicting-archive-member"):
        installation.materialize_tar_gz(
            _tar([(descendant, b"reviewed tool"), (conflicting_parent, b"xx")]),
            _selection(),
        )


def test_archive_admission_rejects_declared_expansion_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = tarfile.TarInfo("bin/tool")
    selected.size = len(b"reviewed tool")
    extra = tarfile.TarInfo("large")
    extra.size = 2
    selection = _selection()
    monkeypatch.setattr(installation, "MAX_ARCHIVE_EXPANDED_BYTES", 1)

    with pytest.raises(RuntimeError, match="archive-size-limit"):
        installation.materialize_tar_gz(_tar([(selected, b"reviewed tool"), (extra, b"xx")]), selection)


def test_publish_is_atomic_private_and_warm_hits_are_revalidated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed tool"
    selection = _selection(payload)
    acquisitions = 0

    def acquire() -> bytes:
        nonlocal acquisitions
        acquisitions += 1
        return payload

    installed = _direct_install(monkeypatch, tmp_path, selection, payload, acquire=acquire)
    assert installed.read_bytes() == payload
    assert installed.stat().st_mode & 0o777 == 0o500
    assert installed.parent.stat().st_mode & 0o777 == 0o500
    assert acquisitions == 1

    assert _direct_install(monkeypatch, tmp_path, selection, payload, acquire=acquire) == installed
    assert acquisitions == 1


def test_acquired_raw_bytes_are_reverified_before_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection()

    with pytest.raises(RuntimeError, match="raw-manifest-mismatch"):
        _direct_install(
            monkeypatch,
            tmp_path,
            selection,
            b"reviewed tool",
            acquire=lambda: b"different raw carrier",
        )


def test_cross_user_writable_installation_root_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_root = installation.default_installation_root(tmp_path)
    install_root.mkdir(parents=True, mode=0o777)
    install_root.chmod(0o777)

    with pytest.raises(RuntimeError, match="unsafe-private-root"):
        _direct_install(monkeypatch, tmp_path, _selection(), b"reviewed tool")


def test_cross_user_writable_repository_ancestor_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outer = tmp_path / "outer"
    repo_root = outer / "repo"
    repo_root.mkdir(parents=True, mode=0o700)
    repo_root.chmod(0o700)
    outer.chmod(0o777)

    with pytest.raises(RuntimeError, match="unsafe-private-root"):
        _direct_install(monkeypatch, repo_root, _selection(), b"reviewed tool")


def test_group_writable_repository_root_rejects_another_principal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    group_id = tmp_path.stat().st_gid
    tmp_path.chmod(0o770)
    monkeypatch.setattr(installation.pwd, "getpwuid", lambda _uid: SimpleNamespace(pw_name="current"))
    monkeypatch.setattr(
        installation.grp,
        "getgrgid",
        lambda _gid: SimpleNamespace(gr_mem=("current", "other")),
    )
    monkeypatch.setattr(
        installation.pwd,
        "getpwall",
        lambda: [SimpleNamespace(pw_name="current", pw_gid=group_id)],
    )

    with pytest.raises(RuntimeError, match="unsafe-private-root"):
        _direct_install(monkeypatch, tmp_path, _selection(), b"reviewed tool")


def test_group_writable_repository_root_allows_the_current_principal_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    group_id = tmp_path.stat().st_gid
    tmp_path.chmod(0o770)
    monkeypatch.setattr(installation.pwd, "getpwuid", lambda _uid: SimpleNamespace(pw_name="current"))
    monkeypatch.setattr(
        installation.grp,
        "getgrgid",
        lambda _gid: SimpleNamespace(gr_mem=("current",)),
    )
    monkeypatch.setattr(
        installation.pwd,
        "getpwall",
        lambda: [SimpleNamespace(pw_name="current", pw_gid=group_id)],
    )

    installed = _direct_install(monkeypatch, tmp_path, _selection(), b"reviewed tool")

    assert installed.read_bytes() == b"reviewed tool"


@pytest.mark.parametrize(
    ("failing_lookup", "error"),
    [("group", KeyError("missing group")), ("passwd", OSError("unavailable passwd database"))],
)
def test_group_membership_lookup_failure_rejects_group_writable_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failing_lookup: str,
    error: Exception,
) -> None:
    group_id = tmp_path.stat().st_gid
    tmp_path.chmod(0o770)
    monkeypatch.setattr(installation.pwd, "getpwuid", lambda _uid: SimpleNamespace(pw_name="current"))
    monkeypatch.setattr(installation.grp, "getgrgid", lambda _gid: SimpleNamespace(gr_mem=("current",)))
    monkeypatch.setattr(
        installation.pwd,
        "getpwall",
        lambda: [SimpleNamespace(pw_name="current", pw_gid=group_id)],
    )

    def fail_lookup(*_args: object) -> None:
        raise error

    if failing_lookup == "group":
        monkeypatch.setattr(installation.grp, "getgrgid", fail_lookup)
    else:
        monkeypatch.setattr(installation.pwd, "getpwall", fail_lookup)

    with pytest.raises(RuntimeError, match="unsafe-private-root"):
        _direct_install(monkeypatch, tmp_path, _selection(), b"reviewed tool")


def test_tampered_cache_is_quarantined_and_terminal_without_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection()
    install_root = installation.default_installation_root(tmp_path)
    tree = installation.installation_tree_path(install_root, selection)
    binary = tree / "bin" / "tool"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"tampered")
    binary.chmod(0o500)
    _make_private_cache_chain(binary.parent, tmp_path)
    tree.chmod(0o500)

    with pytest.raises(RuntimeError, match="cache-integrity-failure"):
        _direct_install(
            monkeypatch,
            tmp_path,
            selection,
            b"reviewed tool",
            acquire=lambda: pytest.fail("integrity failure triggered acquisition"),
        )

    assert not tree.exists()
    quarantined = list((install_root / "conftest" / ".quarantine").glob("*"))
    assert len(quarantined) == 1


def test_invalid_observer_revalidates_a_concurrent_repair_under_the_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed tool"
    selection = _selection(payload)
    install_root = installation.default_installation_root(tmp_path)
    tree = installation.installation_tree_path(install_root, selection)
    binary = tree / "bin" / "tool"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"tampered")
    binary.chmod(0o500)
    _make_private_cache_chain(binary.parent, tmp_path)
    tree.chmod(0o500)
    observer_waiting = threading.Event()
    repair_published = threading.Event()
    observer_result: list[Path | BaseException] = []

    @contextmanager
    def coordinated_lock(_path: Path) -> Iterator[None]:
        if threading.current_thread().name == "invalid-observer":
            observer_waiting.set()
            assert repair_published.wait(10)
        yield

    monkeypatch.setattr(installation, "_portable_lock", coordinated_lock)

    def ensure() -> Path:
        return installation.ensure_verified_installation(
            tmp_path,
            selection,
            acquire=lambda: payload,
            materialize=installation.materialize_direct,
        )

    def observe() -> None:
        try:
            observer_result.append(ensure())
        except BaseException as exc:  # noqa: BLE001 - the assertion must retain the thread failure.
            observer_result.append(exc)

    observer = threading.Thread(target=observe, name="invalid-observer")
    observer.start()
    assert observer_waiting.wait(10)
    with pytest.raises(RuntimeError, match="cache-integrity-failure"):
        ensure()
    repaired = ensure()
    repair_published.set()
    observer.join(10)

    assert not observer.is_alive()
    assert observer_result == [repaired]
    assert repaired.read_bytes() == payload
    assert len(list((install_root / "conftest" / ".quarantine").glob("cache-*"))) == 1


@pytest.mark.parametrize("valid", [True, False])
def test_legacy_version_cache_moves_to_quarantine_before_reverification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid: bool,
) -> None:
    payload = b"reviewed tool"
    selection = _selection(payload)
    legacy = tmp_path / ".cache" / "raes-sdl" / "tooling" / "conftest" / "0.68.0" / "conftest"
    legacy.parent.mkdir(parents=True)
    _make_private_cache_chain(legacy.parent, tmp_path)
    legacy.write_bytes(payload if valid else b"tampered")
    legacy.chmod(0o755)

    if valid:
        installed = _direct_install(
            monkeypatch,
            tmp_path,
            selection,
            payload,
            legacy_path=legacy,
            acquire=lambda: pytest.fail("valid legacy content triggered acquisition"),
        )
        assert installed.read_bytes() == payload
    else:
        with pytest.raises(RuntimeError, match="legacy-integrity-failure"):
            _direct_install(
                monkeypatch,
                tmp_path,
                selection,
                payload,
                legacy_path=legacy,
                acquire=lambda: pytest.fail("invalid legacy content triggered acquisition"),
            )
    assert not legacy.exists()
    quarantine = installation.default_installation_root(tmp_path) / "conftest" / ".quarantine"
    quarantined_files = [path for path in quarantine.rglob("*") if path.is_file()]
    assert len(quarantined_files) == 1
    assert quarantined_files[0].stat().st_mode & 0o111 == 0


def test_immutable_seed_is_reverified_and_copied_into_private_job_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed tool"
    selection = _selection(payload)
    seed_root = tmp_path / "seed"
    seed_tree = installation.installation_tree_path(seed_root, selection)
    seed_binary = seed_tree / "bin" / "tool"
    seed_binary.parent.mkdir(parents=True)
    seed_binary.write_bytes(payload)
    seed_binary.chmod(0o555)
    for directory in (seed_binary.parent, seed_tree, *seed_tree.parents):
        if directory == tmp_path.parent:
            break
        if directory.exists() and directory != tmp_path:
            directory.chmod(0o555)

    job_root = tmp_path / "job"
    job_root.mkdir()
    job_root.chmod(0o700)
    installed = _direct_install(
        monkeypatch,
        job_root,
        selection,
        payload,
        immutable_seed_root=seed_root,
        acquire=lambda: pytest.fail("valid immutable seed triggered acquisition"),
    )

    assert installed.read_bytes() == payload
    assert installed != seed_binary
    assert installed.stat().st_mode & 0o777 == 0o500
    assert seed_binary.read_bytes() == payload


def test_writable_seed_is_rejected_without_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"reviewed tool"
    selection = _selection(payload)
    seed_root = tmp_path / "seed"
    seed_tree = installation.installation_tree_path(seed_root, selection)
    seed_binary = seed_tree / "bin" / "tool"
    seed_binary.parent.mkdir(parents=True)
    seed_binary.write_bytes(payload)
    seed_binary.chmod(0o755)

    job_root = tmp_path / "job"
    job_root.mkdir()
    job_root.chmod(0o700)
    with pytest.raises(RuntimeError, match="seed-integrity-failure"):
        _direct_install(
            monkeypatch,
            job_root,
            selection,
            payload,
            immutable_seed_root=seed_root,
            acquire=lambda: pytest.fail("writable seed triggered acquisition"),
        )


def test_unqualified_shared_filesystem_is_rejected_before_cache_or_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection()
    monkeypatch.setattr(installation, "_filesystem_type", lambda _path: "nfs4")

    with pytest.raises(RuntimeError, match="unsupported-filesystem"):
        _direct_install(
            monkeypatch,
            tmp_path,
            selection,
            b"reviewed tool",
            acquire=lambda: pytest.fail("unqualified filesystem triggered acquisition"),
        )


def test_darwin_filesystem_qualification_reads_diskutil_plist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[list[str]] = []
    monkeypatch.setattr(installation.platform, "system", lambda: "Darwin")

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(stdout=plistlib.dumps({"FilesystemType": "apfs"}))

    monkeypatch.setattr(installation.subprocess, "run", run)

    installation._require_qualified_filesystem(tmp_path)

    assert observed == [["/usr/sbin/diskutil", "info", "-plist", str(tmp_path.resolve())]]


@pytest.mark.parametrize(
    "payload",
    [b"not a plist", plistlib.dumps({"FilesystemName": "APFS"})],
)
def test_darwin_filesystem_qualification_fails_closed_on_invalid_diskutil_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: bytes,
) -> None:
    monkeypatch.setattr(installation.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        installation.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=payload),
    )

    with pytest.raises(RuntimeError, match="unsupported-filesystem"):
        installation._require_qualified_filesystem(tmp_path)


def test_hardlinked_installed_leaf_is_quarantined_and_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection()
    tree = installation.installation_tree_path(installation.default_installation_root(tmp_path), selection)
    binary = tree / "bin" / "tool"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"reviewed tool")
    binary.chmod(0o500)
    _make_private_cache_chain(binary.parent, tmp_path)
    alias = tmp_path / "alias"
    os.link(binary, alias)
    tree.chmod(0o500)

    with pytest.raises(RuntimeError, match="cache-integrity-failure"):
        _direct_install(monkeypatch, tmp_path, selection, b"reviewed tool")

    assert alias.read_bytes() == b"reviewed tool"
    assert not tree.exists()


@pytest.mark.parametrize(
    ("module", "ensure", "artifact_id", "version", "legacy_name", "materializer"),
    [
        (conftest_tool, conftest_tool.ensure_conftest, "conftest", "0.68.0", "conftest", "materialize_tar_gz"),
        (gitleaks_tool, gitleaks_tool.ensure_gitleaks, "gitleaks", "8.30.1", "gitleaks", "materialize_tar_gz"),
        (vale_tool, vale_tool.ensure_vale, "vale", "3.15.2", "vale", "materialize_tar_gz"),
        (
            osv_scanner_tool,
            osv_scanner_tool.ensure_osv_scanner,
            "osv-scanner",
            "2.4.0",
            "osv-scanner",
            "materialize_direct",
        ),
    ],
)
def test_all_four_wrappers_delegate_to_the_shared_installation_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module: object,
    ensure,
    artifact_id: str,
    version: str,
    legacy_name: str,
    materializer: str,
) -> None:
    selection = _selection(artifact_id=artifact_id, version=version)
    installed = tmp_path / "private" / legacy_name
    observed: dict[str, object] = {}
    local_input = tmp_path / "carrier"

    monkeypatch.setattr("tools.tooling_policy_gate.host_platform_id", lambda: "linux-x86_64")
    monkeypatch.setattr("tools.tooling_policy_gate.load_tooling_artifact_selection", lambda **_kwargs: selection)

    def acquire_locked_bytes(**kwargs: object) -> bytes:
        observed["acquisition"] = kwargs
        return b"raw"

    monkeypatch.setattr(module, "acquire_locked_bytes", acquire_locked_bytes)

    def ensure_verified_installation(repo_root: Path, selected: object, **kwargs: object) -> Path:
        observed.update({"repo_root": repo_root, "selection": selected, **kwargs})
        return installed

    monkeypatch.setattr(installation, "ensure_verified_installation", ensure_verified_installation)

    assert (
        ensure(
            tmp_path,
            version=version,
            local_input=local_input,
            installation_root=tmp_path / "private",
            immutable_seed_root=tmp_path / "seed",
        )
        == installed
    )
    assert observed["repo_root"] == tmp_path
    assert observed["selection"] is selection
    assert observed["legacy_path"] == (
        tmp_path / ".cache" / "raes-sdl" / "tooling" / artifact_id / version / legacy_name
    )
    assert observed["installation_root"] == tmp_path / "private"
    assert observed["immutable_seed_root"] == tmp_path / "seed"
    assert observed["materialize"] is getattr(installation, materializer)
    assert observed["acquire"]() == b"raw"
    assert observed["acquisition"]["local_input"] == local_input


@pytest.mark.integration
def test_real_portable_lock_and_crash_qualification(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT / "implementations" / "tooling" / "python"),
            "--frozen",
            "--no-default-groups",
            "python",
            str(Path(__file__).with_name("issue_1219_installation_harness.py")),
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert completed.returncode == 0, completed.stderr
    evidence = json.loads(completed.stdout)
    assert evidence["schema"] == "issue-1219-local-installation-qualification/v1"
    assert evidence["installation_policy"] == installation.INSTALLATION_POLICY_ID
    assert evidence["cold_processes"] == 32
    assert evidence["warm_clients"] == 100
    assert evidence["coverage"] == {
        "scope": "generic-cli-installation-mechanism",
        "fixture": "synthetic-direct-carrier",
        "canonical_cases": {
            "T05": "local-cli-process-and-crash-slice-only",
            "T06": "local-owner-and-hostile-filesystem-slice-only",
            "T07": "local-cli-client-and-storage-failure-slice-only",
            "T16": "local-install-read-and-promotion-slice-only",
        },
        "canonical_outcome_recorded": False,
    }
    assert evidence["crash_checkpoints"] == [
        "staged-written",
        "staged-durable",
        "published",
        "parent-durable",
    ]
    assert set(evidence["passed_cases"]) == {
        "bounded-lock-timeout",
        "cold-convergence",
        "crash-recovery",
        "live-publisher-exclusion",
        "quota-failure-recovery",
        "unsafe-lock-rejection",
        "warm-validation",
    }


def test_partial_harness_cannot_be_recorded_as_complete_canonical_cases() -> None:
    schema = json.loads(
        (REPO_ROOT / "implementations" / "tooling" / "schemas" / "profiles.schema.json").read_text(encoding="utf-8")
    )
    qualification_ids = set(schema["$defs"]["qualificationRecord"]["properties"]["test_case_ids"]["items"]["enum"])
    case_ids = set(schema["$defs"]["caseResult"]["properties"]["test_case_id"]["enum"])

    assert not {"T05", "T06", "T07", "T16"} & bootstrap_profile._CASE_IDS
    assert not {"T05", "T06", "T07", "T16"} & qualification_ids
    assert qualification_ids == case_ids


def test_bootstrap_qualification_retains_local_evidence_without_overclaiming() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "bootstrap-qualification.yml").read_text(encoding="utf-8")

    assert "issue_1219_installation_harness.py" in workflow
    assert "local-installation-qualification.json" in workflow
    for case_id in ("T05", "T06", "T07", "T16"):
        assert f"record-case {case_id}" not in workflow
