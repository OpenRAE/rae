"""Evidence checks: is a named artifact actually a validated payload of a contract?

Every check here answers with a stable reason string or ``None``. Nothing is
trusted: an artifact counts only once the published schema has been run over it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from tools.policy.common import PolicyFailure, load_bounded_json_object, load_yaml, safe_repo_path
from tools.schema_coverage._keys import (
    ASSURANCE_FULFILLMENT_RELATIVE_PATH,
    CATALOG_RULE_ID,
    CONTRACTS_ROOT,
    DEFS_PREFIX,
    JSON_SUFFIX,
    MAX_POINTER_LENGTH,
    MAX_SCHEMA_BYTES,
    MAX_SOURCE_BYTES,
    METASCHEMA,
    VERSION_SUFFIX,
)
from tools.tooling_artifact_policy_common import is_regular_repo_file

__all__ = [
    "check_embedded_source",
    "check_fixture_source",
    "check_source_path",
    "contract_version_forms",
    "declares_contract",
    "formal_artifact_paths",
    "resolve_pointer",
]


def first_reason(checks: tuple[Callable[[], str | None], ...]) -> str | None:
    """Return the first check's reason, or None when every check is satisfied."""

    for check in checks:
        reason = check()
        if reason is not None:
            return reason
    return None


def contract_version_forms(contract_id: str) -> frozenset[str]:
    """Return the ``schema_version`` spellings that identify ``contract_id``.

    Published schemas spell their own version with a slash
    (``operation-status/v1``) while the publication record and schema filename
    use a hyphen (``operation-status-v1``). Both identify one contract.
    """

    match = VERSION_SUFFIX.match(contract_id)
    if match is None:
        return frozenset({contract_id})
    return frozenset({contract_id, f"{match['base']}/{match['version']}"})


def declares_contract(payload: object, forms: frozenset[str]) -> bool:
    """Whether the document as a whole claims to be a payload of the contract.

    The claim must be the document's own ``schema_version``. A contract id found
    deeper — an element of a declared-contract list, a member of a carrier, a
    prose mention — is not this document claiming to be that contract. A payload
    that genuinely lives inside a carrier is named by its node with an
    ``embedded`` source instead, so it is validated as the thing it is rather
    than dragging its carrier through the wrong schema.
    """

    return isinstance(payload, dict) and payload.get("schema_version") in forms


def formal_artifact_paths(repo_root: Path) -> tuple[frozenset[str], list[PolicyFailure]]:
    """Delivered assurance-artifact paths from the canonical fulfillment map.

    Waived artifacts are deliberately excluded: a dated, tracked waiver records
    an unresolved obligation. A missing fulfillment map is not an error here —
    this gate never requires a formal model.
    """

    path = repo_root / ASSURANCE_FULFILLMENT_RELATIVE_PATH
    if not path.is_file():
        return frozenset(), []
    try:
        document = load_yaml(path)
    except (OSError, yaml.YAMLError):
        failure = PolicyFailure(
            CATALOG_RULE_ID,
            "assurance fulfillment map is not readable valid YAML",
            ASSURANCE_FULFILLMENT_RELATIVE_PATH,
        )
        return frozenset(), [failure]
    entries = document.get("entries")
    delivered = (
        {
            artifact["path"]
            for entry in entries
            if isinstance(entry, dict)
            for artifact in (entry.get("delivered_artifacts") or [])
            if isinstance(artifact, dict) and isinstance(artifact.get("path"), str)
        }
        if isinstance(entries, list)
        else set()
    )
    return frozenset(delivered), []


def check_source_path(repo_root: Path, relative_path: object) -> str | None:
    """Return a stable reason the source path is unusable, or None when it is safe."""

    if not isinstance(relative_path, str) or not relative_path:
        return "source path must be a non-empty string"
    return first_reason(
        (
            lambda: (
                f"source path must be a normalized repo-relative path: {relative_path}"
                if relative_path != Path(relative_path).as_posix() or relative_path.startswith("/")
                else None
            ),
            lambda: (
                f"source path escapes the repository: {relative_path}"
                if safe_repo_path(repo_root, relative_path) is None
                else None
            ),
            lambda: (
                f"source path is not a regular in-repository file: {relative_path}"
                if not is_regular_repo_file(repo_root, relative_path)
                else None
            ),
        )
    )


def _definition_wrapper(root: dict[str, object], schema_pointer: str) -> tuple[dict[str, object] | None, str | None]:
    """Wrap one published ``$defs`` entry so its ``$ref`` resolves locally."""

    definitions = root.get("$defs")
    name = schema_pointer[len(DEFS_PREFIX) :]
    if not isinstance(definitions, dict) or name not in definitions:
        return None, f"schema pointer names no published definition: {schema_pointer}"
    return {"$schema": root.get("$schema", METASCHEMA), "$defs": definitions, "$ref": schema_pointer}, None


def _published_validator(
    repo_root: Path, schema_path: str, schema_pointer: str | None
) -> tuple[Draft202012Validator | None, str | None]:
    """Build a validator for the published schema, or for one of its published ``$defs``.

    Resolution is local: the wrapper copies the root ``$defs`` so a ``$ref`` in
    the named sub-schema resolves without any network or registry lookup.
    """

    try:
        root = load_bounded_json_object(repo_root, schema_path, max_bytes=MAX_SCHEMA_BYTES)
    except ValueError:
        return None, f"published schema is not a readable bounded JSON object: {schema_path}"
    if schema_pointer is None:
        return Draft202012Validator(root), None
    wrapper, reason = _definition_wrapper(root, schema_pointer)
    return (None, reason) if reason is not None else (Draft202012Validator(wrapper), None)


def _conformance_reason(validator: Draft202012Validator, payload: object, relative_path: str) -> str | None:
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if not errors:
        return None
    # Bounded, path-only diagnostics: never echo the payload or the validator message body.
    location = "/".join(str(part) for part in errors[0].path) or "<root>"
    return f"source does not conform to the published schema at {location}: {relative_path}"


def _validated(
    repo_root: Path,
    payload: object,
    schema_path: str,
    schema_pointer: str | None,
    relative_path: str,
) -> str | None:
    validator, reason = _published_validator(repo_root, schema_path, schema_pointer)
    return reason if reason is not None else _conformance_reason(validator, payload, relative_path)


def _bounded_document(
    repo_root: Path, relative_path: str, label: str, max_bytes: int
) -> tuple[dict[str, object] | None, str | None]:
    """Load one bounded repository JSON object, or say why it could not be read."""

    try:
        return load_bounded_json_object(repo_root, relative_path, max_bytes=max_bytes), None
    except ValueError:
        return None, f"{label} source is not a readable bounded JSON object: {relative_path}"


def _contracts_json_reason(relative_path: str, label: str) -> str | None:
    if relative_path.startswith(CONTRACTS_ROOT) and relative_path.endswith(JSON_SUFFIX):
        return None
    return f"{label} source must be a JSON artifact under {CONTRACTS_ROOT}: {relative_path}"


def check_fixture_source(
    repo_root: Path,
    relative_path: str,
    forms: frozenset[str],
    schema_path: str,
) -> str | None:
    """A fixture source is evidence only if it is a payload of the contract that validates.

    Carrying the contract id is an identity claim, not evidence. The gate proves
    the claim here by validating the document against the checked-in published
    schema, so a deliberately invalid document can never stand in as coverage.
    """

    return first_reason(
        (
            lambda: _contracts_json_reason(relative_path, "fixture"),
            lambda: _fixture_evidence_reason(repo_root, relative_path, forms, schema_path),
        )
    )


def _fixture_evidence_reason(
    repo_root: Path, relative_path: str, forms: frozenset[str], schema_path: str
) -> str | None:
    payload, load_reason = _bounded_document(repo_root, relative_path, "fixture", MAX_SOURCE_BYTES)
    if load_reason is not None:
        return load_reason
    if not declares_contract(payload, forms):
        return f"fixture source does not carry a payload of this contract: {relative_path}"
    return _validated(repo_root, payload, schema_path, None, relative_path)


def resolve_pointer(payload: object, pointer: str) -> tuple[object, bool]:
    """Resolve an RFC 6901 pointer against a loaded document."""

    node = payload
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return None, False
    return node, True


def _pointer_reason(pointer: object, relative_path: str) -> str | None:
    valid = isinstance(pointer, str) and pointer.startswith("/") and len(pointer) <= MAX_POINTER_LENGTH
    if valid:
        return None
    return f"embedded source needs an RFC 6901 pointer into the carrier: {relative_path}"


def _schema_pointer_reason(schema_pointer: object, relative_path: str) -> str | None:
    if schema_pointer is None:
        return None
    valid = (
        isinstance(schema_pointer, str)
        and schema_pointer.startswith(DEFS_PREFIX)
        and len(schema_pointer) <= MAX_POINTER_LENGTH
    )
    if valid:
        return None
    return f"embedded schema pointer must name a published definition: {relative_path}"


def check_embedded_source(
    repo_root: Path,
    relative_path: str,
    schema_path: str,
    pointer: object,
    schema_pointer: object,
) -> str | None:
    """An embedded source is evidence only if the pointed-to node validates.

    Some contracts are realized as a node inside a carrier rather than as a
    standalone document — the ``x-raes-invariants`` entries published inside
    other schemas, for example. The carrier and the exact node are named here and
    the gate validates that node against the published shape, so breaking or
    deleting the annotation turns the gate red.
    """

    return first_reason(
        (
            lambda: _contracts_json_reason(relative_path, "embedded"),
            lambda: _pointer_reason(pointer, relative_path),
            lambda: _schema_pointer_reason(schema_pointer, relative_path),
            lambda: _embedded_evidence_reason(repo_root, relative_path, schema_path, pointer, schema_pointer),
        )
    )


def _embedded_evidence_reason(
    repo_root: Path,
    relative_path: str,
    schema_path: str,
    pointer: object,
    schema_pointer: object,
) -> str | None:
    carrier, load_reason = _bounded_document(repo_root, relative_path, "embedded", MAX_SCHEMA_BYTES)
    if load_reason is not None:
        return load_reason
    node, found = resolve_pointer(carrier, str(pointer))
    if not found:
        return f"embedded pointer {pointer} resolves to nothing in {relative_path}"
    return _validated(repo_root, node, schema_path, schema_pointer, relative_path)
