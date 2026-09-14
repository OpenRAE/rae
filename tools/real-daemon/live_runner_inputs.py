#!/usr/bin/env python3
"""Governed acquisition of the live-runner input closure.

The AWS smoke and guest-certification scripts under ``tools/real-daemon/`` used
to acquire their inputs ad hoc on the remote instance: an unpinned CirrOS
download whose failure was swallowed (``curl ... || true``), a pipe-to-shell uv
bootstrap (``curl ... | sh``) and an unfrozen ``libvirt-python`` install. Issue
#1222 replaces that with a single admitted closure selected/verified *locally*
against the reviewed lock and pre-seeded to the instance (see
``docs/decisions/package-artifacts/`` and the issue #1222 preflight note).

This module owns the CirrOS guest-disk selection. It is the sole runtime
lock-selection consumer of ``cirros-guest-disk`` declared in
``implementations/tooling/selector-bindings.json``; the selection call below
uses the reviewed literal dimensions the policy gate discovers. ``uv`` and
CPython are bootstrap-class payloads acquired through
``tools/bootstrap_profile.py`` (their kit verification already binds the lock
digests). ``libvirt-python`` and its build backend are pinned by exact version
and hash in ``tools/real-daemon/live-runner-python.txt`` (Python-closure
authority, not the generic artifact lock); every file in that closure is fetched
and verified here so the runners can install it fully offline.

The command produces a private staging directory holding the verified inputs and
a ``live-runner-inputs-manifest.json`` the shell scripts read to pre-seed and to
re-verify the transferred bytes on the instance. No AWS API, custom transport or
acquisition retry/redirect/TLS/framing code is introduced; acquisition reuses the
maintained-curl client.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.maintained_client_acquisition import acquire_locked_bytes
from tools.tool_versions import (
    CIRROS_GUEST_DISK_VERSION,
    LIVE_RUNNER_CPYTHON_ARTIFACT,
    LIVE_RUNNER_NATIVE_SNAPSHOT,
    LIVE_RUNNER_UBUNTU_IMAGE_NAME,
    LIVE_RUNNER_UBUNTU_IMAGE_OWNER,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# The live runner always targets a Linux x86_64 guest/host, independent of the
# operator box the acquisition runs on. CirrOS is only admitted for that target.
GUEST_PLATFORM_ID = "linux-x86_64"
LIVE_RUNNER_PROFILE_ID = "live-runner-linux-x86_64"
LIVE_RUNNER_HOST_PROFILE_ID = "live-runner-ubuntu-24.04-x86_64"
CIRROS_ARTIFACT_ID = "cirros-guest-disk"

# The pre-seeded image name the smoke harness consumes. Kept in step with the
# CirrOS artifact's installed-manifest path in artifacts.lock.json.
CIRROS_STAGED_NAME = "cirros.img"

LIBVIRT_PYTHON_REQUIREMENTS = REPO_ROOT / "tools" / "real-daemon" / "live-runner-python.txt"
# Reviewed manifest (data, not an inline tuple) for the offline libvirt-python
# build closure. Every sha256 here MUST equal the corresponding pin in
# live-runner-python.txt; test_issue_1222 asserts the equality so they cannot
# drift.
PYTHON_CLOSURE_MANIFEST = REPO_ROOT / "tools" / "real-daemon" / "live-runner-python-closure.json"
WHEELHOUSE_DIR = "wheelhouse"
MANIFEST_NAME = "live-runner-inputs-manifest.json"


@dataclass(frozen=True)
class _RawPin:
    """The lock fields the maintained client needs to admit one raw object."""

    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class _ClosureFile:
    name: str
    version: str
    filename: str
    url: str
    sha256: str
    size: int


def _load_python_closure() -> tuple[_ClosureFile, ...]:
    """Load the reviewed offline build-closure manifest, fail-closed."""

    document = json.loads(PYTHON_CLOSURE_MANIFEST.read_text(encoding="utf-8"))
    files = document.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("live-runner python closure manifest must list at least one file")
    closure: list[_ClosureFile] = []
    for entry in files:
        closure.append(
            _ClosureFile(
                name=str(entry["name"]),
                version=str(entry["version"]),
                filename=str(entry["filename"]),
                url=str(entry["url"]),
                sha256=str(entry["sha256"]),
                size=int(entry["size"]),
            )
        )
    return tuple(closure)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _admit_bytes(data: bytes, *, expected_sha256: str, expected_size: int, target: Path) -> Path:
    """Verify raw bytes against the reviewed identity and publish them atomically.

    This is the non-executable-object admission path for a ``vm-base-image``:
    unlike ``verified_tool_installation.ensure_verified_installation`` (which
    admits an executable tree), a guest disk is a plain data object, so it is
    verified here and written private-then-renamed.
    """

    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise RuntimeError("object bytes do not match the reviewed identity")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".partial")
    staging.write_bytes(data)
    staging.chmod(0o600)
    staging.replace(target)
    return target


def acquire_cirros_guest_disk(
    target: Path,
    *,
    version: str = CIRROS_GUEST_DISK_VERSION,
    local_input: Path | None = None,
) -> Path:
    """Select, verify and write the admitted CirrOS guest disk to ``target``.

    Selection flows through the tooling policy gate before any acquisition; the
    bytes are admitted against the reviewed raw and installed manifests. A guest
    disk is a plain data object, not an executable tree, so it is not routed
    through the executable-only ``ensure_verified_installation`` path.
    ``local_input`` admits an already-present reviewed file instead of a
    download.
    """

    from tools.tooling_policy_gate import load_tooling_artifact_selection

    selection = load_tooling_artifact_selection(
        artifact_id="cirros-guest-disk",
        version=version,
        platform_id=GUEST_PLATFORM_ID,
        profile_id=LIVE_RUNNER_PROFILE_ID,
    )
    if len(selection.source_urls) < 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise RuntimeError("cirros-guest-disk lock selection must contain a source, one raw asset, and one image")
    raw = selection.raw_manifest[0]
    installed = selection.installed_manifest[0]
    data = acquire_locked_bytes(
        artifact_id=CIRROS_ARTIFACT_ID,
        source_url=selection.source_urls[0],
        expected=_RawPin(path=raw.path, sha256=raw.sha256, size=raw.size),
        local_input=local_input,
    )
    return _admit_bytes(data, expected_sha256=installed.sha256, expected_size=installed.size, target=target)


def stage_python_closure(stage_dir: Path) -> dict[str, object]:
    """Fetch and verify the offline libvirt-python build closure into a wheelhouse."""

    wheelhouse = stage_dir / WHEELHOUSE_DIR
    wheelhouse.mkdir(mode=0o700, parents=True, exist_ok=True)
    staged: list[dict[str, object]] = []
    for entry in _load_python_closure():
        data = acquire_locked_bytes(
            artifact_id=f"live-runner-python:{entry.name}",
            source_url=entry.url,
            expected=_RawPin(path=entry.filename, sha256=entry.sha256, size=entry.size),
        )
        _admit_bytes(data, expected_sha256=entry.sha256, expected_size=entry.size, target=wheelhouse / entry.filename)
        staged.append(
            {"name": entry.name, "version": entry.version, "filename": entry.filename, "sha256": entry.sha256}
        )
    return {"dir": WHEELHOUSE_DIR, "files": staged}


def _libvirt_python_pin() -> dict[str, str]:
    """Parse the exact libvirt-python pin from the requirements file, fail-closed."""

    for line in LIBVIRT_PYTHON_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("libvirt-python=="):
            continue
        match = re.match(r"^libvirt-python==(?P<version>\S+)\s+--hash=sha256:(?P<sha>[0-9a-f]{64})", stripped)
        if match is None:
            break
        return {"name": "libvirt-python", "version": match.group("version"), "sha256": match.group("sha")}
    raise RuntimeError("live-runner libvirt-python pin must fix an exact version and sha256 hash")


def requirements_hashes() -> dict[str, str]:
    """Return the name->sha256 map declared in the pip requirements file."""

    hashes: dict[str, str] = {}
    for line in LIBVIRT_PYTHON_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(?P<name>[A-Za-z0-9._-]+)==\S+\s+--hash=sha256:(?P<sha>[0-9a-f]{64})", line.strip())
        if match is not None:
            hashes[match.group("name").lower()] = match.group("sha")
    return hashes


def stage_live_runner_inputs(
    stage_dir: Path,
    *,
    repo_root: Path = REPO_ROOT,
    cirros_local_input: Path | None = None,
    include_cirros: bool = True,
) -> Path:
    """Stage the verified live-runner closure and write its manifest.

    Returns the manifest path. The staging directory must live under the
    repository (the offline-kit fetch admits payloads through the fixed
    repository cache chain) and holds the verified linux-x86_64 uv payload, the
    offline libvirt-python build wheelhouse, the CirrOS guest disk (smoke only),
    and the manifest the shell scripts read to pre-seed the instance and
    re-verify the transferred bytes.
    """

    from tools.bootstrap_profile import fetch_offline_kit_payloads

    try:
        stage_dir.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise RuntimeError("live-runner stage directory must live under the repository") from exc

    stage_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    # uv and the declared CPython interpreter are bootstrap-class: acquire them
    # through the host-profile kit selection (verified against the lock), never a
    # per-artifact runtime selection. Binding the interpreter makes the ABI
    # execution-bound rather than relying on the host's ambient python3.
    payloads = {
        str(entry["artifact_id"]): entry
        for entry in fetch_offline_kit_payloads(
            LIVE_RUNNER_HOST_PROFILE_ID, stage_dir, [LIVE_RUNNER_CPYTHON_ARTIFACT, "uv"]
        )
    }
    uv_payload = payloads["uv"]
    cpython_payload = payloads[LIVE_RUNNER_CPYTHON_ARTIFACT]

    closure = stage_python_closure(stage_dir)

    manifest: dict[str, object] = {
        "schema": "raes.live-runner-inputs/v1",
        "base_image": {
            "owner": LIVE_RUNNER_UBUNTU_IMAGE_OWNER,
            "name": LIVE_RUNNER_UBUNTU_IMAGE_NAME,
        },
        "native_repository_snapshot": LIVE_RUNNER_NATIVE_SNAPSHOT,
        "cpython": {
            "artifact_id": LIVE_RUNNER_CPYTHON_ARTIFACT,
            "platform_id": GUEST_PLATFORM_ID,
            "staged_path": str(cpython_payload["path"]),
            "sha256": str(cpython_payload["sha256"]),
            "size": int(cpython_payload["size"]),
        },
        "uv": {
            "artifact_id": "uv",
            "platform_id": GUEST_PLATFORM_ID,
            "staged_path": str(uv_payload["path"]),
            "sha256": str(uv_payload["sha256"]),
            "size": int(uv_payload["size"]),
        },
        "libvirt_python": _libvirt_python_pin(),
        "python_closure": closure,
        "requirements_file": str(LIBVIRT_PYTHON_REQUIREMENTS.relative_to(repo_root)),
    }

    # The guest-certified run builds its own busybox appliance and does not use
    # CirrOS; only the plain smoke needs the guest disk pre-seeded.
    if include_cirros:
        staged_image = stage_dir / CIRROS_STAGED_NAME
        acquire_cirros_guest_disk(staged_image, local_input=cirros_local_input)
        manifest["cirros_guest_disk"] = {
            "artifact_id": CIRROS_ARTIFACT_ID,
            "version": CIRROS_GUEST_DISK_VERSION,
            "platform_id": GUEST_PLATFORM_ID,
            "staged_path": CIRROS_STAGED_NAME,
            "sha256": _sha256_file(staged_image),
            "size": staged_image.stat().st_size,
        }

    manifest_path = stage_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    return manifest_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage the admitted live-runner input closure.")
    parser.add_argument(
        "--stage-dir",
        required=True,
        type=Path,
        help="private staging directory for verified inputs",
    )
    parser.add_argument(
        "--cirros-local-input",
        type=Path,
        default=None,
        help="admit an already-present reviewed CirrOS image instead of downloading",
    )
    parser.add_argument(
        "--no-cirros",
        dest="include_cirros",
        action="store_false",
        help="stage only uv and the libvirt-python closure (guest-certified run builds its own appliance)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    manifest_path = stage_live_runner_inputs(
        args.stage_dir,
        cirros_local_input=args.cirros_local_input,
        include_cirros=args.include_cirros,
    )
    print(str(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
