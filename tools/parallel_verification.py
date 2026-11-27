#!/usr/bin/env python3
"""Run isolated nox verification lanes concurrently.

The canonical nox ``verify`` session uses this module to execute independent
lanes in separate processes.  Keeping the processes isolated avoids sharing a
``nox.Session`` across threads, while the fixed argv construction preserves the
repository's single nox verification graph.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter


@dataclass(frozen=True)
class VerificationLane:
    """One independently executable nox session in the verification graph."""

    name: str
    nox_session: str
    posargs: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationLaneResult:
    """Captured outcome for one lane."""

    name: str
    returncode: int
    output: str
    duration_s: float


def _run_lane(
    lane: VerificationLane,
    *,
    nox_python: Path,
    noxfile: Path,
    repo_root: Path,
    base_env: Mapping[str, str],
) -> VerificationLaneResult:
    command = [
        str(nox_python),
        "-m",
        "nox",
        "-f",
        str(noxfile),
        "-s",
        lane.nox_session,
    ]
    if lane.posargs:
        command.extend(("--", *lane.posargs))
    environment = os.environ.copy()
    environment.update(base_env)
    environment.update(lane.env)
    started = perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        returncode = completed.returncode
        output = completed.stdout or ""
    except OSError as exc:
        # A lane that cannot start is a typed result; the OS reason is bounded text without paths.
        returncode = 126
        output = f"unable to start verification lane {lane.name}: {exc.strerror or type(exc).__name__}\n"
    return VerificationLaneResult(
        name=lane.name,
        returncode=returncode,
        output=output,
        duration_s=perf_counter() - started,
    )


def run_verification_lanes(
    lanes: Sequence[VerificationLane],
    *,
    nox_python: Path,
    noxfile: Path,
    repo_root: Path,
    base_env: Mapping[str, str] | None = None,
    max_workers: int | None = None,
) -> list[VerificationLaneResult]:
    """Run all lanes concurrently and return results in declaration order."""

    if not lanes:
        return []
    worker_count = len(lanes) if max_workers is None else max_workers
    if worker_count < 1:
        raise ValueError("max_workers must be at least one")
    environment = dict(base_env or {})
    with ThreadPoolExecutor(max_workers=min(len(lanes), worker_count), thread_name_prefix="verification") as executor:
        futures = [
            executor.submit(
                _run_lane,
                lane,
                nox_python=nox_python,
                noxfile=noxfile,
                repo_root=repo_root,
                base_env=environment,
            )
            for lane in lanes
        ]
        return [future.result() for future in futures]
