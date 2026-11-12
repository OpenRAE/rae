"""Shared primitives for the closed development artifact-policy validator."""

from __future__ import annotations

import re
import stat
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402

from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path  # noqa: E402

TOOLING_ROOT = "implementations/tooling"
ARTIFACT_LOCK_PATH = f"{TOOLING_ROOT}/artifacts.lock.json"
PROFILES_PATH = f"{TOOLING_ROOT}/profiles/development-profiles.json"
ADMISSION_POLICY_PATH = f"{TOOLING_ROOT}/admission-policy.json"
SELECTOR_BINDINGS_PATH = f"{TOOLING_ROOT}/selector-bindings.json"

POLICY_SCHEMAS = {
    ARTIFACT_LOCK_PATH: f"{TOOLING_ROOT}/schemas/artifact-lock.schema.json",
    PROFILES_PATH: f"{TOOLING_ROOT}/schemas/profiles.schema.json",
    ADMISSION_POLICY_PATH: f"{TOOLING_ROOT}/schemas/admission-policy.schema.json",
    SELECTOR_BINDINGS_PATH: f"{TOOLING_ROOT}/schemas/selector-bindings.schema.json",
}
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SCANNED_FILE_BYTES = 2 * 1024 * 1024
_INVALID_AUTHORITY = "tooling authority is missing, unsafe, or malformed"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
TOML_SUFFIX = ".toml"
YAML_SUFFIXES = frozenset({".yaml", ".yml"})
FORBIDDEN_EXECUTABLE_KEYS = frozenset(
    {
        "argv",
        "command",
        "commands",
        "exec",
        "hook",
        "hooks",
        "install_command",
        "post_install",
        "pre_install",
        "script",
        "shell",
    }
)
MUTABLE_SELECTORS = frozenset({"dev", "head", "latest", "main", "master", "nightly", "stable"})
SECRET_QUERY_KEYS = frozenset(
    {
        "access_token",
        "apikey",
        "api_key",
        "auth",
        "key",
        "password",
        "secret",
        "sig",
        "signature",
        "token",
    }
)


def failure(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def normalize_platform_id(value: str) -> str:
    """Return the canonical OS/architecture identity used by the lock."""

    normalized = value.strip().lower().replace("_", "-")
    parts = [part for part in normalized.split("-") if part]
    os_aliases = {"darwin": "macos", "mac": "macos", "osx": "macos"}
    arch_aliases = {
        "64-bit": "x86-64",
        "aarch64": "arm64",
        "amd64": "x86-64",
        "x64": "x86-64",
        "x86_64": "x86-64",
    }
    if parts:
        parts[0] = os_aliases.get(parts[0], parts[0])
    if len(parts) >= 2:
        arch = arch_aliases.get("-".join(parts[1:]), "-".join(parts[1:]))
        parts = [parts[0], arch]
    return "-".join(parts).replace("x86-64", "x86_64")


def load_documents(
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], list[PolicyFailure]]:
    """Load and locally validate every closed policy document."""

    try:
        __import__("jsonschema")
    except ModuleNotFoundError:
        return {}, [
            failure(
                "tooling-validator-unavailable",
                "the frozen project JSON Schema validator is unavailable",
            )
        ]
    documents: dict[str, dict[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for policy_path, schema_path in POLICY_SCHEMAS.items():
        unsafe_file = next(
            (
                relative_path
                for relative_path in (policy_path, schema_path)
                if not is_regular_repo_file(repo_root, relative_path)
            ),
            None,
        )
        if unsafe_file is not None:
            failures.append(
                failure(
                    "tooling-json-file",
                    "policy authorities must be bounded regular files inside the repository",
                    unsafe_file,
                )
            )
            continue
        try:
            document = load_bounded_json_object(repo_root, policy_path, max_bytes=MAX_JSON_BYTES)
            schema = load_bounded_json_object(repo_root, schema_path, max_bytes=MAX_JSON_BYTES)
        except (OSError, InvalidInputError):
            failures.append(
                failure(
                    "tooling-json-parse",
                    "policy or schema could not be loaded and parsed safely",
                    policy_path,
                )
            )
            continue
        documents[policy_path] = document
        failures.extend(_schema_failures(document, schema, policy_path, schema_path))
    return documents, failures


def read_tooling_document(repo_root: Path, path: str) -> dict[str, Any]:
    """Read one bounded, duplicate-free authority without following symlinks."""

    if not is_regular_repo_file(repo_root, path):
        raise InvalidInputError(_INVALID_AUTHORITY)
    try:
        return load_bounded_json_object(repo_root, path, max_bytes=MAX_JSON_BYTES)
    except (OSError, InvalidInputError, RecursionError):
        raise InvalidInputError(_INVALID_AUTHORITY) from None


def validate_tooling_record(
    repo_root: Path,
    document: Mapping[str, Any],
    policy_path: str,
    *,
    definition: str | None = None,
) -> None:
    """Reuse an authority's schema for a document or a selected record."""

    schema_path = POLICY_SCHEMAS[policy_path]
    schema = read_tooling_document(repo_root, schema_path)
    if definition is not None:
        schema = {"$ref": f"#/$defs/{definition}", "$defs": schema.get("$defs", {})}
    if _schema_failures(document, schema, policy_path, schema_path):
        raise InvalidInputError("selected tooling authority has an invalid shape")


def _schema_failures(
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
    policy_path: str,
    schema_path: str,
) -> list[PolicyFailure]:
    if contains_nonlocal_schema_reference(schema):
        message = "internal tooling schemas may use only local fragment references"
        return [failure("tooling-schema-reference", message, schema_path)]
    errors = _schema_errors(document, schema, policy_path, schema_path)
    if isinstance(errors, PolicyFailure):
        return [errors]
    return [
        failure(
            "tooling-schema",
            f"schema validation failed at {'.'.join(str(part) for part in error.absolute_path) or '<root>'}",
            policy_path,
        )
        for error in errors
    ]


def _schema_errors(
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
    policy_path: str,
    schema_path: str,
) -> list[Any] | PolicyFailure:
    """Return the validation errors of a policy document, or the failure that prevents validation."""

    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError

    try:
        from referencing.exceptions import Unresolvable
    except ModuleNotFoundError:
        # jsonschema before 4.18, such as the Ubuntu 24.04 package that the development container
        # base image uses, resolves references itself and raises RefResolutionError.
        from jsonschema.exceptions import RefResolutionError as Unresolvable

    malformed = failure("tooling-schema", "internal tooling schema is malformed or nested too deeply", schema_path)
    try:
        Draft202012Validator.check_schema(schema)
    except (SchemaError, RecursionError):
        # The metaschema check refuses a malformed keyword or pattern, and stops at the
        # recursion limit for a schema that nests too deeply.
        return malformed
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    try:
        errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    except (Unresolvable, re.error):
        # The metaschema check does not resolve references, so a dangling local $ref fails here. A
        # jsonschema release whose metaschema check does not test regular expressions (4.10 on the
        # base image) compiles a malformed schema pattern here.
        errors = malformed
    except RecursionError:
        # The validator descends once for each level where the schema and the document nest together.
        errors = failure("tooling-schema", "policy document nests too deeply to validate", policy_path)
    return errors


def is_regular_repo_file(repo_root: Path, relative_path: str) -> bool:
    """Return whether every path component is non-symlink and the leaf is regular."""

    if safe_repo_path(repo_root, relative_path) is None:
        return False
    current = repo_root.resolve()
    parts = Path(relative_path).parts
    valid = bool(parts)
    for index, part in enumerate(parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError:
            valid = False
            break
        if stat.S_ISLNK(mode) or index < len(parts) - 1 and not stat.S_ISDIR(mode):
            valid = False
            break
        if index == len(parts) - 1 and not stat.S_ISREG(mode):
            valid = False
    return valid


def contains_nonlocal_schema_reference(value: object) -> bool:
    """Return whether a schema tree contains a non-fragment reference."""

    # An explicit stack, because the JSON decoder accepts nesting beyond the interpreter recursion limit.
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            for key, child in current.items():
                if key == "$ref" and (not isinstance(child, str) or not child.startswith("#")):
                    return True
                pending.append(child)
        elif isinstance(current, list):
            pending.extend(current)
    return False


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def string_set(value: object) -> set[str]:
    return {item for item in as_list(value) if isinstance(item, str)}


def _policy_compatibility_failures(
    subject: object, evidence_compatible: bool, expected_subjects: set[str], path: str, context: str
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    # The expected subjects are text, so a subject of another type, also one that cannot be hashed, is incompatible.
    if not isinstance(subject, str) or subject not in expected_subjects:
        failures.append(
            failure("tooling-policy-subject", f"{context} admission policy has an incompatible subject", path)
        )
    if not evidence_compatible:
        message = f"{context} does not supply evidence accepted by its admission policy"
        failures.append(failure("tooling-policy-evidence", message, path))
    return failures


def policy_join_failures(
    *,
    policy_refs: set[str],
    expected_subjects: set[str],
    provided_evidence: set[str],
    policies: Mapping[str, Mapping[str, Any]],
    path: str,
    context: str,
    require_all_evidence_per_policy: bool,
) -> list[PolicyFailure]:
    """Validate active subject/evidence joins for one policy consumer."""

    failures: list[PolicyFailure] = []
    joined_subjects: set[str] = set()
    joined_evidence: set[str] = set()
    for policy_ref in sorted(policy_refs):
        policy = policies.get(policy_ref)
        if policy is None or policy.get("status") != "active":
            failures.append(
                failure(
                    "tooling-policy-reference",
                    f"{context} references a missing or inactive admission policy",
                    path,
                )
            )
            continue
        subject = policy.get("subject")
        accepted_evidence = string_set(policy.get("accepted_evidence"))
        if isinstance(subject, str):
            joined_subjects.add(subject)
        joined_evidence.update(accepted_evidence)
        evidence_compatible = (
            provided_evidence <= accepted_evidence
            if require_all_evidence_per_policy
            else bool(provided_evidence & accepted_evidence)
        )
        failures.extend(_policy_compatibility_failures(subject, evidence_compatible, expected_subjects, path, context))
    if expected_subjects - joined_subjects:
        failures.append(
            failure(
                "tooling-policy-subject",
                f"{context} lacks an active admission policy for every declared subject",
                path,
            )
        )
    if provided_evidence - joined_evidence:
        failures.append(
            failure(
                "tooling-policy-evidence",
                f"{context} supplies evidence not admitted by its referenced policies",
                path,
            )
        )
    return failures


def walk_forbidden_keys(value: object, *, path: str = "<root>") -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    # An explicit stack of pending steps keeps the depth-first order of the findings,
    # because the JSON decoder accepts nesting beyond the interpreter recursion limit.
    # A step is a forbidden key to report or a child value to walk.
    pending: list[tuple[bool, object, str]] = [(False, value, path)]
    while pending:
        is_key, current, current_path = pending.pop()
        if is_key:
            failures.append(
                failure(
                    "tooling-executable-field",
                    f"declarative policy contains forbidden executable field {current!r}",
                    current_path,
                )
            )
            continue
        steps: list[tuple[bool, object, str]] = []
        if isinstance(current, Mapping):
            for key, child in current.items():
                if isinstance(key, str) and key.lower() in FORBIDDEN_EXECUTABLE_KEYS:
                    steps.append((True, key, current_path))
                steps.append((False, child, f"{current_path}.{key}"))
        elif isinstance(current, list):
            steps = [(False, child, f"{current_path}[{index}]") for index, child in enumerate(current)]
        pending.extend(reversed(steps))
    return failures


def has_secret_bearing_locator(locator: str) -> bool:
    """Return whether a locator embeds secret material or interpolation."""

    parsed = None
    if "${{" not in locator and "${" not in locator and "{{" not in locator:
        with suppress(ValueError):
            parsed = urlsplit(locator)
    return bool(
        parsed is None
        or parsed.username is not None
        or parsed.password is not None
        or any(key.lower() in SECRET_QUERY_KEYS for key, _value in parse_qsl(parsed.query, keep_blank_values=True))
    )


def is_portable_relative_manifest_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and "\\" not in value
        and not re.match(r"^[A-Za-z]:", value)
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def safe_text(repo_root: Path, relative_path: str) -> str | None:
    """Read one bounded tracked file without following unsafe paths."""

    text = None
    if ".secrets" not in Path(relative_path).parts:
        path = safe_repo_path(repo_root, relative_path)
        if (
            path is not None
            and is_regular_repo_file(repo_root, relative_path)
            and path.stat().st_size <= MAX_SCANNED_FILE_BYTES
        ):
            with suppress(OSError, UnicodeError):
                text = path.read_text(encoding="utf-8")
    return text


def walk_mapping_values(value: object, key_name: str) -> tuple[list[str], bool]:
    """Return scalar values for an exact structured key and whether any were invalid."""

    values: list[str] = []
    invalid = False
    children: list[object] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == key_name:
                if isinstance(child, str) and child:
                    values.append(child)
                else:
                    invalid = True
            children.append(child)
    elif isinstance(value, list):
        children.extend(value)
    for child in children:
        child_values, child_invalid = walk_mapping_values(child, key_name)
        values.extend(child_values)
        invalid = invalid or child_invalid
    return values, invalid
