"""Verified, concurrent-safe local installation for reviewed development tools."""

from __future__ import annotations

import errno
import grp
import hashlib
import io
import json
import logging
import os
import platform
import pwd
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path, PurePosixPath
from typing import Protocol

INSTALLATION_POLICY_ID = "install-v1"
MAX_ARCHIVE_MEMBERS = 1024
MAX_ARCHIVE_PATH_BYTES = 1024
MAX_ARCHIVE_PATH_DEPTH = 16
MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 120
_QUALIFIED_FILESYSTEMS = frozenset(
    {
        "apfs",
        "btrfs",
        "ext2",
        "ext3",
        "ext4",
        "hfs",
        "hfsplus",
        "overlay",
        "tmpfs",
        "xfs",
        "zfs",
    }
)


class ManifestEntry(Protocol):
    path: str
    sha256: str
    size: int
    executable: bool


class ArtifactSelection(Protocol):
    artifact_id: str
    platform_id: str
    policy_refs: tuple[str, ...]
    raw_manifest: tuple[ManifestEntry, ...]
    installed_manifest: tuple[ManifestEntry, ...]


def _portable_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
        or len(value.encode("utf-8")) > MAX_ARCHIVE_PATH_BYTES
        or len(path.parts) > MAX_ARCHIVE_PATH_DEPTH
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError("tool-installation: unsafe-archive-member")
    return path


def installed_manifest_identity(entries: Iterable[ManifestEntry]) -> str:
    """Return the canonical installed-tree identity selected by the lock."""

    payload = sorted(
        (
            {
                "executable": entry.executable,
                "path": _portable_path(entry.path).as_posix(),
                "sha256": entry.sha256,
                "size": entry.size,
            }
            for entry in entries
        ),
        key=lambda entry: entry["path"],
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def default_installation_root(repo_root: Path) -> Path:
    """Return the explicit per-checkout private installation namespace."""

    return repo_root / ".cache" / "raes-sdl" / "tooling" / "installations"


def _safe_component(value: str) -> str:
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value) is None:
        raise RuntimeError("tool-installation: invalid-selection")
    return value


def _policy_identity(selection: ArtifactSelection) -> str:
    encoded = json.dumps(
        {
            "installation_policy": INSTALLATION_POLICY_ID,
            "policy_refs": list(selection.policy_refs),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def installation_tree_path(installation_root: Path, selection: ArtifactSelection) -> Path:  # NOSONAR
    """Return the content-addressed tree path for a validated selection."""

    manifests = (*selection.raw_manifest, *selection.installed_manifest)
    installed_paths = [entry.path for entry in selection.installed_manifest]
    if (
        len(selection.raw_manifest) != 1
        or not selection.installed_manifest
        or len(installed_paths) != len(set(installed_paths))
        or sum(entry.executable is True for entry in selection.installed_manifest) != 1
        or not selection.policy_refs
        or not all(isinstance(reference, str) and reference for reference in selection.policy_refs)
        or any(
            not isinstance(entry.path, str)
            or not isinstance(entry.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", entry.sha256) is None
            or not isinstance(entry.size, int)
            or isinstance(entry.size, bool)
            or entry.size < 1
            or entry.size > MAX_ARCHIVE_EXPANDED_BYTES
            or not isinstance(entry.executable, bool)
            for entry in manifests
        )
    ):
        raise RuntimeError("tool-installation: invalid-selection")
    for entry in manifests:
        _portable_path(entry.path)
    return (
        installation_root
        / _safe_component(selection.artifact_id)
        / _safe_component(selection.platform_id)
        / selection.raw_manifest[0].sha256
        / INSTALLATION_POLICY_ID
        / _policy_identity(selection)
        / installed_manifest_identity(selection.installed_manifest)
    )


def _executable_entry(selection: ArtifactSelection) -> ManifestEntry:
    return next(entry for entry in selection.installed_manifest if entry.executable)


def _validate_archive_shape(members: list[tarfile.TarInfo]) -> None:  # NOSONAR -- explicit archive limits fail closed.
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise RuntimeError("tool-installation: archive-member-limit")
    seen: set[PurePosixPath] = set()
    files: set[PurePosixPath] = set()
    total = 0
    for member in members:
        path = _portable_path(member.name)
        if path in seen:
            raise RuntimeError("tool-installation: duplicate-archive-member")
        if any(parent in files for parent in path.parents) or any(path in existing.parents for existing in seen):
            raise RuntimeError("tool-installation: conflicting-archive-member")
        if not (member.isfile() or member.isdir()) or getattr(member, "sparse", None):
            raise RuntimeError("tool-installation: unsafe-archive-member")
        if member.size < 0 or member.size > MAX_ARCHIVE_MEMBER_BYTES:
            raise RuntimeError("tool-installation: archive-size-limit")
        total += member.size
        if total > MAX_ARCHIVE_EXPANDED_BYTES:
            raise RuntimeError("tool-installation: archive-size-limit")
        if member.isfile():
            files.add(path)
        seen.add(path)


def _validate_materialized(
    materialized: Mapping[str, bytes],
    installed_manifest: tuple[ManifestEntry, ...],
) -> dict[str, bytes]:
    expected_paths = {entry.path for entry in installed_manifest}
    if set(materialized) != expected_paths or len(expected_paths) != len(installed_manifest):
        raise RuntimeError("tool-installation: installed-manifest-mismatch")  # NOSONAR -- stable reason code.
    result: dict[str, bytes] = {}
    for entry in installed_manifest:
        payload = materialized[entry.path]
        if len(payload) != entry.size or hashlib.sha256(payload).hexdigest() != entry.sha256:
            raise RuntimeError("tool-installation: installed-manifest-mismatch")
        result[entry.path] = payload
    return result


def materialize_tar_gz(raw_bytes: bytes, selection: ArtifactSelection) -> dict[str, bytes]:
    """Admit a bounded tar.gz carrier and return exactly the installed manifest."""

    try:
        with tarfile.open(fileobj=io.BytesIO(raw_bytes), mode="r:gz") as archive:
            members = archive.getmembers()
            _validate_archive_shape(members)
            by_path = {member.name: member for member in members}
            materialized: dict[str, bytes] = {}
            for entry in selection.installed_manifest:
                member = by_path.get(entry.path)
                if member is None or not member.isfile():
                    raise RuntimeError("tool-installation: installed-manifest-mismatch")
                stream = archive.extractfile(member)
                if stream is None:
                    raise RuntimeError("tool-installation: installed-manifest-mismatch")
                materialized[entry.path] = stream.read(entry.size + 1)
    except RuntimeError:
        raise
    except (OSError, tarfile.TarError, UnicodeError) as exc:
        raise RuntimeError("tool-installation: unsafe-archive") from exc
    return _validate_materialized(materialized, selection.installed_manifest)


def materialize_direct(raw_bytes: bytes, selection: ArtifactSelection) -> dict[str, bytes]:
    """Admit a direct-file carrier against the installed manifest."""

    if len(selection.installed_manifest) != 1:
        raise RuntimeError("tool-installation: installed-manifest-mismatch")
    entry = selection.installed_manifest[0]
    return _validate_materialized({entry.path: raw_bytes}, selection.installed_manifest)


def _validate_raw_bytes(raw_bytes: object, selection: ArtifactSelection) -> bytes:
    if len(selection.raw_manifest) != 1 or not isinstance(raw_bytes, bytes):
        raise RuntimeError("tool-installation: raw-manifest-mismatch")
    entry = selection.raw_manifest[0]
    if len(raw_bytes) != entry.size or hashlib.sha256(raw_bytes).hexdigest() != entry.sha256:
        raise RuntimeError("tool-installation: raw-manifest-mismatch")
    return raw_bytes


def _decode_mount_path(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def _filesystem_type(path: Path) -> str:  # NOSONAR -- Linux and Darwin parsers deliberately fail closed.
    """Return a stable local filesystem type without consulting ambient config."""

    existing = path
    while not existing.exists():
        if existing == existing.parent:
            raise RuntimeError("tool-installation: unsupported-filesystem")  # NOSONAR -- stable reason code.
        existing = existing.parent
    canonical = existing.resolve()
    if platform.system() == "Linux":
        try:
            lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("tool-installation: unsupported-filesystem") from exc
        candidates: list[tuple[int, str]] = []
        for line in lines:
            before, separator, after = line.partition(" - ")
            fields = before.split()
            trailing = after.split()
            if not separator or len(fields) < 5 or not trailing:
                continue
            mount = Path(_decode_mount_path(fields[4]))
            try:
                canonical.relative_to(mount)
            except ValueError:
                continue
            candidates.append((len(mount.parts), trailing[0]))
        if candidates:
            return max(candidates)[1].lower()
        raise RuntimeError("tool-installation: unsupported-filesystem")
    if platform.system() == "Darwin":
        try:
            completed = subprocess.run(
                ["/sbin/mount"],
                check=True,
                capture_output=True,
                env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                text=True,
                timeout=10,
            )
            if not isinstance(completed.stdout, str) or len(completed.stdout.encode("utf-8")) > 1024 * 1024:
                raise ValueError("mount response exceeds the admission bound")
            candidates = []
            for line in completed.stdout.splitlines():
                _device, on_separator, mounted = line.partition(" on ")
                mount_value, options_separator, options = mounted.rpartition(" (")
                if not on_separator or not options_separator or not options.endswith(")"):
                    continue
                filesystem_type = options[:-1].partition(",")[0].strip()
                if not filesystem_type:
                    continue
                mount = Path(_decode_mount_path(mount_value))
                try:
                    canonical.relative_to(mount)
                except ValueError:
                    continue
                candidates.append((len(mount.parts), filesystem_type))
            if not candidates:
                raise ValueError("mount response has no matching filesystem")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise RuntimeError("tool-installation: unsupported-filesystem") from exc
        return max(candidates)[1].lower()
    raise RuntimeError("tool-installation: unsupported-filesystem")


def _require_qualified_filesystem(path: Path) -> None:
    if _filesystem_type(path) not in _QUALIFIED_FILESYSTEMS:
        raise RuntimeError("tool-installation: unsupported-filesystem")


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _group_has_other_principal(group_id: int) -> bool:
    """Return whether a writable group grants access to another OS principal."""

    try:
        current_uid = os.geteuid()
        current_name = pwd.getpwuid(current_uid).pw_name
        explicit_members = set(grp.getgrgid(group_id).gr_mem)
        primary_members = {entry.pw_name for entry in pwd.getpwall() if entry.pw_gid == group_id}
    except (KeyError, OSError):
        return True
    return bool((explicit_members | primary_members) - {current_name})


def _cross_principal_writable(state: os.stat_result) -> bool:
    return bool(state.st_mode & 0o002) or bool(state.st_mode & 0o020 and _group_has_other_principal(state.st_gid))


def _assert_private_directory_state(state: os.stat_result, *, exact_mode: int | None = None) -> None:
    if not stat.S_ISDIR(state.st_mode) or state.st_uid != os.geteuid() or _cross_principal_writable(state):
        raise RuntimeError("tool-installation: unsafe-private-root")  # NOSONAR -- stable reason code.
    if exact_mode is not None and state.st_mode & 0o777 != exact_mode:
        raise RuntimeError("tool-installation: unsafe-private-root")


def _assert_private_directory(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    state = path.lstat()
    if stat.S_ISLNK(state.st_mode):
        raise RuntimeError("tool-installation: unsafe-private-root")
    _assert_private_directory_state(state, exact_mode=exact_mode)
    return state


def _assert_trusted_anchor_chain(repo_root: Path) -> Path:
    anchor = repo_root.absolute()
    current = anchor
    while True:
        state = current.lstat()
        if stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode):
            raise RuntimeError("tool-installation: unsafe-private-root")
        writable_by_other_principal = _cross_principal_writable(state)
        sticky_parent = current != anchor and bool(state.st_mode & stat.S_ISVTX)
        if writable_by_other_principal and not sticky_parent:
            raise RuntimeError("tool-installation: unsafe-private-root")
        if current == current.parent:
            break
        current = current.parent
    _assert_private_directory(anchor)
    return anchor


def _directory_open_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


@contextmanager
def _private_root_guard(repo_root: Path, path: Path) -> Iterator[None]:  # NOSONAR
    """Hold no-follow descriptors for the trusted namespace during installation."""

    anchor = _assert_trusted_anchor_chain(repo_root)
    try:
        parts = path.relative_to(repo_root).parts
    except ValueError as exc:
        raise RuntimeError("tool-installation: unsafe-private-root") from exc
    descriptors: list[tuple[int, Path]] = []
    try:
        descriptor = os.open(anchor, _directory_open_flags())
        descriptors.append((descriptor, anchor))
        if not os.path.samestat(os.fstat(descriptor), anchor.lstat()):
            raise RuntimeError("tool-installation: unsafe-private-root")
        current = anchor
        for part in parts:
            with suppress(FileExistsError):
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            child = os.open(part, _directory_open_flags(), dir_fd=descriptor)
            current /= part
            child_state = os.fstat(child)
            _assert_private_directory_state(child_state, exact_mode=0o700 if current == path else None)
            if not os.path.samestat(child_state, current.lstat()):
                os.close(child)
                raise RuntimeError("tool-installation: unsafe-private-root")
            descriptors.append((child, current))
            descriptor = child
    except OSError as exc:
        for descriptor, _held_path in reversed(descriptors):
            os.close(descriptor)
        raise RuntimeError("tool-installation: unsafe-private-root") from exc
    except BaseException:
        for descriptor, _held_path in reversed(descriptors):
            os.close(descriptor)
        raise
    try:
        yield
        for held, held_path in descriptors:
            if not os.path.samestat(os.fstat(held), held_path.lstat()):
                raise RuntimeError("tool-installation: unsafe-private-root")
    finally:
        for descriptor, _held_path in reversed(descriptors):
            os.close(descriptor)


def _ensure_private_subdirectory(path: Path, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("tool-installation: unsafe-private-root") from exc
    current = root
    _assert_private_directory(current, exact_mode=0o700)
    for part in relative.parts:
        current /= part
        with suppress(FileExistsError):
            current.mkdir(mode=0o700)
        _assert_private_directory(current, exact_mode=0o700)


def _fsync_directory(path: Path) -> None:
    if platform.system() == "Darwin":
        try:
            subprocess.run(
                ["/bin/sync"],
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError(errno.EIO, "directory synchronization failed") from exc
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_verified_file(  # NOSONAR -- paired before/open/after checks resist substitution races.
    path: Path,
    entry: ManifestEntry,
    *,
    mode: str,
) -> bytes:
    before = path.lstat()
    permissions = before.st_mode & 0o777
    expected_mode = 0o500 if entry.executable else 0o400
    owner_ok = before.st_uid == os.geteuid()
    if mode == "seed":
        owner_ok = before.st_uid in {0, os.geteuid()}
        mode_ok = not permissions & 0o222 and (not entry.executable or bool(permissions & 0o111))
    elif mode == "legacy":
        # Version-keyed caches were created under the user's umask; a group
        # write bit is a risk only when that group admits another principal.
        mode_ok = not _cross_principal_writable(before) and (not entry.executable or bool(permissions & 0o100))
    elif mode == "staged":
        mode_ok = permissions == 0o600
    else:
        mode_ok = permissions == expected_mode
    if (
        not owner_ok
        or not mode_ok
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size != entry.size
    ):
        raise RuntimeError("tool-installation: file-integrity-failure")  # NOSONAR -- stable reason code.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    payload = bytearray()
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise RuntimeError("tool-installation: file-integrity-failure")
        while chunk := stream.read(min(1024 * 1024, entry.size + 1 - len(payload))):
            payload.extend(chunk)
            digest.update(chunk)
            if len(payload) > entry.size:
                raise RuntimeError("tool-installation: file-integrity-failure")
    after = path.lstat()
    if (
        len(payload) != entry.size
        or digest.hexdigest() != entry.sha256
        or not os.path.samestat(opened, after)
        or not stat.S_ISREG(after.st_mode)
    ):
        raise RuntimeError("tool-installation: file-integrity-failure")
    return bytes(payload)


def _expected_directories(entries: tuple[ManifestEntry, ...]) -> set[str]:
    result = {"."}
    for entry in entries:
        path = _portable_path(entry.path)
        result.update(parent.as_posix() for parent in path.parents if parent.as_posix() != ".")
    return result


def _validate_tree(  # NOSONAR -- the full tree shape and every leaf are checked explicitly.
    tree: Path,
    entries: tuple[ManifestEntry, ...],
    *,
    mode: str,
) -> dict[str, bytes]:
    state = tree.lstat()
    if not stat.S_ISDIR(state.st_mode) or tree.is_symlink():
        raise RuntimeError("tool-installation: tree-integrity-failure")  # NOSONAR -- stable reason code.
    permissions = state.st_mode & 0o777
    valid_owners = {0, os.geteuid()} if mode == "seed" else {os.geteuid()}
    if state.st_uid not in valid_owners or (mode == "seed" and permissions & 0o222):
        raise RuntimeError("tool-installation: tree-integrity-failure")
    if mode == "installed" and permissions != 0o500:
        raise RuntimeError("tool-installation: tree-integrity-failure")
    if mode == "staged" and permissions != 0o700:
        raise RuntimeError("tool-installation: tree-integrity-failure")
    actual_files: set[str] = set()
    actual_directories = {"."}
    for current, directories, files in os.walk(tree, followlinks=False):
        current_path = Path(current)
        for name in directories:
            child = current_path / name
            child_state = child.lstat()
            if child.is_symlink() or not stat.S_ISDIR(child_state.st_mode):
                raise RuntimeError("tool-installation: tree-integrity-failure")
            child_permissions = child_state.st_mode & 0o777
            if child_state.st_uid not in valid_owners:
                raise RuntimeError("tool-installation: tree-integrity-failure")
            if mode == "installed" and child_permissions != 0o500:
                raise RuntimeError("tool-installation: tree-integrity-failure")
            if mode == "staged" and child_permissions != 0o700:
                raise RuntimeError("tool-installation: tree-integrity-failure")
            if mode == "seed" and child_permissions & 0o222:
                raise RuntimeError("tool-installation: tree-integrity-failure")
            actual_directories.add(child.relative_to(tree).as_posix())
        actual_files.update((current_path / name).relative_to(tree).as_posix() for name in files)
    expected_files = {entry.path for entry in entries}
    if actual_files != expected_files or actual_directories != _expected_directories(entries):
        raise RuntimeError("tool-installation: tree-integrity-failure")
    return {entry.path: _read_verified_file(tree / entry.path, entry, mode=mode) for entry in entries}


def _make_quarantine_non_executable(path: Path) -> None:  # NOSONAR -- every file type fails non-executable.
    state = _lstat(path)
    if state is None or path.is_symlink():
        return
    if path.is_dir():
        for current, directories, files in os.walk(path, topdown=False, followlinks=False):
            current_path = Path(current)
            for name in files:
                child = current_path / name
                if not child.is_symlink():
                    child.chmod(0o600)
            for name in directories:
                child = current_path / name
                if not child.is_symlink():
                    child.chmod(0o700)
            current_path.chmod(0o700)
    elif stat.S_ISREG(state.st_mode):
        path.chmod(0o600)


def _quarantine(path: Path, quarantine_root: Path, *, prefix: str) -> Path:
    _assert_private_directory(quarantine_root, exact_mode=0o700)
    destination = quarantine_root / f"{prefix}-{uuid.uuid4().hex}"
    state = path.lstat()
    if stat.S_ISDIR(state.st_mode) and not path.is_symlink() and state.st_uid == os.geteuid():
        path.chmod(0o700)
    os.replace(path, destination)
    _make_quarantine_non_executable(destination)
    _fsync_directory(path.parent)
    _fsync_directory(quarantine_root)
    return destination


def _private_lock_state(state: os.stat_result, *, exact_mode: bool) -> bool:
    permissions_private = state.st_mode & 0o777 == 0o600 if exact_mode else state.st_mode & 0o177 == 0
    return stat.S_ISREG(state.st_mode) and state.st_uid == os.geteuid() and state.st_nlink == 1 and permissions_private


@contextmanager
def _portable_lock(path: Path, timeout: float | None = None) -> Iterator[None]:
    try:
        from filelock import FileLock, Timeout
    except ImportError:
        raise RuntimeError("tool-installation: portable-lock-unavailable") from None
    logging.getLogger("filelock").setLevel(logging.WARNING)
    existing = _lstat(path)
    if existing is not None and not _private_lock_state(existing, exact_mode=False):
        raise RuntimeError("tool-installation: unsafe-lock-file")
    wait_seconds = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    lock = FileLock(path, timeout=wait_seconds, mode=0o600, fallback_to_soft=False, preserve_lock_file=True)
    try:
        with lock:
            if not _private_lock_state(path.lstat(), exact_mode=True):
                raise RuntimeError("tool-installation: unsafe-lock-file")
            yield
    except Timeout:
        raise RuntimeError("tool-installation: lock-timeout") from None


def _tree_present(path: Path) -> bool:
    return _lstat(path) is not None


def _validated_installed_executable(target: Path, selection: ArtifactSelection) -> Path:
    _validate_tree(target, selection.installed_manifest, mode="installed")
    _fsync_directory(target.parent)
    return target / _executable_entry(selection).path


def _clean_staging(parent: Path, tree_name: str) -> None:
    for child in parent.glob(f".stage-{tree_name}-*"):
        if child.is_symlink() or not child.is_dir():
            child.unlink(missing_ok=True)
        else:
            _make_quarantine_non_executable(child)
            shutil.rmtree(child)
    _fsync_directory(parent)


def _write_file(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publication_checkpoint(_name: str, _path: Path) -> None:
    """Test seam for crash injection at durable publication boundaries."""


def _directory_rename_requires_writable_source() -> bool:
    """Return whether the host refuses to rename a directory without owner write (APFS)."""

    return platform.system() == "Darwin"


def _seal_staged_root(stage: Path) -> None:
    """Seal the staged root before publication wherever the host can still rename it."""

    if not _directory_rename_requires_writable_source():
        stage.chmod(0o500)
    _fsync_directory(stage)


def _publish_staged_root(stage: Path, target: Path) -> None:
    """Atomically publish a staged root; only APFS must seal it after the rename."""

    os.rename(stage, target)
    if _directory_rename_requires_writable_source():
        _publication_checkpoint("renamed-unsealed", target)
        target.chmod(0o500)
    _fsync_directory(target)


def _complete_interrupted_seal(target: Path) -> None:
    """Finish an APFS publication interrupted between its rename and root seal.

    Callers hold the identity lock, so no live publisher can own this state;
    every other property of the tree is still validated afterward.
    """

    if not _directory_rename_requires_writable_source():
        return
    state = target.lstat()
    if stat.S_ISDIR(state.st_mode) and state.st_uid == os.geteuid() and state.st_mode & 0o777 == 0o700:
        target.chmod(0o500)
        _fsync_directory(target)


def _publish_tree(
    target: Path,
    entries: tuple[ManifestEntry, ...],
    materialized: Mapping[str, bytes],
) -> None:
    stage = Path(tempfile.mkdtemp(prefix=f".stage-{target.name}-", dir=target.parent))
    stage.chmod(0o700)
    try:
        for entry in entries:
            relative = _portable_path(entry.path)
            parent = stage.joinpath(*relative.parts[:-1])
            current = stage
            for part in relative.parts[:-1]:
                current /= part
                with suppress(FileExistsError):
                    current.mkdir(mode=0o700)
            _write_file(parent / relative.name, materialized[entry.path])
        _publication_checkpoint("staged-written", stage)
        _validate_tree(stage, entries, mode="staged")
        for entry in entries:
            file_path = stage / entry.path
            file_path.chmod(0o500 if entry.executable else 0o400)
            descriptor = os.open(file_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        directories = sorted(
            [path for path in stage.rglob("*") if path.is_dir() and not path.is_symlink()],
            key=lambda value: len(value.parts),
            reverse=True,
        )
        for directory in directories:
            directory.chmod(0o500)
            _fsync_directory(directory)
        _seal_staged_root(stage)
        _publication_checkpoint("staged-durable", stage)
        _publish_staged_root(stage, target)
        _publication_checkpoint("published", target)
        _fsync_directory(target.parent)
        _publication_checkpoint("parent-durable", target)
        _validate_tree(target, entries, mode="installed")
    finally:
        if _tree_present(stage):
            _make_quarantine_non_executable(stage)
            shutil.rmtree(stage)


def _legacy_carrier(
    legacy_path: Path,
    selection: ArtifactSelection,
    quarantine_root: Path,
) -> dict[str, bytes] | None:
    if not _tree_present(legacy_path):
        return None
    if len(selection.installed_manifest) != 1:
        raise RuntimeError("tool-installation: legacy-integrity-failure")
    container = quarantine_root / f"legacy-{uuid.uuid4().hex}"
    container.mkdir(mode=0o700)
    moved = container / legacy_path.name
    os.replace(legacy_path, moved)
    _fsync_directory(legacy_path.parent)
    _fsync_directory(container)
    try:
        payload = _read_verified_file(moved, selection.installed_manifest[0], mode="legacy")
    except (OSError, RuntimeError):
        _make_quarantine_non_executable(container)
        raise RuntimeError("tool-installation: legacy-integrity-failure") from None
    _make_quarantine_non_executable(container)
    _fsync_directory(container)
    return {selection.installed_manifest[0].path: payload}


def _assert_immutable_seed_chain(seed_root: Path, seed_tree: Path) -> None:
    try:
        relative = seed_tree.relative_to(seed_root)
    except ValueError as exc:
        raise RuntimeError("tool-installation: seed-integrity-failure") from exc  # NOSONAR -- stable reason code.
    current = seed_root
    for part in ("", *relative.parts):
        if part:
            current /= part
        state = current.lstat()
        if (
            current.is_symlink()
            or not stat.S_ISDIR(state.st_mode)
            or state.st_uid not in {0, os.geteuid()}
            or state.st_mode & 0o222
        ):
            raise RuntimeError("tool-installation: seed-integrity-failure")


def _validated_existing_or_quarantine(
    target: Path,
    selection: ArtifactSelection,
    quarantine_root: Path,
) -> Path:
    try:
        _complete_interrupted_seal(target)
        return _validated_installed_executable(target, selection)
    except (OSError, RuntimeError):
        _quarantine(target, quarantine_root, prefix="cache")
        raise RuntimeError("tool-installation: cache-integrity-failure") from None


def _ensure_verified_installation(  # NOSONAR -- lock/recovery branches are explicit security states.
    repo_root: Path,
    selection: ArtifactSelection,
    *,
    acquire: Callable[[], bytes],
    materialize: Callable[[bytes, ArtifactSelection], Mapping[str, bytes]],
    legacy_path: Path | None = None,
    installation_root: Path | None = None,
    immutable_seed_root: Path | None = None,
) -> Path:
    """Return one fully admitted executable from a private installed tree."""

    install_root = installation_root or default_installation_root(repo_root)
    _require_qualified_filesystem(install_root)
    target = installation_tree_path(install_root, selection)
    artifact_root = install_root / selection.artifact_id
    lock_root = artifact_root / ".locks"
    quarantine_root = artifact_root / ".quarantine"
    _ensure_private_subdirectory(target.parent, install_root)
    _ensure_private_subdirectory(lock_root, install_root)
    _ensure_private_subdirectory(quarantine_root, install_root)
    identity = target.name
    identity_lock = lock_root / f"install-{identity}.lock"
    migration_lock = lock_root / f"migration-{selection.platform_id}.lock"

    if _tree_present(target):
        try:
            return _validated_installed_executable(target, selection)
        except (OSError, RuntimeError):
            with _portable_lock(identity_lock):
                if _tree_present(target):  # NOSONAR -- recheck under the lock closes the publication race.
                    return _validated_existing_or_quarantine(target, selection, quarantine_root)
            raise RuntimeError("tool-installation: cache-integrity-failure") from None

    legacy_materialized: Mapping[str, bytes] | None = None
    if legacy_path is not None:
        with _portable_lock(migration_lock):
            legacy_materialized = _legacy_carrier(legacy_path, selection, quarantine_root)

    with _portable_lock(identity_lock):
        _clean_staging(target.parent, target.name)
        if _tree_present(target):
            return _validated_existing_or_quarantine(target, selection, quarantine_root)

        if legacy_materialized is not None:
            materialized = legacy_materialized
        elif immutable_seed_root is not None:
            _require_qualified_filesystem(immutable_seed_root)
            seed_tree = installation_tree_path(immutable_seed_root, selection)
            try:
                _assert_immutable_seed_chain(immutable_seed_root, seed_tree)
                materialized = _validate_tree(seed_tree, selection.installed_manifest, mode="seed")
            except (OSError, RuntimeError):
                raise RuntimeError("tool-installation: seed-integrity-failure") from None
        else:
            raw_bytes = _validate_raw_bytes(acquire(), selection)
            materialized = materialize(raw_bytes, selection)
        materialized = _validate_materialized(materialized, selection.installed_manifest)
        _publish_tree(target, selection.installed_manifest, materialized)
        return target / _executable_entry(selection).path


def ensure_verified_installation(
    repo_root: Path,
    selection: ArtifactSelection,
    *,
    acquire: Callable[[], bytes],
    materialize: Callable[[bytes, ArtifactSelection], Mapping[str, bytes]],
    legacy_path: Path | None = None,
    installation_root: Path | None = None,
    immutable_seed_root: Path | None = None,
) -> Path:
    """Return one fully admitted executable without leaking filesystem details."""

    try:
        install_root = installation_root or default_installation_root(repo_root)
        with _private_root_guard(repo_root, install_root):
            return _ensure_verified_installation(
                repo_root,
                selection,
                acquire=acquire,
                materialize=materialize,
                legacy_path=legacy_path,
                installation_root=install_root,
                immutable_seed_root=immutable_seed_root,
            )
    except RuntimeError:
        raise
    except OSError as exc:
        reason = (
            "storage-exhausted" if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)} else "filesystem-failure"
        )
        raise RuntimeError(f"tool-installation: {reason}") from None
