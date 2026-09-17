#!/usr/bin/env python3
"""Pull and verify the locked release-test image using the native runtime."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar

# The release lane runs this file as a script, so `sys.path[0]` is `tools/`
# rather than the repository root and the package imports below would not
# resolve. Every other tool entry point in this repository does the same.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.oci_release_selection import (  # noqa: E402
    EXECUTION_PLATFORM_ID,
    EXECUTION_PROFILE_ID,
    RELEASE_TEST_IMAGE_ARTIFACT_ID,
    RELEASE_TEST_IMAGE_VERSION,
    REQUIRED_PLATFORM_IDS,
    ImageAdmissionError,
    LockedPlatformGraph,  # noqa: E402
    execution_graph,
    locked_platform_graphs,
    locked_repository,
)

SOURCE_CLASS_ENV = "RAES_OCI_SOURCE_CLASS"
MIRROR_REPOSITORY_ENV = "RAES_OCI_MIRROR_REPOSITORY"

_ALLOWED_RUNTIMES = frozenset({"docker", "podman"})
# Ambient proxy, registry, credential-helper and image-override state must not
# reach a client this module starts.
_CLIENT_ENV = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
PULL_TIMEOUT_SECONDS = 600
INSPECT_TIMEOUT_SECONDS = 60

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# A bare repository reference: optional host[:port], then lowercase path
# components. No scheme, userinfo, query, tag or digest may appear, so a mirror
# setting can never smuggle a credential or re-pin the image.
_DOMAIN = (
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?))*(?::[0-9]{1,5})?"
)
_PATH_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*"
_REPOSITORY_RE = re.compile(rf"^(?:{_DOMAIN}/)?{_PATH_COMPONENT}(?:/{_PATH_COMPONENT})*$")

_INSPECT_FORMAT = "{{.Architecture}}\n{{.Os}}\n{{json .RootFS.Layers}}"

Runner = Callable[..., subprocess.CompletedProcess]


def _default_runner(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, **kwargs)


def _run(argv: list[str], *, timeout: int, runner: Runner) -> str:
    """Run one fixed argv under a bounded wall clock and a minimal environment."""

    try:
        completed = runner(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(_CLIENT_ENV),
        )
    except subprocess.TimeoutExpired as exc:
        raise ImageAdmissionError("client-timeout") from exc
    except OSError as exc:
        raise ImageAdmissionError("client-unavailable") from exc
    if completed.returncode != 0:
        raise ImageAdmissionError("acquisition-failed")
    return completed.stdout if isinstance(completed.stdout, str) else ""


def _require_runtime(runtime: str) -> str:
    if runtime not in _ALLOWED_RUNTIMES:
        raise ImageAdmissionError("runtime-not-allowed")
    return runtime


_T = TypeVar("_T")


def attempt(operation: Callable[[], _T]) -> tuple[_T | None, str | None]:
    """Run one admission step, returning its stable reason code on refusal.

    Admission refusals are classified by the caller -- an availability failure
    may skip an optional run while an integrity failure never may -- so the
    reason code has to reach that decision as a value. Catching the module's own
    exception here keeps that handling in the module that defines it.
    """

    try:
        return operation(), None
    except ImageAdmissionError as exc:
        return None, exc.reason


def resolve_source(environ: Mapping[str, str]) -> None:
    """Refuse retired disconnected settings instead of silently going online."""
    if environ.get(SOURCE_CLASS_ENV, "public") != "public" or environ.get(MIRROR_REPOSITORY_ENV):
        raise ImageAdmissionError("source-class")


def image_reference(locked_repository: str, index_digest: str) -> str:
    """Return the digest-pinned reference from the selected lock."""
    if _DIGEST_RE.fullmatch(index_digest) is None or _REPOSITORY_RE.fullmatch(locked_repository) is None:
        raise ImageAdmissionError("image-identity")
    return f"{locked_repository}@{index_digest}"


def acquire_image(
    reference: str,
    *,
    runtime: str,
    runner: Runner = _default_runner,
) -> None:
    """Pull the locked image once; native client failures remain terminal."""
    repository, separator, digest = reference.partition("@")
    if not separator or image_reference(repository, digest) != reference:
        raise ImageAdmissionError("image-identity")
    _run(
        [_require_runtime(runtime), "pull", reference],
        timeout=PULL_TIMEOUT_SECONDS,
        runner=runner,
    )


def verify_daemon_image(
    reference: str,
    graph: LockedPlatformGraph,
    *,
    runtime: str,
    runner: Runner = _default_runner,
) -> None:
    """Prove the runtime holds exactly the reviewed platform image.

    The uncompressed layer identities are used rather than the daemon's image
    id, because the id means the config digest under one storage driver and the
    pulled manifest digest under another, while the layer identities are
    intrinsic to the content and therefore survive a registry pull, an offline
    import and either driver.
    """

    stdout = _run(
        [
            _require_runtime(runtime),
            "image",
            "inspect",
            "--format",
            _INSPECT_FORMAT,
            reference,
        ],
        timeout=INSPECT_TIMEOUT_SECONDS,
        runner=runner,
    )
    fields = stdout.strip().splitlines()
    if len(fields) != 3:
        raise ImageAdmissionError("image-identity")
    architecture, operating_system, raw_layers = fields
    try:
        layers = json.loads(raw_layers)
    except ValueError as exc:
        raise ImageAdmissionError("image-identity") from exc
    observed = (
        architecture,
        operating_system,
        tuple(layers) if isinstance(layers, list) else (),
    )
    if observed != (graph.architecture, graph.os, graph.diff_ids):
        raise ImageAdmissionError("image-identity")


__all__ = (
    "EXECUTION_PLATFORM_ID",
    "EXECUTION_PROFILE_ID",
    "RELEASE_TEST_IMAGE_ARTIFACT_ID",
    "RELEASE_TEST_IMAGE_VERSION",
    "REQUIRED_PLATFORM_IDS",
    "ImageAdmissionError",
    "SOURCE_CLASS_ENV",
    "MIRROR_REPOSITORY_ENV",
    "attempt",
    "resolve_source",
    "image_reference",
    "acquire_image",
    "verify_daemon_image",
    "execution_graph",
    "locked_platform_graphs",
    "locked_repository",
)
