"""ADR-036 module-boundary decision for one import of a first-party module.

The static module-boundary check and the ADR-117 hidden-import check use this one
decision, so a dynamic import meets the same rules as a static one: forbidden
prefixes, private module paths, public prefixes and allowed packages.
"""

from __future__ import annotations

from collections.abc import Mapping

RULE_IMPORT = "module-boundary-import"
RULE_PRIVATE_IMPORT = "module-boundary-private-import"
RULE_PUBLIC_API = "module-boundary-public-api"


def boundary_violation(
    rule: Mapping[str, object], known_modules: frozenset[str], imported: str
) -> tuple[str, str] | None:
    """Return the rule id and the message for an import that the module boundary refuses, else ``None``.

    ``rule`` has the keys ``id``, ``allowed_top_level_imports``, ``forbidden_import_prefixes`` and
    ``public_import_prefixes``. An import of the module's own package or of an unknown package is
    not checked. The checks run in this order, and the first refusal wins.
    """

    module_id = str(rule["id"])
    top_level = imported.split(".", 1)[0]
    if top_level == module_id or top_level not in known_modules:
        return None
    checks = (_forbidden_prefix, _private_path, _public_prefix, _allowed_package)
    return next((found for check in checks if (found := check(rule, module_id, top_level, imported)) is not None), None)


def _forbidden_prefix(
    rule: Mapping[str, object], module_id: str, top_level: str, imported: str
) -> tuple[str, str] | None:
    if not matches_any_import_prefix(imported, tuple(rule["forbidden_import_prefixes"])):  # type: ignore[arg-type]
        return None
    return (
        RULE_IMPORT,
        f"{module_id} must not import {imported!r}; module-boundary rules are defined by module_boundaries",
    )


def _private_path(rule: Mapping[str, object], module_id: str, top_level: str, imported: str) -> tuple[str, str] | None:
    if not uses_private_module_path(imported):
        return None
    return RULE_PRIVATE_IMPORT, f"{module_id} must not import private/internal module path {imported!r}"


def _public_prefix(rule: Mapping[str, object], module_id: str, top_level: str, imported: str) -> tuple[str, str] | None:
    public_prefixes = rule["public_import_prefixes"].get(top_level)  # type: ignore[attr-defined]
    if not public_prefixes or matches_any_import_prefix(imported, tuple(public_prefixes)):
        return None
    return (
        RULE_PUBLIC_API,
        f"{module_id} may import {top_level} only through public prefixes {sorted(public_prefixes)!r}",
    )


def _allowed_package(
    rule: Mapping[str, object], module_id: str, top_level: str, imported: str
) -> tuple[str, str] | None:
    if top_level in rule["allowed_top_level_imports"]:  # type: ignore[operator]
        return None
    return RULE_IMPORT, f"{module_id} may not import {top_level}; add an ADR-backed module-boundary allowance first"


def matches_any_import_prefix(imported: str, prefixes: tuple[str, ...]) -> bool:
    return any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes)


def uses_private_module_path(imported: str) -> bool:
    return any(part.startswith("_") for part in imported.split(".")[1:])


__all__ = [
    "RULE_IMPORT",
    "RULE_PRIVATE_IMPORT",
    "RULE_PUBLIC_API",
    "boundary_violation",
    "matches_any_import_prefix",
    "uses_private_module_path",
]
