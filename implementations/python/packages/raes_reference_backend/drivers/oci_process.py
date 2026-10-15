"""Bounded native CLI leaf; terminating the CLI proves nothing about remote effects."""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from time import monotonic
from typing import Protocol


class NativeProcessRunner(Protocol):
    def __call__(self, argv: list[str], *, deadline: float, max_output_bytes: int) -> bytes: ...


def run_bounded_process(argv: list[str], *, deadline: float, max_output_bytes: int) -> bytes:
    """Execute trusted fixed arguments with bounded output and no inherited credentials."""

    if (
        not argv
        or not os.path.isabs(argv[0])
        or any(not isinstance(item, str) or "\0" in item for item in argv)
        or type(max_output_bytes) is not int
        or not 1 <= max_output_bytes <= 1024 * 1024
    ):
        raise ValueError("native command configuration is invalid")
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ValueError("native command deadline exhausted")
    try:
        return asyncio.run(_run(argv, remaining, max_output_bytes))
    except TimeoutError:
        raise ValueError("native command deadline exhausted") from None
    except OSError:
        raise ValueError("native command is unavailable") from None


async def _run(argv: list[str], seconds: float, limit: int) -> bytes:
    process = None
    try:
        async with asyncio.timeout(seconds):
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": os.defpath},
                cwd="/",
                limit=min(limit + 1, 4096),
            )
            output = bytearray()
            while chunk := await process.stdout.read(min(8192, limit - len(output) + 1)):
                if len(output) + len(chunk) > limit:
                    raise ValueError("native command exceeded its output bound")
                output.extend(chunk)
            if await process.wait() != 0:
                raise ValueError("native command did not succeed")
            return bytes(output)
    finally:
        if process is not None:
            await _reap_process(process)


async def _reap_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.kill()
    async with asyncio.timeout(1):
        # Drain a paused transport before wait(), including after a kill.
        if process.stdout is not None:
            await _discard_output(process.stdout)
        await process.wait()


async def _discard_output(stream: asyncio.StreamReader) -> None:
    while not stream.at_eof():
        await stream.read(4096)
