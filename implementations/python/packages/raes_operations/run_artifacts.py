"""Shared run-archive helpers for operational proof artifacts.

Both the TechVault native live gate and the libvirt scenario-evidence producer write
JSON artifacts under a ``runs/<run-id>/<subdir>/`` archive. They share one
definition of a safe run-id filesystem label and one atomic JSON writer here
rather than carrying parallel copies.

The run-id label rule matches the historical TechVault convention
(``^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$``): a leading alphanumeric, then up to 127
characters drawn from alphanumerics, underscore, dot, and hyphen. It rejects path
separators, ``..`` traversal, and leading dots so a caller-supplied run id can
never escape the archive directory.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord

RUN_ID_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def is_valid_run_id_label(run_id: str) -> bool:
    """Return True when ``run_id`` is a safe, containment-validated filesystem label."""
    return bool(RUN_ID_LABEL_PATTERN.fullmatch(run_id))


def portable_artifact_ref(path: Path) -> str:
    """Return a repository-portable reference without exposing a host path."""

    for anchor in ("examples", "contracts", "specs", "docs"):
        if anchor in path.parts:
            return "/".join(path.parts[path.parts.index(anchor) :])
    return path.name


def run_artifact_path(output_dir: Path, run_id: str, subdir: str, filename: str) -> Path:
    """Return the archive path ``<output_dir>/runs/<run_id>/<subdir>/<filename>``.

    Raises ``ValueError`` when ``run_id`` is not a safe filesystem label so the
    path is never constructed from an unvalidated label.
    """
    if not is_valid_run_id_label(run_id):
        raise ValueError("run id must be a safe filesystem label")
    return output_dir / "runs" / run_id / subdir / filename


def serialize_run_artifact(payload: Mapping[str, Any]) -> str:
    """Serialize a run artifact to canonical JSON text (indent=2, sorted keys, trailing newline)."""
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def atomic_write_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write ``payload`` as canonical JSON to ``path``.

    Creates the parent directory, writes to a temp file in the same directory, then
    ``os.replace`` to swap it into place so a reader never observes a partial write.
    Cleans up the temp file on any failure before re-raising.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = serialize_run_artifact(payload)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


class RunMaterializationArchive:
    """Publish admitted SDL through the run archive's protected byte boundary.

    Publication precedes the caller's durable reference commit. An identical
    retry is safe; a conflicting identity is never overwritten. This is not a
    transaction with an operation store and never retries materialization.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)

    def publish(self, content: str) -> MaterializationArchiveRecord:
        from raes.canonical import canonical_materialized_sdl_digest
        from raes.formatting import render_sdl_source
        from raes.materialization import MaterializedScenario
        from raes.parser import parse_sdl
        from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord

        try:
            scenario = parse_sdl(content)
            if not isinstance(scenario, MaterializedScenario):
                raise ValueError("not a materialization description")
            provenance = scenario.materialization_provenance
            if not is_valid_run_id_label(provenance.run_id):
                raise ValueError("unsafe run identity")
            data = render_sdl_source(scenario).content.encode("utf-8")
        except Exception:
            raise ValueError("materialization archive requires valid bounded SDL and safe identities") from None
        relative = Path("runs") / provenance.run_id / "attestations" / f"{provenance.attestation_id}.sdl"
        record = MaterializationArchiveRecord.model_validate(
            {
                "reference": {
                    "ref_id": provenance.attestation_id,
                    "ref_digest": canonical_materialized_sdl_digest(scenario).value,
                    "ref_path": relative.as_posix(),
                },
                "artifact": {
                    "artifact_id": provenance.attestation_id,
                    "role": "materialization-attestation",
                    "media_type": "application/vnd.raes.sdl+yaml",
                    "uri": "urn:sha256:" + hashlib.sha256(data).hexdigest(),
                    "checksum": {"algorithm": "sha256", "value": hashlib.sha256(data).hexdigest()},
                    "size_bytes": len(data),
                    "created_at": provenance.recorded_at.isoformat(),
                    "source": provenance.producer.name,
                    "sensitivity": "restricted",
                },
                "run_id": provenance.run_id,
                "operation_id": provenance.operation_id,
            }
        )
        self.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = os.open(self.output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in relative.parts[:-1]:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=directory)
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            _publish_immutable_bytes(directory, relative.name, data)
        finally:
            os.close(directory)
        return record


def _verify_immutable_bytes(directory: int, name: str, data: bytes) -> None:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("materialization archive artifact is not a protected regular file")
        if info.st_size != len(data) or handle.read(len(data) + 1) != data:
            raise ValueError("materialization archive identity already binds different bytes")


def _publish_immutable_bytes(directory: int, name: str, data: bytes) -> None:
    temporary = f".attestation-{uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        except FileExistsError:
            _verify_immutable_bytes(directory, name, data)
        os.fsync(directory)
        _verify_immutable_bytes(directory, name, data)
    finally:
        os.unlink(temporary, dir_fd=directory)
