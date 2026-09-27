"""Bounded repository file access for the offline model producer."""

import os
import stat
from pathlib import Path, PurePosixPath

from tools.policy.common import safe_repo_path

MAX_BYTES = 2 * 1024 * 1024


def safe_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (
        not parts
        or len(relative) > 256
        or "\\" in relative
        or any(part in {".", ".."} for part in parts)
    ):
        raise ValueError("unsafe model artifact path")
    target = safe_repo_path(root, relative)
    if target is None or target != root.resolve() / relative:
        raise ValueError("unsafe model artifact path")
    cursor = root.resolve()
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("unsafe model artifact path")
    return target


def read_bytes(root: Path, relative: str) -> bytes:
    safe_path(root, relative)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("invalid model artifact file")
            content = stream.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError("model artifact exceeds byte limit")
            return content
    except OSError:
        raise ValueError("model artifact is unavailable or unsafe") from None
    finally:
        os.close(directory)
