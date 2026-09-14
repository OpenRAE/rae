"""Local, locked, and OCI import resolution orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack
from urllib.parse import quote

from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from .._errors import SDLParseDiagnostic, SDLParseError
from .._source_profile import DEFAULT_SOURCE_PARSE_OPTIONS, SDLSourceParseOptions
from ..scenario import ImportDecl, ModuleDescriptor, Scenario
from ._constants import LOCKFILE_NAME, OCI_BUNDLE_MEDIA_TYPE, OCI_LAYOUT_MEDIA_TYPE
from ._digests import _SHA256_PREFIX, _descriptor_digest, _normalize_exact_or_range, _satisfies_version
from ._verified_sources import _local_resolved_source, _VerifiedSourceBundle
from .models import (
    Lockfile,
    LockRecord,
    ResolvedModule,
    TrustPolicy,
    _scenario_module_descriptor,
    load_trust_policy,
)

# The private digest/signature seams (``_sha256_digest``, ``_json_request``,
# ``_bytes_request``, ``_extract_bundle_to_cache``, ``_verify_signatures``,
# ``_OCI_LIMITS``) are resolved through the package facade with function-local
# ``from . import`` at each use, rather than bound here from the submodules. A test
# that patches ``raes.module_registry.<seam>`` then replaces the binding these
# production calls use, exactly as the pre-split single-file module did.


@dataclass(frozen=True)
class _ResolutionContext:
    """Invariant options shared by locked, local, and OCI resolution."""

    base_dir: Path
    lockfile: Lockfile | None
    trust_policy: TrustPolicy
    source_options: SDLSourceParseOptions
    source_diagnostics: list[SDLParseDiagnostic] | None
    verified_sources: _VerifiedSourceBundle | None
    registry_base_dir: Path | None


class _ResolutionPrivateOptions(TypedDict, total=False):
    """Compatibility names for descriptor-bound internal resolution state."""

    verified_sources: _VerifiedSourceBundle | None
    _registry_base_dir: Path | None


def _parse_oci_source(source: str) -> tuple[str, str]:
    ref = source.removeprefix("oci:")
    if "://" in ref:
        ref = ref.split("://", 1)[1]
    if "/" not in ref:
        raise SDLParseError(f"Invalid OCI source '{source}'")
    registry, repository = ref.split("/", 1)
    if not registry or not repository:
        raise SDLParseError(f"Invalid OCI source '{source}'")
    return registry, repository


def _registry_base_url(registry: str, *, allow_insecure_http: bool) -> str:
    # Honor an already scheme-qualified registry as-is; otherwise build the scheme
    # from a variable so the clear-text ``http`` transport is selected only for the
    # explicit ``allow_insecure_http`` opt-in or loopback hosts, defaulting to
    # ``https`` for every other registry.
    scheme_sep = "://"
    scheme_end = registry.find(scheme_sep)
    if scheme_end != -1 and registry[:scheme_end] in ("http", "https"):
        return registry.rstrip("/")
    loopback = registry.startswith(("localhost:", "127.0.0.1:", "localhost/", "127.0.0.1/"))
    scheme = "http" if allow_insecure_http or loopback else "https"
    return f"{scheme}{scheme_sep}{registry}".rstrip("/")


def _parse_versioned_tags(tags: list[str]) -> list[tuple[Version, str]]:
    parsed: list[tuple[Version, str]] = []
    for tag in tags:
        try:
            parsed.append((Version(tag), tag))
        except InvalidVersion:
            continue
    return parsed


def _select_tag(tags: list[str], requested_version: str) -> str:
    spec = _normalize_exact_or_range(requested_version)
    parsed = _parse_versioned_tags(tags)
    if spec is None:
        if parsed:
            return max(parsed)[1]
        if tags:
            return max(tags)
        raise SDLParseError("OCI module has no published tags")
    matching = [(version, tag) for version, tag in parsed if version in spec]
    if matching:
        return max(matching)[1]
    raise SDLParseError(f"No OCI module tag satisfies requested version '{requested_version}'")


def _lock_record_for(lockfile: Lockfile | None, import_decl: ImportDecl) -> LockRecord | None:
    if lockfile is None:
        return None
    for record in lockfile.imports:
        if (
            record.source == import_decl.normalized_source
            and record.namespace == import_decl.namespace
            and record.requested_version == (import_decl.version or "*")
        ):
            return record
    return None


def _verify_allowed_parameters(
    import_decl: ImportDecl,
    descriptor: ModuleDescriptor,
) -> None:
    allowed = set(descriptor.parameters)
    disallowed = sorted(name for name in import_decl.parameters if name not in allowed)
    if disallowed:
        raise SDLParseError(f"Import parameters not allowed by module '{descriptor.id}': " + ", ".join(disallowed))


def _validate_digest_pin(actual_digest: str, expected_digest: str, *, source: str) -> None:
    if not expected_digest:
        return
    normalized_actual = actual_digest.removeprefix(_SHA256_PREFIX)
    normalized_expected = expected_digest.removeprefix(_SHA256_PREFIX)
    if normalized_actual != normalized_expected:
        raise SDLParseError(f"Digest mismatch for import '{source}': {expected_digest!r} != {actual_digest!r}")


def resolve_import(
    import_decl: ImportDecl,
    *,
    base_dir: Path,
    lockfile: Lockfile | None = None,
    trust_policy: TrustPolicy | None = None,
    source_options: SDLSourceParseOptions = DEFAULT_SOURCE_PARSE_OPTIONS,
    source_diagnostics: list[SDLParseDiagnostic] | None = None,
    **private_options: Unpack[_ResolutionPrivateOptions],
) -> ResolvedModule:
    context = _ResolutionContext(
        base_dir=base_dir,
        lockfile=lockfile,
        trust_policy=trust_policy or TrustPolicy(),
        source_options=source_options,
        source_diagnostics=source_diagnostics,
        verified_sources=private_options.get("verified_sources"),
        registry_base_dir=private_options.get("_registry_base_dir"),
    )
    return _resolve_import_with_context(import_decl, context)


def _resolve_import_with_context(import_decl: ImportDecl, context: _ResolutionContext) -> ResolvedModule:
    source = import_decl.normalized_source
    if source.startswith("locked:"):
        return _resolve_locked_import(import_decl, source, context=context)
    if source.startswith("local:"):
        return _resolve_local_import(import_decl, source, context=context)
    if not source.startswith("oci:"):
        raise SDLParseError(f"Unsupported import source '{source}'")
    return _resolve_oci_import(
        import_decl,
        source,
        base_dir=context.base_dir if context.registry_base_dir is None else context.registry_base_dir,
        lockfile=context.lockfile,
        trust_policy=context.trust_policy,
        source_options=context.source_options,
    )


def _resolve_locked_import(
    import_decl: ImportDecl,
    source: str,
    *,
    context: _ResolutionContext,
) -> ResolvedModule:
    locked_ref = source.removeprefix("locked:")
    lockfile = context.lockfile
    if lockfile is None:
        raise SDLParseError(f"Locked import '{source}' requires {LOCKFILE_NAME}")
    record = next(
        (
            candidate
            for candidate in lockfile.imports
            if candidate.resolved_source == locked_ref or candidate.source == locked_ref
        ),
        None,
    )
    if record is None:
        raise SDLParseError(f"Locked import '{source}' is not present in {LOCKFILE_NAME}")
    delegated = ImportDecl(
        source=record.source,
        namespace=import_decl.namespace or record.namespace,
        version=record.requested_version,
        parameters=dict(import_decl.parameters),
        digest=import_decl.digest or record.content_digest,
    )
    return _resolve_import_with_context(delegated, context)


def _resolve_local_import(
    import_decl: ImportDecl,
    source: str,
    *,
    context: _ResolutionContext,
) -> ResolvedModule:
    from ..parser import _load_normalized_data, read_sdl_source
    from . import _sha256_digest

    relative = source.removeprefix("local:")
    if context.verified_sources is None:
        import_path = (context.base_dir / relative).resolve()
        if not import_path.is_relative_to(context.base_dir.resolve()):
            raise SDLParseError(f"Local import path escapes base directory: {relative!r}")
        if not import_path.exists():
            raise SDLParseError(f"Imported SDL file not found: {relative}")
        imported_source = read_sdl_source(import_path, limits=context.source_options.limits)
    else:
        import_path, imported_source = context.verified_sources.resolve_local(
            base_dir=context.base_dir,
            relative=relative,
        )
    imported_raw = _load_normalized_data(
        imported_source.text,
        path=import_path,
        source_format=context.source_options.source_format,
        required_semantic_revision=context.source_options.required_semantic_revision,
        migration_policy=context.source_options.migration_policy,
        limits=context.source_options.limits,
        source_diagnostics=context.source_diagnostics,
    )
    imported_scenario = Scenario.model_validate(imported_raw)
    descriptor = _scenario_module_descriptor(
        imported_scenario,
        source_id=relative.replace("\\", "/"),
    )
    content_digest = f"{_SHA256_PREFIX}{_sha256_digest(imported_source.raw_bytes)}"
    if not _satisfies_version(descriptor.version, import_decl.version):
        raise SDLParseError(
            f"Import '{relative}' requested version {import_decl.version!r} but module declares {descriptor.version!r}"
        )
    if context.verified_sources is None and not context.trust_policy.allow_unsigned_local_sources:
        raise SDLParseError(
            "Local SDL imports are disabled by trust policy because unsigned local sources are not allowed"
        )
    _validate_digest_pin(content_digest, import_decl.digest, source=source)
    locked = _lock_record_for(context.lockfile, import_decl)
    if locked is not None and locked.content_digest:
        _validate_digest_pin(content_digest, locked.content_digest, source=source)
    _verify_allowed_parameters(import_decl, descriptor)
    return ResolvedModule(
        import_decl=import_decl,
        module_descriptor=descriptor,
        root_file=import_path,
        source_document=imported_source,
        resolved_source=_local_resolved_source(
            import_path,
            context.base_dir,
            lexical=context.verified_sources is not None,
        ),
        content_digest=content_digest,
        export_hash=_descriptor_digest(descriptor.exports),
        verified_sources=context.verified_sources,
    )


def _resolve_oci_manifest(
    *,
    base_url: str,
    repository: str,
    import_decl: ImportDecl,
    locked: LockRecord | None,
    source: str,
) -> tuple[str, dict[str, Any]]:
    from . import _bytes_request, _decode_json_object, _json_request, _sha256_digest

    manifest_ref = locked.manifest_digest if locked is not None else None
    if manifest_ref is None:
        tags_payload = _json_request(f"{base_url}/v2/{quote(repository, safe='/')}/tags/list")
        raw_tags = tags_payload.get("tags") or []
        if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
            raise SDLParseError(f"OCI tag metadata for '{source}' has an invalid tags list")
        tags = raw_tags
        manifest_ref = _select_tag(tags, import_decl.version)
    manifest_bytes = _bytes_request(
        f"{base_url}/v2/{quote(repository, safe='/')}/manifests/{quote(str(manifest_ref), safe=':@/')}",
        headers={"Accept": OCI_LAYOUT_MEDIA_TYPE},
    )
    manifest_digest = f"{_SHA256_PREFIX}{_sha256_digest(manifest_bytes)}"
    manifest = _decode_json_object(manifest_bytes, context=f"OCI manifest for '{source}'")
    if locked is not None and locked.manifest_digest != manifest_digest:
        raise SDLParseError(
            f"Lockfile digest mismatch for import '{source}': {locked.manifest_digest!r} != {manifest_digest!r}"
        )
    return manifest_digest, manifest


def _resolve_oci_config(
    *, base_url: str, repository: str, manifest: dict[str, Any], source: str
) -> tuple[dict[str, Any], str]:
    from . import _bytes_request, _decode_json_object, _sha256_digest

    config = manifest.get("config", {})
    layers = manifest.get("layers", [])
    if (
        not isinstance(config, dict)
        or not isinstance(layers, list)
        or any(not isinstance(item, dict) for item in layers)
    ):
        raise SDLParseError(f"OCI module '{source}' has malformed config or layer descriptors")
    layer = next(
        (candidate for candidate in layers if candidate.get("mediaType") == OCI_BUNDLE_MEDIA_TYPE),
        None,
    )
    if not config or not layer:
        raise SDLParseError(f"OCI module '{source}' is missing config or bundle layer")
    config_digest = str(config.get("digest", ""))
    layer_digest = str(layer.get("digest", ""))
    # Verify the config blob bytes hash to the manifest's config.digest BEFORE
    # decoding the JSON (issue #14). Fetching by digest is not integrity: a
    # compromised registry can serve arbitrary bytes for the config endpoint, and
    # those bytes carry the unsigned-by-default root_file that selects the module
    # entrypoint. Hash the exact bytes received - never a reserialized object -
    # and reuse the bundle's digest spelling.
    config_bytes = _bytes_request(
        f"{base_url}/v2/{quote(repository, safe='/')}/blobs/{quote(config_digest, safe=':@/')}"
    )
    if f"{_SHA256_PREFIX}{_sha256_digest(config_bytes)}" != config_digest:
        raise SDLParseError(f"OCI module '{source}' config digest verification failed")
    config_payload = _decode_json_object(config_bytes, context=f"OCI config for '{source}'")
    return config_payload, layer_digest


def _fetch_oci_bundle(*, base_url: str, repository: str, layer_digest: str, source: str) -> bytes:
    from . import _OCI_LIMITS, _bytes_request, _sha256_digest

    bundle_bytes = _bytes_request(
        f"{base_url}/v2/{quote(repository, safe='/')}/blobs/{quote(layer_digest, safe=':@/')}",
        max_bytes=_OCI_LIMITS.max_bundle_bytes,
    )
    if f"{_SHA256_PREFIX}{_sha256_digest(bundle_bytes)}" != layer_digest:
        raise SDLParseError(f"OCI module '{source}' bundle digest verification failed")
    return bundle_bytes


def _build_oci_descriptor(
    *,
    config_payload: dict[str, Any],
    layer_digest: str,
    import_decl: ImportDecl,
    locked: LockRecord | None,
    source: str,
) -> tuple[ModuleDescriptor, str, str]:
    try:
        descriptor = ModuleDescriptor.model_validate(config_payload.get("module", {}))
    except ValidationError as exc:
        raise SDLParseError(f"OCI module '{source}' has invalid module descriptor") from exc
    if locked is not None and locked.module_id != descriptor.id:
        raise SDLParseError(
            f"Lockfile module id mismatch for import '{source}': {locked.module_id!r} != {descriptor.id!r}"
        )
    if not _satisfies_version(descriptor.version, import_decl.version):
        raise SDLParseError(
            f"OCI import '{source}' requested version {import_decl.version!r} "
            f"but resolved module declares {descriptor.version!r}"
        )
    content_digest = layer_digest
    _validate_digest_pin(content_digest, import_decl.digest, source=source)
    # Resolve the config-declared root_file as a single string before it reaches
    # the signature payload or extraction (issue #14). Signing and extracting the
    # SAME value closes the gap where a signature verified over a default root_file
    # while a different attacker-declared root_file was extracted.
    raw_root_file = config_payload.get("root_file", "module.yaml")
    if not isinstance(raw_root_file, str):
        raise SDLParseError(f"OCI module '{source}' declares a non-string root_file")
    return descriptor, content_digest, raw_root_file


def _resolve_oci_import(
    import_decl: ImportDecl,
    source: str,
    *,
    base_dir: Path,
    lockfile: Lockfile | None,
    trust_policy: TrustPolicy,
    source_options: SDLSourceParseOptions,
) -> ResolvedModule:
    from . import _extract_bundle_to_cache, _verify_signatures

    registry, repository = _parse_oci_source(source)
    registry_policy = trust_policy.registries.get(registry)
    if registry_policy is None:
        raise SDLParseError(f"Registry '{registry}' is not allowed by trust policy")
    base_url = _registry_base_url(registry, allow_insecure_http=registry_policy.allow_insecure_http)
    locked = _lock_record_for(lockfile, import_decl)
    manifest_digest, manifest = _resolve_oci_manifest(
        base_url=base_url, repository=repository, import_decl=import_decl, locked=locked, source=source
    )
    config_payload, layer_digest = _resolve_oci_config(
        base_url=base_url, repository=repository, manifest=manifest, source=source
    )
    bundle_bytes = _fetch_oci_bundle(base_url=base_url, repository=repository, layer_digest=layer_digest, source=source)
    descriptor, content_digest, root_file = _build_oci_descriptor(
        config_payload=config_payload, layer_digest=layer_digest, import_decl=import_decl, locked=locked, source=source
    )
    signer_id = ""
    if registry_policy.require_signatures:
        raw_signatures = config_payload.get("signatures", [])
        if not isinstance(raw_signatures, list) or any(not isinstance(item, dict) for item in raw_signatures):
            raise SDLParseError(f"OCI module '{source}' has malformed signature metadata")
        signer_id = _verify_signatures(
            signatures=raw_signatures,
            trust_policy=registry_policy,
            module_descriptor=descriptor,
            content_digest=content_digest,
            root_file=root_file,
        )
    verified_sources = _extract_bundle_to_cache(
        bundle_bytes=bundle_bytes,
        manifest_digest=manifest_digest.replace(_SHA256_PREFIX, ""),
        content_digest=content_digest,
        root_file=root_file,
        base_dir=base_dir,
        source_options=source_options,
    )
    if not isinstance(verified_sources, _VerifiedSourceBundle):
        raise SDLParseError("OCI module cache did not return verified source documents")
    resolved_root, resolved_source_document = verified_sources.resolve_local(
        base_dir=verified_sources.cache_root,
        relative=root_file,
    )
    _verify_allowed_parameters(import_decl, descriptor)
    export_hash = _descriptor_digest(descriptor.exports)
    if locked is not None and locked.export_hash != export_hash:
        raise SDLParseError(f"Lockfile export hash mismatch for import '{source}'")
    return ResolvedModule(
        import_decl=import_decl,
        module_descriptor=descriptor,
        root_file=resolved_root,
        source_document=resolved_source_document,
        resolved_source=f"{registry}/{repository}@{manifest_digest}",
        manifest_digest=manifest_digest,
        content_digest=content_digest,
        export_hash=export_hash,
        signer_id=signer_id,
        verified_sources=verified_sources,
    )


def resolve_lock_records(
    root_path: Path,
    *,
    trust_policy: TrustPolicy | None = None,
) -> Lockfile:
    from ..parser import _load_normalized_data, read_sdl_source

    trust_policy = trust_policy or load_trust_policy(root_path.parent)
    root_data = _load_normalized_data(read_sdl_source(root_path).text, path=root_path)
    imports = [ImportDecl.model_validate(item) for item in root_data.get("imports", [])]
    records: list[LockRecord] = []
    for import_decl in imports:
        resolved = resolve_import(
            import_decl,
            base_dir=root_path.parent,
            trust_policy=trust_policy,
        )
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
