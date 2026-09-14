"""Acquire reviewed generic-tool bytes through the qualified native client."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

SYSTEM_CURL = Path("/usr/bin/curl")
PROBE_TIMEOUT_SECONDS = 15
MAX_PROBE_OUTPUT_BYTES = 8192
MAX_GENERIC_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_LARGE_OBJECT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_TRANSFER_SECONDS = 30
_HASH_CHUNK_BYTES = 1024 * 1024
_MINIMUM_CURL = (8, 4, 0)
_VERSION_RE = re.compile(r"(\d{1,10})[.](\d{1,10})[.](\d{1,10})")
_CLIENT_ENV = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
_TLS_EXIT_CODES = frozenset({35, 51, 58, 60, 77, 82, 83, 90, 91})


class LockedRawObject(Protocol):
    """The lock fields needed to admit one raw object."""

    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class TransferBudget:
    """A closed, separately qualified native-client budget for one object class.

    Every value is native curl configuration or process supervision; no field
    selects repository transport, retry, or redirect behavior.
    """

    budget_id: str
    max_bytes: int
    max_time_seconds: int
    connect_timeout_seconds: int
    retries: int
    retry_delay_seconds: int
    retry_max_time_seconds: int
    wall_grace_seconds: int
    low_speed_bytes_per_second: int | None = None
    low_speed_seconds: int | None = None


GENERIC_TRANSFER_BUDGET = TransferBudget(
    budget_id="generic",
    max_bytes=MAX_GENERIC_ARTIFACT_BYTES,
    max_time_seconds=DEFAULT_TRANSFER_SECONDS,
    connect_timeout_seconds=5,
    retries=2,
    retry_delay_seconds=1,
    retry_max_time_seconds=15,
    wall_grace_seconds=5,
)
# The pinned proof archive is a 1.2 GB object. Its budget is qualified
# separately so the generic 30 second bound is never falsely applied to it: a
# stalled transfer is aborted by curl's native low-speed limit, retries remain
# curl's own bounded retries, and the wall deadline covers the retry window.
LARGE_OBJECT_TRANSFER_BUDGET = TransferBudget(
    budget_id="large-object",
    max_bytes=MAX_LARGE_OBJECT_BYTES,
    max_time_seconds=3600,
    connect_timeout_seconds=15,
    retries=2,
    retry_delay_seconds=5,
    retry_max_time_seconds=120,
    wall_grace_seconds=150,
    low_speed_bytes_per_second=64 * 1024,
    low_speed_seconds=120,
)


def curl_version_is_supported(value: str) -> bool:
    """Return whether curl meets the qualified unknown-length size floor."""

    match = _VERSION_RE.search(value)
    return match is not None and tuple(int(part) for part in match.groups()) >= _MINIMUM_CURL


def _validated_transfer_bounds(
    executable: Path,
    url: str,
    max_bytes: int,
    max_time_seconds: int | None,
    budget: TransferBudget,
) -> int:
    """Validate the credential-free locator, fixed client, and budget; return the deadline."""

    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("curl transfer requires a credential-free HTTPS URL")
    if executable != SYSTEM_CURL or not executable.is_absolute():
        raise ValueError("curl transfer requires the qualified absolute client")
    deadline = budget.max_time_seconds if max_time_seconds is None else max_time_seconds
    if not 1 <= max_bytes <= budget.max_bytes:
        raise ValueError(f"curl transfer size limit is outside the {budget.budget_id} artifact budget")
    if not 1 <= deadline <= budget.max_time_seconds:
        raise ValueError(f"curl transfer deadline must be between 1 and {budget.max_time_seconds} seconds")
    return deadline


def _low_speed_argv(budget: TransferBudget) -> tuple[str, ...]:
    if budget.low_speed_bytes_per_second is None or budget.low_speed_seconds is None:
        return ()
    return ("--speed-limit", str(budget.low_speed_bytes_per_second), "--speed-time", str(budget.low_speed_seconds))


def curl_transfer_argv(
    executable: Path,
    url: str,
    output: Path,
    *,
    ca_cert: Path | None,
    max_bytes: int,
    max_time_seconds: int | None = None,
    budget: TransferBudget = GENERIC_TRANSFER_BUDGET,
) -> list[str]:
    """Build the fixed argv shared by qualification and real acquisition."""

    deadline = _validated_transfer_bounds(executable, url, max_bytes, max_time_seconds, budget)
    argv = [
        str(executable),
        "--disable",
        "--silent",
        "--show-error",
        "--fail",
        "--location",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--max-redirs",
        "5",
        "--retry",
        str(budget.retries),
        "--retry-delay",
        str(budget.retry_delay_seconds),
        "--retry-max-time",
        str(budget.retry_max_time_seconds),
        "--connect-timeout",
        str(budget.connect_timeout_seconds),
        "--max-time",
        str(deadline),
        "--max-filesize",
        str(max_bytes),
    ]
    argv.extend(_low_speed_argv(budget))
    if ca_cert is not None:
        argv.extend(("--cacert", str(ca_cert)))
    argv.extend(("--output", str(output), url))
    return argv


def _remove_output(output: Path, reason_code: str) -> dict[str, str]:
    output.unlink(missing_ok=True)
    return {"outcome": "failed", "reason_code": reason_code}


def _curl_preflight_failure(executable: Path) -> str | None:
    failure: str | None = None
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=dict(_CLIENT_ENV),
        )
    except (OSError, subprocess.SubprocessError):
        failure = "curl-unavailable"
    if failure is None:
        observed = f"{completed.stdout}\n{completed.stderr}"
        if completed.returncode != 0:
            failure = "curl-unavailable"
        elif len(observed.encode("utf-8")) > MAX_PROBE_OUTPUT_BYTES or not curl_version_is_supported(completed.stdout):
            failure = "curl-version-inadequate"
    return failure


def _curl_is_supported(executable: Path) -> bool:
    return _curl_preflight_failure(executable) is None


def run_curl_transfer(  # NOSONAR -- stable exit classes form the public diagnostic boundary.
    executable: Path,
    url: str,
    output: Path,
    *,
    ca_cert: Path | None,
    max_bytes: int,
    max_time_seconds: int | None = None,
    budget: TransferBudget = GENERIC_TRANSFER_BUDGET,
) -> dict[str, str]:
    """Run the qualified client once and return only a stable outcome."""

    argv = curl_transfer_argv(
        executable,
        url,
        output,
        ca_cert=ca_cert,
        max_bytes=max_bytes,
        max_time_seconds=max_time_seconds,
        budget=budget,
    )
    deadline = budget.max_time_seconds if max_time_seconds is None else max_time_seconds
    if preflight_failure := _curl_preflight_failure(executable):
        return _remove_output(output, preflight_failure)
    try:
        completed = subprocess.run(  # noqa: S603 -- fixed absolute executable and fixed argv.
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=deadline + budget.wall_grace_seconds,
            env=dict(_CLIENT_ENV),
        )
    except subprocess.TimeoutExpired:
        return _remove_output(output, "curl-wall-deadline")
    except OSError:
        return _remove_output(output, "curl-unavailable")
    if completed.returncode == 63:
        return _remove_output(output, "curl-size-limit-enforced")
    if completed.returncode in _TLS_EXIT_CODES:
        return _remove_output(output, "curl-tls-rejected")
    if completed.returncode == 28:
        return _remove_output(output, "curl-transfer-deadline")
    if completed.returncode != 0:
        return _remove_output(output, "curl-transfer-failed")
    try:
        mode = output.lstat().st_mode
        within_limit = stat.S_ISREG(mode) and not stat.S_ISLNK(mode) and output.stat().st_size <= max_bytes
    except OSError:
        within_limit = False
    if not within_limit:
        return _remove_output(output, "curl-size-limit-bypassed")
    return {"outcome": "passed", "reason_code": "curl-transfer-qualified"}


def _read_bounded_regular_file(path: Path, *, max_bytes: int) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise OSError("input is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise OSError("input changed while it was opened")
        payload = stream.read(max_bytes + 1)
    after = path.lstat()
    if len(payload) > max_bytes or len(payload) != opened.st_size or not os.path.samestat(opened, after):
        raise OSError("input changed while it was read")
    return payload


def _matches_lock(payload: bytes, expected: LockedRawObject) -> bool:
    return len(payload) == expected.size and sha256(payload).hexdigest() == expected.sha256


def acquire_locked_bytes(
    *,
    artifact_id: str,
    source_url: str,
    expected: LockedRawObject,
    local_input: Path | None = None,
) -> bytes:
    """Acquire one selected raw object and admit it against the reviewed lock."""

    if not 1 <= expected.size <= MAX_GENERIC_ARTIFACT_BYTES:
        raise RuntimeError(f"{artifact_id} locked raw size is outside the generic artifact budget")
    if local_input is not None:
        try:
            payload = _read_bounded_regular_file(local_input, max_bytes=expected.size)
        except OSError:
            raise RuntimeError(f"{artifact_id} local input failed locked identity validation") from None
        if not _matches_lock(payload, expected):
            raise RuntimeError(f"{artifact_id} local input failed locked identity validation")
        return payload

    with tempfile.TemporaryDirectory(prefix="raes-artifact-acquisition-") as temporary_dir:
        output = Path(temporary_dir) / "raw-object"
        result = run_curl_transfer(
            SYSTEM_CURL,
            source_url,
            output,
            ca_cert=None,
            max_bytes=expected.size,
        )
        if result["outcome"] != "passed":
            raise RuntimeError(f"{artifact_id} acquisition failed: {result['reason_code']}")
        try:
            payload = _read_bounded_regular_file(output, max_bytes=expected.size)
        except OSError:
            raise RuntimeError(f"{artifact_id} acquired output is unsafe") from None
        if not _matches_lock(payload, expected):
            raise RuntimeError(f"{artifact_id} acquired bytes differ from the reviewed lock")
        return payload


def _open_regular_no_follow(path: Path) -> tuple[int, os.stat_result]:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise OSError("input is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)
    descriptor = os.open(path, flags)
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
        os.close(descriptor)
        raise OSError("input changed while it was opened")
    return descriptor, opened


def _copy_bounded_regular_file(source: Path, destination: Path, *, expected: LockedRawObject) -> bool:
    """Copy one opened source inode into a caller-owned file while hashing it."""

    descriptor, opened = _open_regular_no_follow(source)
    digest = sha256()
    total = 0
    with os.fdopen(descriptor, "rb") as stream:
        if opened.st_size != expected.size:
            return False
        flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        output = os.open(destination, flags)
        try:
            while chunk := stream.read(min(_HASH_CHUNK_BYTES, expected.size + 1 - total)):
                total += len(chunk)
                if total > expected.size:
                    return False
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    view = view[os.write(output, view) :]
            os.fsync(output)
        finally:
            os.close(output)
        after = source.lstat()
    unchanged = os.path.samestat(opened, after) and after.st_size == opened.st_size
    return unchanged and total == expected.size and digest.hexdigest() == expected.sha256


def _regular_file_matches_lock(path: Path, expected: LockedRawObject) -> bool:
    descriptor, opened = _open_regular_no_follow(path)
    digest = sha256()
    total = 0
    with os.fdopen(descriptor, "rb") as stream:
        if opened.st_size != expected.size:
            return False
        while chunk := stream.read(min(_HASH_CHUNK_BYTES, expected.size + 1 - total)):
            total += len(chunk)
            digest.update(chunk)
    after = path.lstat()
    return os.path.samestat(opened, after) and total == expected.size and digest.hexdigest() == expected.sha256


def acquire_locked_file(
    *,
    artifact_id: str,
    source_url: str,
    expected: LockedRawObject,
    destination: Path,
    local_input: Path | None = None,
    budget: TransferBudget = LARGE_OBJECT_TRANSFER_BUDGET,
) -> None:
    """Place one selected raw object in a caller-owned private file and admit it.

    The destination must already exist as the caller's exclusive staging file.
    An explicit local input is copied from its opened inode; otherwise the
    qualified native client writes the object. Either carrier is admitted only
    by exact size and SHA-256, and a failed admission never falls back.
    """

    if not 1 <= expected.size <= budget.max_bytes:
        raise RuntimeError(f"{artifact_id} locked raw size is outside the {budget.budget_id} artifact budget")
    if local_input is not None:
        try:
            admitted = _copy_bounded_regular_file(local_input, destination, expected=expected)
        except OSError:
            admitted = False
        if not admitted:
            raise RuntimeError(f"{artifact_id} local input failed locked identity validation")
        return
    result = run_curl_transfer(
        SYSTEM_CURL,
        source_url,
        destination,
        ca_cert=None,
        max_bytes=expected.size,
        budget=budget,
    )
    if result["outcome"] != "passed":
        raise RuntimeError(f"{artifact_id} acquisition failed: {result['reason_code']}")
    try:
        admitted = _regular_file_matches_lock(destination, expected)
    except OSError:
        raise RuntimeError(f"{artifact_id} acquired output is unsafe") from None
    if not admitted:
        raise RuntimeError(f"{artifact_id} acquired bytes differ from the reviewed lock")


__all__ = [
    "GENERIC_TRANSFER_BUDGET",
    "LARGE_OBJECT_TRANSFER_BUDGET",
    "MAX_GENERIC_ARTIFACT_BYTES",
    "MAX_LARGE_OBJECT_BYTES",
    "SYSTEM_CURL",
    "TransferBudget",
    "acquire_locked_bytes",
    "acquire_locked_file",
    "curl_transfer_argv",
    "curl_version_is_supported",
    "run_curl_transfer",
]
