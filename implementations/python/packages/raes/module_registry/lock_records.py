"""Lockfile record resolution for an SDL root's import declarations."""

from __future__ import annotations

from pathlib import Path

from .._errors import SDLSourceRange
from .._model_diagnostics import _import_declarations
from .models import Lockfile, LockRecord, TrustPolicy, load_trust_policy
from .resolution import resolve_import


def resolve_lock_records(
    root_path: Path,
    *,
    trust_policy: TrustPolicy | None = None,
) -> Lockfile:
    """Resolve the root's imports into lock records.

    The declarations and the provenance each record implies are checked as
    ``parse_sdl_file`` checks them, so a root it rejects for either reason
    never yields a lockfile.
    """

    from .._composition_provenance import _provenance_record
    from ..parser import _load_normalized_data, read_sdl_source

    trust_policy = trust_policy or load_trust_policy(root_path.parent)
    source_ranges: dict[str, SDLSourceRange] = {}
    root_data = _load_normalized_data(read_sdl_source(root_path).text, path=root_path, source_ranges=source_ranges)
    imports = _import_declarations(root_data, path=root_path, source_ranges=source_ranges)
    records: list[LockRecord] = []
    for import_decl in imports:
        resolved = resolve_import(
            import_decl,
            base_dir=root_path.parent,
            trust_policy=trust_policy,
        )
        _provenance_record(resolved, requested=import_decl, path=root_path)
        records.append(
            LockRecord(
                source=import_decl.normalized_source,
                namespace=import_decl.namespace,
                requested_version=import_decl.version or "*",
                resolved_source=resolved.resolved_source,
                module_id=resolved.module_descriptor.id,
                module_version=resolved.module_descriptor.version,
                manifest_digest=resolved.manifest_digest,
                content_digest=resolved.content_digest,
                export_hash=resolved.export_hash,
                signer_id=resolved.signer_id,
            )
        )
    return Lockfile(imports=records)
