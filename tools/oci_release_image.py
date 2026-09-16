#!/usr/bin/env python3
"""Admission boundary for the reviewed release-test OCI image.

Acquisition location and image identity are separate concerns. The identity is
the reviewed index digest in the development artifact lock and never changes
with the source; the location is a closed source class an operator selects.
Because a mirror-only or pre-seeded site has no route to the public origin, a
silent fallback between classes would convert an availability failure into an
unreviewed public pull -- so there is none.

Skopeo and Docker/Podman own every transfer. This module builds validated fixed
argv, bounds the process, hashes local bytes, and classifies exits. It contains
no HTTP, registry protocol, retry, redirect, TLS or framing code, and it never
places a credential, endpoint or native output on argv or in a diagnostic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# The release lane runs this file as a script, so `sys.path[0]` is `tools/`
# rather than the repository root and the package imports below would not
# resolve. Every other tool entry point in this repository does the same.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.oci_image_layout import LayoutRejected, LockedPlatformGraph, OciDescriptor, verify_layout  # noqa: E402

# The reviewed lock selection this module admits.
RELEASE_TEST_IMAGE_ARTIFACT_ID = "release-test-alpine"
RELEASE_TEST_IMAGE_VERSION = "3.20.10"
# Every platform a mirror or offline export must carry.
REQUIRED_PLATFORM_IDS = ("linux-x86_64", "linux-arm64")
# The one platform the release lane executes on. arm64 is retained and exported,
# but claiming arm64 execution would need daemon evidence this repository does
# not have (see `docs/decisions/package-artifacts/architecture.md`).
EXECUTION_PLATFORM_ID = "linux-x86_64"
EXECUTION_PROFILE_ID = "public-linux-x86_64"

SOURCE_CLASS_ENV = "RAES_OCI_SOURCE_CLASS"
MIRROR_REPOSITORY_ENV = "RAES_OCI_MIRROR_REPOSITORY"

LAYOUT_TAG = "release-test"
# An imported image carries no registry repository digest, so a pre-seeded
# context names it locally. The tag is the reviewed index digest itself, which
# cannot float to other content and is derived from the lock rather than from
# operator input.
PRESEED_LOCAL_REPOSITORY = "raes-release-test/alpine"
_COPY_CLIENT = "skopeo"
_ALLOWED_RUNTIMES = frozenset({"docker", "podman"})
# Ambient proxy, registry, credential-helper and image-override state must not
# reach a client this module starts.
_CLIENT_ENV = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
PULL_TIMEOUT_SECONDS = 600
COPY_TIMEOUT_SECONDS = 900
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


class ImageAdmissionError(Exception):
    """The release-test image could not be admitted.

    Carries a stable reason code only. A mirror endpoint, credential, image
    reference or native client output never reaches the message.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"release-test image admission failed: {reason}")
        self.reason = reason


class SourceClass(Enum):
    """Where the reviewed image may be obtained in this context."""

    PRESEEDED = "preseeded"
    MIRROR = "mirror"
    PUBLIC = "public"


@dataclass(frozen=True)
class ImageSource:
    source_class: SourceClass
    repository: str | None = None


SelectionLoader = Callable[..., "object"]

# The lock admits arm64 for retention and export; only the execution platform
# has a profile that also claims a daemon can run it.
_PLATFORM_PROFILES = {
    "linux-x86_64": "public-linux-x86_64",
    "linux-arm64": "public-linux-arm64",
}


def _default_selection_loader(*, version: str, platform_id: str, profile_id: str):
    """Load one reviewed lock selection through the canonical policy gate.

    The artifact id is a literal here on purpose: the selector policy reads it
    statically, so a computed id would make this consumer invisible to the
    coverage gate that proves every locked artifact has exactly one consumer.
    """

    from tools.tooling_policy_gate import load_tooling_artifact_selection

    return load_tooling_artifact_selection(
        artifact_id="release-test-alpine",
        version=version,
        platform_id=platform_id,
        profile_id=profile_id,
    )


def _descriptor(value) -> OciDescriptor:
    return OciDescriptor(digest=value.digest, size=value.size)


def locked_repository(*, loader: SelectionLoader = _default_selection_loader) -> str:
    """Return the reviewed image repository, without its registry-neutral scheme."""

    selection = _select(EXECUTION_PLATFORM_ID, loader)
    return _asset(selection)


def _asset(selection) -> str:
    """Return the reviewed OCI repository the locked index digest lives in."""

    asset = getattr(selection, "asset", "")
    if not isinstance(asset, str) or _REPOSITORY_RE.fullmatch(asset) is None:
        raise ImageAdmissionError("image-identity")
    return asset


def _select(platform_id: str, loader: SelectionLoader):
    return loader(
        version=RELEASE_TEST_IMAGE_VERSION,
        platform_id=platform_id,
        profile_id=_PLATFORM_PROFILES[platform_id],
    )


def locked_platform_graphs(*, loader: SelectionLoader = _default_selection_loader) -> tuple[LockedPlatformGraph, ...]:
    """Project the reviewed graph of every platform a mirror or export must carry.

    A selection without a graph is refused rather than degraded to an index-only
    check, and every platform must sit under one reviewed index -- two indexes
    would mean two images wearing one artifact id.
    """

    graphs: list[LockedPlatformGraph] = []
    for platform_id in REQUIRED_PLATFORM_IDS:
        selection = _select(platform_id, loader)
        graph = getattr(selection, "oci_graph", None)
        if graph is None:
            raise ImageAdmissionError("graph-unavailable")
        graphs.append(
            LockedPlatformGraph(
                platform_id=platform_id,
                index=_descriptor(graph.index),
                manifest=_descriptor(graph.manifest),
                config=_descriptor(graph.config),
                layers=tuple(_descriptor(layer) for layer in graph.layers),
                diff_ids=tuple(graph.diff_ids),
                architecture=graph.architecture,
                os=graph.os,
                variant=graph.variant,
            )
        )
    if len({graph.index for graph in graphs}) != 1:
        raise ImageAdmissionError("index-identity")
    return tuple(graphs)


def execution_graph(graphs: Sequence[LockedPlatformGraph]) -> LockedPlatformGraph:
    """Return the one platform graph the release lane executes."""

    for graph in graphs:
        if graph.platform_id == EXECUTION_PLATFORM_ID:
            return graph
    raise ImageAdmissionError("graph-unavailable")


def _default_runner(argv: list[str], **kwargs) -> subprocess.CompletedProcess:  # pragma: no cover - IO leaf
    return subprocess.run(argv, **kwargs)


def _run(argv: list[str], *, timeout: int, runner: Runner) -> str:
    """Run one fixed argv under a bounded wall clock and a minimal environment."""

    try:
        completed = runner(
            argv,
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


def resolve_source(environ: Mapping[str, str]) -> ImageSource:
    """Resolve the closed source class an operator selected.

    An unset selector means the ordinary public origin. A mirror-only context
    must name its reviewed mirror repository; a missing or malformed value fails
    closed rather than degrading to a public pull.
    """

    raw = environ.get(SOURCE_CLASS_ENV, SourceClass.PUBLIC.value)
    try:
        source_class = SourceClass(raw)
    except ValueError as exc:
        raise ImageAdmissionError("source-class") from exc
    if source_class is not SourceClass.MIRROR:
        return ImageSource(source_class=source_class)
    repository = environ.get(MIRROR_REPOSITORY_ENV, "")
    if _REPOSITORY_RE.fullmatch(repository) is None:
        raise ImageAdmissionError("mirror-configuration")
    return ImageSource(source_class=source_class, repository=repository)


def image_reference(locked_repository: str, index_digest: str, source: ImageSource) -> str:
    """Return the digest-pinned reference for *source*.

    The digest is the reviewed index identity in every class, so a mirror
    changes only where the same bytes are read from. There is no spelling of
    this function that produces a tag.
    """

    if _DIGEST_RE.fullmatch(index_digest) is None:
        raise ImageAdmissionError("image-identity")
    if source.source_class is SourceClass.PRESEEDED:
        return local_preseed_reference(index_digest)
    repository = source.repository or locked_repository
    if _REPOSITORY_RE.fullmatch(repository) is None:
        raise ImageAdmissionError("image-identity")
    return f"{repository}@{index_digest}"


def local_preseed_reference(index_digest: str) -> str:
    """Return the local name an imported reviewed image is loaded under."""

    if _DIGEST_RE.fullmatch(index_digest) is None:
        raise ImageAdmissionError("image-identity")
    return f"{PRESEED_LOCAL_REPOSITORY}:{index_digest.removeprefix('sha256:')}"


def acquire_image(
    source: ImageSource,
    reference: str,
    *,
    runtime: str,
    runner: Runner = _default_runner,
) -> None:
    """Obtain the reviewed image for *source*, or fail.

    A pre-seeded context performs no acquisition at all: the image is already
    present, and reaching the network would defeat the reason the class exists.
    A failed mirror pull is terminal -- the public origin is never tried.
    """

    if source.source_class is SourceClass.PRESEEDED:
        return
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
        [_require_runtime(runtime), "image", "inspect", "--format", _INSPECT_FORMAT, reference],
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
    observed = (architecture, operating_system, tuple(layers) if isinstance(layers, list) else ())
    if observed != (graph.architecture, graph.os, graph.diff_ids):
        raise ImageAdmissionError("image-identity")


def export_layout(reference: str, layout_root: Path, *, runner: Runner = _default_runner) -> None:
    """Copy every reviewed platform of *reference* into an OCI layout.

    `--all` carries the whole reviewed index rather than the running host's
    platform, and `--preserve-digests` makes the client refuse rather than
    silently re-serialize the graph this repository pinned.
    """

    _run(
        [
            _COPY_CLIENT,
            "copy",
            "--all",
            "--preserve-digests",
            f"docker://{reference}",
            f"oci:{layout_root}:{LAYOUT_TAG}",
        ],
        timeout=COPY_TIMEOUT_SECONDS,
        runner=runner,
    )


def import_layout_into_daemon(layout_root: Path, local_reference: str, *, runner: Runner = _default_runner) -> None:
    """Load the verified layout's host platform into the local runtime.

    The layout must already have been admitted by
    `tools.oci_image_layout.verify_layout`; the daemon readback afterwards is
    corroboration, not the integrity proof.
    """

    _run(
        [
            _COPY_CLIENT,
            "copy",
            f"oci:{layout_root}:{LAYOUT_TAG}",
            f"docker-daemon:{local_reference}",
        ],
        timeout=COPY_TIMEOUT_SECONDS,
        runner=runner,
    )


def export_command(
    *,
    layout_root: Path | str,
    environ: Mapping[str, str],
    loader: SelectionLoader = _default_selection_loader,
    runner: Runner = _default_runner,
) -> Path:
    """Export every reviewed platform, then admit the result offline.

    A pre-seeded context has nothing to export from -- that is the point of the
    class -- so asking for one here is a configuration error rather than a
    reason to reach a registry.
    """

    source = resolve_source(environ)
    if source.source_class is SourceClass.PRESEEDED:
        raise ImageAdmissionError("source-class")
    graphs = locked_platform_graphs(loader=loader)
    reference = image_reference(locked_repository(loader=loader), graphs[0].index.digest, source)
    destination = Path(layout_root)
    export_layout(reference, destination, runner=runner)
    verify_layout(destination, graphs)
    return destination


def import_command(
    *,
    layout_root: Path | str,
    runtime: str,
    environ: Mapping[str, str],
    loader: SelectionLoader = _default_selection_loader,
    runner: Runner = _default_runner,
) -> str:
    """Admit a layout offline, load it, then prove what the runtime now holds.

    The offline admission happens first and unconditionally: an export is an
    untrusted carrier, and a client must never be handed content this
    repository has not already re-hashed against the reviewed lock.
    """

    # An import has no source class to resolve: the layout in hand is the
    # source, and admitting it must not depend on how it was obtained. The
    # parameter is kept so both commands share one call shape.
    del environ
    graphs = locked_platform_graphs(loader=loader)
    source = Path(layout_root)
    verify_layout(source, graphs)
    graph = execution_graph(graphs)
    reference = local_preseed_reference(graph.index.digest)
    import_layout_into_daemon(source, reference, runner=runner)
    verify_daemon_image(reference, graph, runtime=runtime, runner=runner)
    return reference


def main(argv: Sequence[str] | None = None) -> int:
    """Run the reviewed export/import boundary from the release lane."""

    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    export = subcommands.add_parser("export", help="copy every reviewed platform into a verified OCI layout")
    export.add_argument("--layout", required=True)
    load = subcommands.add_parser("import", help="admit a layout offline and load it into the container runtime")
    load.add_argument("--layout", required=True)
    load.add_argument("--runtime", default="docker")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "export":
            destination = export_command(layout_root=arguments.layout, environ=os.environ)
            print(f"exported and verified the reviewed OCI graph into {destination}")
        else:
            reference = import_command(
                layout_root=arguments.layout,
                runtime=arguments.runtime,
                environ=os.environ,
            )
            print(f"imported and verified the reviewed OCI graph as {reference}")
    except (ImageAdmissionError, LayoutRejected) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


__all__ = [
    "EXECUTION_PLATFORM_ID",
    "EXECUTION_PROFILE_ID",
    "ImageAdmissionError",
    "ImageSource",
    "LayoutRejected",
    "MIRROR_REPOSITORY_ENV",
    "PRESEED_LOCAL_REPOSITORY",
    "RELEASE_TEST_IMAGE_ARTIFACT_ID",
    "RELEASE_TEST_IMAGE_VERSION",
    "REQUIRED_PLATFORM_IDS",
    "SOURCE_CLASS_ENV",
    "SourceClass",
    "acquire_image",
    "execution_graph",
    "export_command",
    "export_layout",
    "image_reference",
    "import_command",
    "import_layout_into_daemon",
    "local_preseed_reference",
    "locked_platform_graphs",
    "locked_repository",
    "main",
    "resolve_source",
    "verify_daemon_image",
    "verify_layout",
]


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
