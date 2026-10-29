"""Bounded native child execution for archive decoding and finite model checks.

Callers own fixed argument construction and any required namespace isolation.
Output descriptors must refer to private regular files, never pipes or devices.
"""

from __future__ import annotations

import os
import signal
import stat
import subprocess
from collections.abc import Sequence
from contextlib import suppress
from typing import BinaryIO


def run_bounded(
    command: Sequence[str],
    *,
    stdout: BinaryIO,
    stderr: BinaryIO,
    stdin: BinaryIO | None = None,
    wall_seconds: float = 45,
    file_bytes: int = 1024 * 1024,
) -> None:
    """Run with fixed host limits; refuse partial results and reap descendants."""

    if not 0 < wall_seconds <= 60 or not 0 < file_bytes <= 256 * 1024 * 1024:
        raise ValueError("invalid tool budget")
    if not all(stat.S_ISREG(os.fstat(stream.fileno()).st_mode) for stream in (stdout, stderr)):
        raise ValueError("tool output requires private files")
    argv = [
        "/usr/bin/prlimit",
        "--core=0",
        "--cpu=30",
        "--as=2147483648",
        "--nofile=64",
        f"--fsize={file_bytes}",
        "--",
        *command,
    ]
    child: subprocess.Popen[bytes] | None = None
    try:
        child = subprocess.Popen(
            argv,
            stdin=stdin if stdin is not None else subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env={"PATH": "/usr/bin", "LC_ALL": "C", "TZ": "UTC"},
            start_new_session=True,
            close_fds=True,
        )
        code = child.wait(timeout=wall_seconds)
        if code != 0 or any(os.fstat(stream.fileno()).st_size >= file_bytes for stream in (stdout, stderr)):
            raise RuntimeError("bounded-tool-failed")
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("bounded-tool-failed") from None
    finally:
        if child is not None:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
