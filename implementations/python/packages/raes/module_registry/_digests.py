"""Digest and version-matching helpers for module resolution."""

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version
from raes_contracts.digests import sha256_hex
from raes_contracts.json_serialization import sorted_json_text

from .._errors import SDLParseError


def _descriptor_digest(exports: dict[str, list[str]]) -> str:
    return sha256_hex(sorted_json_text(exports).encode("utf-8"))


def _normalize_exact_or_range(version: str) -> SpecifierSet | None:
    value = (version or "*").strip()
    if value in {"", "*"}:
        return None
    if any(token in value for token in "<>!=~"):
        return SpecifierSet(value)
    return SpecifierSet(f"=={value}")


def _satisfies_version(actual: str, requested: str) -> bool:
    spec = _normalize_exact_or_range(requested)
    if spec is None:
        return True
    try:
        version = Version(actual)
    except InvalidVersion:
        return actual == requested
    return version in spec


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
