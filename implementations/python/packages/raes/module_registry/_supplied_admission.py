"""Digest-pin and lock-record admission for imports read from supplied sources (ADR-119 section 3).

The refusal messages are fixed. They never contain an import source, a pin or a
lock value, because a consumer can show them to a person who did not supply them.
"""

from __future__ import annotations

import re

from .._errors import SDLImportError, SDLImportErrorCode
from ..scenario import ImportDecl
from .models import Lockfile, ResolvedModule

_PIN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


def require_import_pin(import_decl: ImportDecl) -> str:
    """Return the well-formed digest pin of one supplied import, or refuse the import."""

    pin = import_decl.digest
    if not pin:
        raise SDLImportError(SDLImportErrorCode.DIGEST_MISSING, "A supplied import must have a digest pin.")
    if _PIN.fullmatch(pin) is None:
        raise SDLImportError(
            SDLImportErrorCode.DIGEST_INVALID,
            "A supplied import digest pin must be sha256: and 64 lowercase hexadecimal digits.",
        )
    return pin


def require_lock_record(lockfile: Lockfile | None, resolved: ResolvedModule) -> None:
    """Require exactly one lock record for the import, and require it to agree with the resolution."""

    if lockfile is None:
        raise SDLImportError(
            SDLImportErrorCode.LOCK_MISSING, "A supplied import requires the lock beside its importing document."
        )
    import_decl = resolved.import_decl
    key = (import_decl.normalized_source, import_decl.namespace, import_decl.version or "*")
    records = [
        record for record in lockfile.imports if (record.source, record.namespace, record.requested_version) == key
    ]
    if not records:
        raise SDLImportError(SDLImportErrorCode.LOCK_RECORD_MISSING, "No lock record matches the supplied import.")
    if len(records) > 1:
        raise SDLImportError(
            SDLImportErrorCode.LOCK_AMBIGUOUS, "More than one lock record matches the supplied import."
        )
    record = records[0]
    descriptor = resolved.module_descriptor
    recorded = (
        record.resolved_source,
        record.module_id,
        record.module_version,
        record.content_digest,
        record.export_hash,
        record.manifest_digest,
        record.signer_id,
    )
    # A local record has no OCI manifest and no signer.
    expected = (
        resolved.resolved_source,
        descriptor.id,
        descriptor.version,
        resolved.content_digest,
        resolved.export_hash,
        "",
        "",
    )
    if recorded != expected:
        raise SDLImportError(
            SDLImportErrorCode.LOCK_MISMATCH, "The lock record does not agree with the supplied import."
        )
