"""Expose only the filesystem tar from descriptor-held, verified Debian bytes."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

from tools.bounded_tool_process import OperationalError, run_bounded
from tools.verified_tool_installation import ToolInstallationError


@contextmanager
def decoded_debian_tree(stream: BinaryIO) -> Iterator[BinaryIO]:
    """Use the maintained decoder without installing or executing package hooks."""

    with tempfile.TemporaryFile() as decoded, tempfile.TemporaryFile() as errors:
        try:
            run_bounded(
                ["/usr/bin/dpkg-deb", "--fsys-tarfile", "-"],
                stdin=stream,
                stdout=decoded,
                stderr=errors,
                file_bytes=256 * 1024 * 1024,
            )
        except OperationalError:
            raise ToolInstallationError("tool-installation: archive-decoder-failed") from None
        decoded.seek(0)
        yield decoded
