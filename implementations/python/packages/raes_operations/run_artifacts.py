"""Shared run-archive helpers for protected run records.

``RunMaterializationArchive`` is the portable materialization archive that
``RuntimeManager`` and ``RuntimeControlPlane`` accept. It publishes admitted SDL
under a ``runs/<run-id>/attestations/`` archive and validates every path from a
safe run-id filesystem label.

The run-id label rule is ``^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$``: a leading
alphanumeric, then up to 127 characters drawn from alphanumerics, underscore,
dot, and hyphen. It rejects path separators, ``..`` traversal, and leading dots
so a caller-supplied run id can never escape the archive directory.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import os
import re
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError, OperationalError

if TYPE_CHECKING:
    from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord
    from raes_contracts.materialization import MaterializationSubmission

RUN_ID_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PUBLICATION_REFUSED = "materialization archive requires valid bounded SDL and safe identities"
# A missing file, a changed permission, or a symbolic link: an open with O_NOFOLLOW reports a link
# with ELOOP, or with ENOTDIR under O_DIRECTORY.
_RETAINED_ARTIFACT_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.EACCES, errno.EPERM})


def is_valid_run_id_label(run_id: str) -> bool:
    """Return True when ``run_id`` is a safe, containment-validated filesystem label."""
    return bool(RUN_ID_LABEL_PATTERN.fullmatch(run_id))


def _materialization_record_path(record: MaterializationArchiveRecord) -> Path:
    relative = Path(record.reference.ref_path)
    expected = Path("runs") / record.run_id / "attestations" / f"{record.reference.ref_id}.sdl"
    if (
        not is_valid_run_id_label(record.run_id)
        or not is_valid_run_id_label(record.reference.ref_id)
        or relative != expected
        or relative.parts[:3] != ("runs", record.run_id, "attestations")
        or any(component in {".", ".."} for component in relative.parts)
        or len(relative.parts) != 4
    ):
        raise EvidenceIntegrityError("materialization archive record names an invalid archive path")
    return relative


@contextlib.contextmanager
def _archive_storage_refusals(*, retained: bool) -> Iterator[None]:
    """Classify a filesystem failure of the archive (E9).

    Under ``retained``, a missing artifact, a replaced directory, a changed permission or a
    planted symbolic link means that the archive does not hold the protected files that it
    created. Any other failure, and any failure outside ``retained``, is a host failure.
    """

    try:
        yield
    except OSError as exc:
        if retained and exc.errno in _RETAINED_ARTIFACT_ERRNOS:
            raise EvidenceIntegrityError("materialization archive artifact is not the retained protected file") from exc
        raise OperationalError("materialization archive storage operation failed") from exc


class RunMaterializationArchive:
    """Publish admitted SDL through the run archive's protected byte boundary.

    Publication precedes the caller's durable reference commit. An identical
    retry is safe; a conflicting identity is never overwritten. This is not a
    transaction with an operation store and never retries materialization.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)

    def read(self, record: MaterializationArchiveRecord) -> MaterializationSubmission:
        """Resolve only protected, bounded bytes named by a validated archive record."""
        from raes_contracts.materialization import (
            MATERIALIZATION_MAX_BYTES,
            MaterializationSubmission,
            require_materialization_records,
        )

        # The record is retained evidence; its validators refuse an invalid record with ValueError (E3).
        try:
            require_materialization_records((record,))
        except ValueError as exc:
            raise EvidenceIntegrityError("materialization archive record failed its contract check") from exc
        relative = _materialization_record_path(record)
        with _archive_storage_refusals(retained=False):
            directory = os.open(self.output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with _archive_storage_refusals(retained=True):
                for component in relative.parts[:-1]:
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    os.close(directory)
                    directory = child
                descriptor = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(descriptor, "rb") as handle:
                    info = os.fstat(handle.fileno())
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_size > MATERIALIZATION_MAX_BYTES
                    ):
                        raise EvidenceIntegrityError("materialization archive is not a bounded protected regular file")
                    data = handle.read(MATERIALIZATION_MAX_BYTES + 1)
        finally:
            os.close(directory)
        if (
            len(data) != record.artifact.size_bytes
            or hashlib.sha256(data).hexdigest() != record.artifact.checksum.value
        ):
            raise EvidenceIntegrityError("materialization archive bytes do not match the retained record")
        # Bytes that match the record but are not bounded UTF-8 SDL text are not a valid retained artifact.
        try:
            return MaterializationSubmission(sdl=data.decode("utf-8"))
        except ValueError as exc:
            raise EvidenceIntegrityError("materialization archive bytes are not a valid submission") from exc

    def publish(self, content: str) -> MaterializationArchiveRecord:
        from raes.canonical import canonical_materialized_sdl_digest
        from raes.formatting import render_sdl_source
        from raes.materialization import MaterializedScenario
        from raes.parser import parse_sdl
        from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord

        # SDL failures are InvalidInputError; ``from None`` keeps authored values out of the refusal.
        try:
            scenario = parse_sdl(content)
        except InvalidInputError:
            raise InvalidInputError(_PUBLICATION_REFUSED) from None
        if not isinstance(scenario, MaterializedScenario) or not is_valid_run_id_label(
            scenario.materialization_provenance.run_id
        ):
            raise InvalidInputError(_PUBLICATION_REFUSED)
        provenance = scenario.materialization_provenance
        try:
            data = render_sdl_source(scenario).content.encode("utf-8")
        except InvalidInputError:
            raise InvalidInputError(_PUBLICATION_REFUSED) from None
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
                "inventory": provenance.inventory,
            }
        )
        with _archive_storage_refusals(retained=False):
            self.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory = os.open(self.output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            # Below its root, the archive holds only directories and artifacts that it created.
            with _archive_storage_refusals(retained=True):
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
            raise EvidenceIntegrityError("materialization archive artifact is not a protected regular file")
        if info.st_size != len(data) or handle.read(len(data) + 1) != data:
            raise ConflictError("materialization archive identity already binds different bytes")


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
