"""Shared primitives for the closed development artifact-policy validator."""

from __future__ import annotations

import re
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path

TOOLING_ROOT = "implementations/tooling"
ARTIFACT_LOCK_PATH = f"{TOOLING_ROOT}/artifacts.lock.json"
PROFILES_PATH = f"{TOOLING_ROOT}/profiles/development-profiles.json"
ADMISSION_POLICY_PATH = f"{TOOLING_ROOT}/admission-policy.json"
ACTIONS_POLICY_PATH = f"{TOOLING_ROOT}/actions-policy.json"
SELECTOR_BINDINGS_PATH = f"{TOOLING_ROOT}/selector-bindings.json"
INVENTORY_COVERAGE_PATH = f"{TOOLING_ROOT}/inventory-coverage.json"

POLICY_SCHEMAS = {
    ARTIFACT_LOCK_PATH: f"{TOOLING_ROOT}/schemas/artifact-lock.schema.json",
    PROFILES_PATH: f"{TOOLING_ROOT}/schemas/profiles.schema.json",
    ADMISSION_POLICY_PATH: f"{TOOLING_ROOT}/schemas/admission-policy.schema.json",
    ACTIONS_POLICY_PATH: f"{TOOLING_ROOT}/schemas/actions-policy.schema.json",
    SELECTOR_BINDINGS_PATH: f"{TOOLING_ROOT}/schemas/selector-bindings.schema.json",
    INVENTORY_COVERAGE_PATH: f"{TOOLING_ROOT}/schemas/inventory-coverage.schema.json",
}
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SCANNED_FILE_BYTES = 2 * 1024 * 1024
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


def load_documents(repo_root: Path) -> tuple[dict[str, dict[str, Any]], list[PolicyFailure]]:
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
        except (OSError, ValueError):
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


def _schema_failures(
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
    policy_path: str,
    schema_path: str,
) -> list[PolicyFailure]:
    from jsonschema import Draft202012Validator, FormatChecker

    if contains_nonlocal_schema_reference(schema):
        return [
            failure(
                "tooling-schema-reference",
                "internal tooling schemas may use only local fragment references",
                schema_path,
            )
        ]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        failure(
            "tooling-schema",
            "schema validation failed at "
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}",
            policy_path,
        )
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]


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

    found = False
    if isinstance(value, Mapping):
        found = any(
            key == "$ref"
            and (not isinstance(child, str) or not child.startswith("#"))
            or contains_nonlocal_schema_reference(child)
            for key, child in value.items()
        )
    elif isinstance(value, list):
        found = any(contains_nonlocal_schema_reference(child) for child in value)
    return found


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def string_set(value: object) -> set[str]:
    return {item for item in as_list(value) if isinstance(item, str)}


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
        if subject not in expected_subjects:
            failures.append(
                failure(
                    "tooling-policy-subject",
                    f"{context} admission policy has an incompatible subject",
                    path,
                )
            )
        evidence_compatible = (
            provided_evidence <= accepted_evidence
            if require_all_evidence_per_policy
            else bool(provided_evidence & accepted_evidence)
        )
        if not evidence_compatible:
            failures.append(
                failure(
                    "tooling-policy-evidence",
                    f"{context} does not supply evidence accepted by its admission policy",
                    path,
                )
            )
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
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_EXECUTABLE_KEYS:
                failures.append(
                    failure(
                        "tooling-executable-field",
                        f"declarative policy contains forbidden executable field {key!r}",
                        ARTIFACT_LOCK_PATH,
                    )
                )
            failures.extend(walk_forbidden_keys(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            failures.extend(walk_forbidden_keys(child, path=f"{path}[{index}]"))
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
