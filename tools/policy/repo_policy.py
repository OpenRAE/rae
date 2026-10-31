from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import yaml
from raes_contracts.errors import InvalidInputError

from .adr import (
    normalize_adr_status as _normalize_adr_status,
)
from .adr import (
    parse_adr_file as _parse_adr_file,
)
from .common import PolicyFailure, load_yaml, parse_python_source, path_matches_prefix, read_repository_text
from .common import safe_repo_path as _safe_repo_path
from .conftest_tool import run_conftest_policy
from .import_boundaries import boundary_violation
from .structural_ratchet import evaluate_structural_ratchet

StructuralPolicyRunner = Callable[[dict], list[PolicyFailure]]
# Runs the ADR-117 structural checks on the loaded policy.
RatchetRunner = Callable[[dict[str, object]], list[PolicyFailure]]
# What load_yaml raises for a missing, unreadable, non-UTF-8, malformed or
# excessively nested policy file, and InvalidInputError for a scalar that the
# safe constructor cannot build. The message never echoes the file content.
_YAML_LOAD_FAILURES = (OSError, UnicodeDecodeError, yaml.YAMLError, RecursionError, InvalidInputError)


def load_policy(repo_root: Path) -> dict:
    return load_yaml(repo_root / "tools" / "policy" / "adr_policy.yaml")


def _load_policy_guarded(repo_root: Path) -> tuple[dict | None, list[PolicyFailure]]:
    """Load ``adr_policy.yaml`` and confirm its root is a mapping. A parse
    error or a non-mapping root surfaces as ``policy-config-malformed``
    rather than a traceback, so a PR that breaks the policy file fails the
    gate cleanly instead of crashing CI (and instead of letting downstream
    checkers raise ``KeyError`` on a malformed mapping)."""
    fail = lambda msg: PolicyFailure("policy-config-malformed", msg, _POLICY_CONFIG_PATH)  # noqa: E731
    try:
        policy = load_policy(repo_root)
    except _YAML_LOAD_FAILURES:
        return None, [fail(f"{_POLICY_CONFIG_PATH} could not be parsed (missing or invalid YAML)")]
    reason = _policy_shape_failure(policy)
    if reason is not None:
        return None, [fail(reason)]
    return policy, []


def _policy_shape_failure(policy: object) -> str | None:
    """Return why a loaded policy is not a JSON-compatible mapping, or None."""
    if not isinstance(policy, dict):
        return f"{_POLICY_CONFIG_PATH} root must be a YAML mapping; got {type(policy).__name__}"
    try:
        # The structural runner gives the policy to conftest as sorted JSON. A YAML timestamp, set or
        # binary value, or a mapping whose keys do not sort, has no JSON form (TypeError); a recursive
        # alias is a circular reference (ValueError). The try holds only the encoder.
        json.dumps(policy, sort_keys=True)
    except TypeError, ValueError:
        return f"{_POLICY_CONFIG_PATH} must contain only JSON data"
    return None


def evaluate_repo_policy(
    repo_root: Path,
    changed: list[str],
    *,
    check_set: str = "full",
    structural_runner: StructuralPolicyRunner | None = None,
    base_rev: str | None = None,
    ratchet_runner: RatchetRunner | None = None,
) -> list[PolicyFailure]:
    policy, policy_load_errs = _load_policy_guarded(repo_root)
    if policy_load_errs:
        return policy_load_errs
    assert policy is not None

    failures: list[PolicyFailure] = []
    if check_set == "full":
        # The structural ratchets are global (ADR-117): they run for every full check, also
        # when the change list is empty or holds only deletions.
        if ratchet_runner is None:

            def ratchet_runner(loaded_policy: dict[str, object]) -> list[PolicyFailure]:
                return evaluate_structural_ratchet(repo_root, loaded_policy, base_rev=base_rev)

        failures.extend(ratchet_runner(policy))

    # Drop any changed path that escapes the repository root (absolute,
    # parent-traversal, or a planted symlink that resolves outside the
    # tree) BEFORE any checker reads it. This is a single chokepoint:
    # every downstream checker that opens a changed file — the layering
    # scan, the size cap, the import-direction check, the compat-wrapper
    # check — receives an already-validated list, so none of them can be
    # tricked into reading an out-of-tree file. See ADR-015.
    safe_changed: list[str] = []
    for rel_path in changed:
        if _safe_repo_path(repo_root, rel_path) is None:
            failures.append(
                PolicyFailure(
                    "policy-path-unsafe",
                    f"changed path '{rel_path}' resolves outside the repository root; refusing to inspect",
                    rel_path,
                )
            )
        else:
            safe_changed.append(rel_path)
    changed = safe_changed

    if not changed:
        # No by-file changes to check (e.g. a deletion-only PR — the repo's
        # changed-paths helper excludes deletions). The ADR-015 config-wide
        # invariants (allowlist present + well-formed, allowlist ⊆ the
        # locked set, every initial oversized file either still
        # allow-listed-and-over-cap or genuinely split below it) must still
        # hold regardless, so run that portion before returning.
        failures.extend(_check_layering_and_oversized(repo_root, policy, []))
        failures.extend(_check_module_boundaries(repo_root, policy, [], check_set=check_set))
        return failures

    if structural_runner is None:

        def structural_runner(input_document: dict) -> list[PolicyFailure]:
            return run_conftest_policy(input_document, repo_root=repo_root)

    failures.extend(
        structural_runner(
            {
                "changed": changed,
                "check_set": check_set,
                "policy": policy,
            }
        )
    )
    failures.extend(_check_layering_and_oversized(repo_root, policy, changed))
    failures.extend(_check_module_boundaries(repo_root, policy, changed, check_set=check_set))

    if check_set == "full":
        failures.extend(_check_adr_template(repo_root, changed))
        failures.extend(_check_adr_index(repo_root, policy, changed))

    if "CHANGELOG.md" in changed:
        failures.extend(_check_changelog_versioned(repo_root))

    return failures


# ──────────────────────────────────────────────────────────────────────────
# ADR-015: SDL→processor layering rule + 1,000-line source-file cap.
#
# These two gates catch unintentional regressions in normal contributions:
# a developer who accidentally writes `import raes_processor` in `raes/`,
# or one who pushes a >1,000-line file, or a split PR that forgets to drain
# its allowlist entry. The cap is a backstop; ADR-117 checks the module
# structure directly. The policy and its YAML config are PR-mutable; PR
# review (not this code) defends against deliberate weakening. See ADR-015.
# ──────────────────────────────────────────────────────────────────────────

_POLICY_CONFIG_PATH = "tools/policy/adr_policy.yaml"

# The set of source files that were over the source-file cap when the current
# cap was adopted. The cap was 600 lines at the ADR-015 landing, 500 from
# 2026-07-12 (#561) and 1,000 from 2026-10-30 (#1734, ADR-015 Amendments). Each
# cap change re-baselined this set to the files over the new cap; no file was
# over 1,000 lines, so the set is empty. The size-cap allowlist
# (tools/policy/oversized_allowlist.yaml) may only ever be a SUBSET of this set,
# so it stays empty. This is a code constant — not config in adr_policy.yaml —
# so that "the allowlist only shrinks" is enforced against a fixed reference
# rather than against an input the same PR can edit. Adding an oversized file
# therefore requires a diff to this module, which PR review scrutinises as
# policy, not as data noise.
_ADR015_INITIAL_OVERSIZED_FILES: frozenset[str] = frozenset()


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str_list_ok(value: object, *, allow_empty: bool) -> bool:
    if not isinstance(value, list):
        return False
    if not value and not allow_empty:
        return False
    return all(_is_str(item) for item in value)


def _validate_oversized_config(
    config: object,
) -> tuple[dict | None, list[PolicyFailure]]:
    """Validate the ``oversized_source_files`` block. Returns
    ``(normalized_config, failures)``; ``normalized_config`` is None when
    the block is missing/malformed (with failures populated). Per ADR-015
    this block is required policy — an absent block is a malformation, not
    an opt-out, so the size cap can't be silently disabled."""
    fail = lambda msg: PolicyFailure("policy-config-malformed", msg, _POLICY_CONFIG_PATH)  # noqa: E731
    if config is None:
        return None, [fail("oversized_source_files block is required (ADR-015) but is absent")]
    if not isinstance(config, dict):
        return None, [fail(f"oversized_source_files must be a mapping; got {type(config).__name__}")]

    failures: list[PolicyFailure] = []
    line_cap = config.get("line_cap")
    if not _is_int(line_cap) or line_cap <= 0:
        failures.append(fail(f"oversized_source_files.line_cap must be a positive integer; got {line_cap!r}"))
    allowlist_path = config.get("allowlist_path")
    if not _is_str(allowlist_path) or not allowlist_path:
        failures.append(
            fail(f"oversized_source_files.allowlist_path must be a non-empty string; got {allowlist_path!r}")
        )
    scope_roots = config.get("scope_roots")
    if not _str_list_ok(scope_roots, allow_empty=False):
        failures.append(fail("oversized_source_files.scope_roots must be a non-empty list of strings"))
    file_extensions = config.get("file_extensions")
    if not _str_list_ok(file_extensions, allow_empty=False):
        failures.append(fail("oversized_source_files.file_extensions must be a non-empty list of strings"))
    excluded = config.get("excluded_path_prefixes", [])
    if excluded is None:
        excluded = []
    if not _str_list_ok(excluded, allow_empty=True):
        failures.append(fail("oversized_source_files.excluded_path_prefixes must be a list of strings"))

    if failures:
        return None, failures
    return (
        {
            "line_cap": line_cap,
            "allowlist_path": allowlist_path,
            "scope_roots": tuple(scope_roots),
            "file_extensions": tuple(file_extensions),
            "excluded_path_prefixes": tuple(excluded),
        },
        [],
    )


def _validate_layering_rules(rules: object) -> tuple[list[dict], list[PolicyFailure]]:
    """Validate the ``layering_rules`` list. Returns ``(rules, failures)``;
    on any malformation ``failures`` is populated and ``rules`` is empty.
    Per ADR-015 at least one layering rule is required — an absent or empty
    list is a malformation, not an opt-out."""
    fail = lambda msg: PolicyFailure("policy-config-malformed", msg, _POLICY_CONFIG_PATH)  # noqa: E731
    if rules is None:
        return [], [fail("layering_rules is required (ADR-015) but is absent")]
    if not isinstance(rules, list):
        return [], [fail(f"layering_rules must be a list; got {type(rules).__name__}")]
    if not rules:
        return [], [fail("layering_rules must contain at least one rule (ADR-015)")]

    failures: list[PolicyFailure] = []
    validated: list[dict] = []
    seen_ids: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            failures.append(fail(f"layering_rules[{index}] must be a mapping; got {type(rule).__name__}"))
            continue
        rule_id = rule.get("id")
        scope_root = rule.get("scope_root")
        forbidden = rule.get("forbidden_top_level")
        ok = True
        if not _is_str(rule_id) or not rule_id:
            failures.append(fail(f"layering_rules[{index}].id must be a non-empty string; got {rule_id!r}"))
            ok = False
        elif rule_id in seen_ids:
            failures.append(fail(f"layering_rules[{index}].id '{rule_id}' is duplicated"))
            ok = False
        if not _is_str(scope_root) or not scope_root:
            failures.append(fail(f"layering_rules[{index}].scope_root must be a non-empty string; got {scope_root!r}"))
            ok = False
        if not _is_str(forbidden) or not forbidden:
            failures.append(
                fail(f"layering_rules[{index}].forbidden_top_level must be a non-empty string; got {forbidden!r}")
            )
            ok = False
        if ok:
            seen_ids.add(rule_id)
            validated.append(
                {
                    "id": rule_id,
                    "scope_root": scope_root,
                    "forbidden_top_level": forbidden,
                }
            )
    if failures:
        return [], failures
    return validated, []


def _validate_allowlist(repo_root: Path, allowlist_path: str) -> tuple[frozenset[str] | None, list[PolicyFailure]]:
    """Read and validate the allowlist YAML at ``allowlist_path``. Returns
    ``(files, failures)``; ``files`` is None on a missing/malformed/unsafe
    file. ``allowlist_path`` comes from PR-controlled config, so it is
    validated to stay inside the repo before any I/O, and a parse error
    does not echo the file's content into the failure message."""
    fail = lambda msg: PolicyFailure("policy-config-malformed", msg, allowlist_path)  # noqa: E731
    safe = _safe_repo_path(repo_root, allowlist_path)
    if safe is None:
        return None, [
            PolicyFailure(
                "policy-path-unsafe",
                (
                    f"oversized_source_files.allowlist_path '{allowlist_path}' is not a safe "
                    "repo-relative path (absolute, parent-traversal, or resolves outside the repo)"
                ),
                _POLICY_CONFIG_PATH,
            )
        ]
    if not safe.is_file():
        return None, [fail(f"{allowlist_path} is missing or is not a regular file")]
    try:
        data = load_yaml(safe)
    except _YAML_LOAD_FAILURES:
        return None, [fail(f"{allowlist_path} could not be parsed (invalid YAML)")]
    if not isinstance(data, dict):
        return None, [fail(f"{allowlist_path} root must be a YAML mapping; got {type(data).__name__}")]
    files = data.get("files", [])
    if files is None:
        files = []
    if not _str_list_ok(files, allow_empty=True):
        return None, [fail(f"{allowlist_path} 'files' must be a list of repo-relative path strings")]
    return frozenset(files), []


def _check_layering_and_oversized(repo_root: Path, policy: dict, changed: list[str]) -> list[PolicyFailure]:
    layering_rules, layering_errs = _validate_layering_rules(policy.get("layering_rules"))
    oversized_cfg, oversized_errs = _validate_oversized_config(policy.get("oversized_source_files"))
    config_errs = layering_errs + oversized_errs
    if config_errs:
        # No point checking against malformed config.
        return config_errs
    assert oversized_cfg is not None  # validator returned no errors

    failures: list[PolicyFailure] = []
    failures.extend(_check_layering(repo_root, layering_rules, changed))
    allowlist, allowlist_errs = _validate_allowlist(repo_root, oversized_cfg["allowlist_path"])
    if allowlist_errs:
        return [*failures, *allowlist_errs]
    assert allowlist is not None
    failures.extend(_check_oversized(repo_root, oversized_cfg, allowlist, changed))
    failures.extend(_check_drain(allowlist, oversized_cfg["allowlist_path"]))
    failures.extend(_check_oversized_debt_consistency(repo_root, oversized_cfg, allowlist))
    return failures


def _check_oversized_debt_consistency(repo_root: Path, config: dict, allowlist: frozenset[str]) -> list[PolicyFailure]:
    """Reconcile every ADR-015 initial-oversized path against the allowlist
    and the file on disk. This is a config-wide check (it does not look at
    the changed set) because both relevant mutations — splitting the file
    (which deletes the original) and draining the allowlist entry — can be
    invisible to a changed-paths helper that excludes deletions.

    For each path in ``_ADR015_INITIAL_OVERSIZED_FILES``:

    - If it is still allow-listed, it must resolve to a regular repo file
      that is still over the cap. A file that has been split/shrunk/deleted
      but left in the allowlist is a stale entry (``oversized-allowlist-
      stale-entry``); one replaced by an out-of-tree symlink is
      ``policy-path-unsafe``.
    - If it has been removed from the allowlist (i.e. claimed "drained"),
      the file must actually have been split: it may not still be a regular
      repo file over the cap. If it is, that is a premature drain
      (``oversized-source-file``) — the allowlist shrank without the work
      being done.
    """
    line_cap = config["line_cap"]
    allowlist_path = config["allowlist_path"]
    failures: list[PolicyFailure] = []
    for path in sorted(_ADR015_INITIAL_OVERSIZED_FILES):
        safe = _safe_repo_path(repo_root, path)
        allow_listed = path in allowlist
        if safe is None:
            if allow_listed:
                failures.append(
                    PolicyFailure(
                        "policy-path-unsafe",
                        (
                            f"allowlist entry '{path}' resolves outside the repository root "
                            "(replaced with a symlink?); remove the allowlist entry"
                        ),
                        allowlist_path,
                    )
                )
            continue
        line_count = _file_line_count(safe)
        if allow_listed:
            if line_count is None:
                failures.append(
                    PolicyFailure(
                        "oversized-allowlist-stale-entry",
                        (
                            f"'{path}' is in {allowlist_path} but no regular file exists at that path "
                            "(split or deleted?); remove the allowlist entry"
                        ),
                        allowlist_path,
                    )
                )
            elif line_count <= line_cap:
                failures.append(
                    PolicyFailure(
                        "oversized-allowlist-stale-entry",
                        (
                            f"'{path}' is in {allowlist_path} but is now {line_count} lines (≤ {line_cap}); "
                            "remove the allowlist entry — it is no longer over-cap debt"
                        ),
                        allowlist_path,
                    )
                )
        else:  # claimed drained — the file must really have been split
            if line_count is not None and line_count > line_cap:
                failures.append(
                    PolicyFailure(
                        "oversized-source-file",
                        (
                            f"'{path}' was removed from {allowlist_path} but is still {line_count} lines, "
                            f"over the {line_cap}-line cap — the allowlist may only shrink once the file has "
                            "actually been split; either split it below the cap or restore the allowlist entry"
                        ),
                        path,
                    )
                )
    return failures


def _file_line_count(path: Path) -> int | None:
    """Line count of ``path``, or None if it is not a readable regular file.

    The bytes are split at the same universal line breaks that text mode uses,
    so the line cap also applies to a file that is not UTF-8.
    """
    if not path.is_file():
        return None
    try:
        content = path.read_bytes()
    except OSError:
        return None
    return len(content.splitlines())


def _check_layering(repo_root: Path, layering_rules: list[dict], changed: list[str]) -> list[PolicyFailure]:
    """For each layering rule, walk the AST of every changed ``.py`` file
    under ``scope_root`` and reject any ``import <forbidden>[…]`` or
    ``from <forbidden>[…] import …`` statement. ``changed`` has already
    been filtered to in-repo paths by ``evaluate_repo_policy``."""
    failures: list[PolicyFailure] = []
    for rule in layering_rules:
        scope_root = rule["scope_root"]
        forbidden = rule["forbidden_top_level"]
        forbidden_dotted = forbidden + "."
        message = f"{scope_root} must not import {forbidden} (rule: {rule['id']})"
        for rel_path in changed:
            if not rel_path.endswith(".py") or not path_matches_prefix(rel_path, scope_root):
                continue
            path = repo_root / rel_path
            if not path.is_file():
                continue
            tree = parse_python_source(path, rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name
                        if name == forbidden or name.startswith(forbidden_dotted):
                            failures.append(PolicyFailure("layering-rule-violation", message, rel_path))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module
                    if module and (module == forbidden or module.startswith(forbidden_dotted)):
                        failures.append(PolicyFailure("layering-rule-violation", message, rel_path))
    return failures


def _check_oversized(
    repo_root: Path, config: dict, allowlist: frozenset[str], changed: list[str]
) -> list[PolicyFailure]:
    """Reject any changed file under ``scope_roots`` (and not under an
    ``excluded_path_prefixes`` entry, and matching ``file_extensions``)
    that exceeds ``line_cap`` lines and is not in the allowlist.

    The ADR-015 initial-oversized paths are NOT checked here even when
    changed — they are reconciled config-wide by
    ``_check_oversized_debt_consistency`` (which owns both the
    "still allow-listed and over cap" and "drained but not split" cases),
    so this checker only catches *new* over-cap files.

    ``changed`` has already been filtered to in-repo paths by
    ``evaluate_repo_policy``."""
    line_cap = config["line_cap"]
    scope_roots = config["scope_roots"]
    excluded = config["excluded_path_prefixes"]
    extensions = config["file_extensions"]
    allowlist_path = config["allowlist_path"]
    failures: list[PolicyFailure] = []
    for rel_path in changed:
        if extensions and not rel_path.endswith(tuple(extensions)):
            continue
        if not any(path_matches_prefix(rel_path, root) for root in scope_roots):
            continue
        if any(path_matches_prefix(rel_path, prefix) for prefix in excluded):
            continue
        if rel_path in allowlist or rel_path in _ADR015_INITIAL_OVERSIZED_FILES:
            continue
        line_count = _file_line_count(repo_root / rel_path)
        if line_count is None:
            continue
        if line_count > line_cap:
            failures.append(
                PolicyFailure(
                    "oversized-source-file",
                    (
                        f"file is {line_count} lines, exceeding the {line_cap}-line cap; "
                        f"split it into subdomain modules (do not add it to {allowlist_path}; "
                        "the allowlist only shrinks)"
                    ),
                    rel_path,
                )
            )
    return failures


def _check_drain(allowlist: frozenset[str], allowlist_path: str) -> list[PolicyFailure]:
    """The allowlist must be a subset of ``_ADR015_INITIAL_OVERSIZED_FILES``
    (a code constant, not config). Entries can be removed (the drain
    mechanism) but not added — a file over the cap that wasn't one of the
    initial oversized files must be split, not allow-listed."""
    return [
        PolicyFailure(
            "oversized-allowlist-locked",
            (
                f"'{path}' is in {allowlist_path} but is not one of the files that were over the "
                "source-file cap when it was adopted (_ADR015_INITIAL_OVERSIZED_FILES in "
                "tools/policy/repo_policy.py); the allowlist may only shrink — split the file instead of adding it"
            ),
            allowlist_path,
        )
        for path in sorted(allowlist - _ADR015_INITIAL_OVERSIZED_FILES)
    ]


def _validate_module_boundary_config(repo_root: Path, config: object) -> tuple[list[dict], list[PolicyFailure]]:
    """Validate the ADR-036 module-boundary policy block."""

    fail = lambda msg: PolicyFailure("policy-config-malformed", msg, _POLICY_CONFIG_PATH)  # noqa: E731
    if config is None:
        return [], [fail("module_boundaries block is required (ADR-036 / MOD-001) but is absent")]
    if not isinstance(config, dict):
        return [], [fail(f"module_boundaries must be a mapping; got {type(config).__name__}")]
    adr = config.get("adr")
    if not _is_str(adr) or not adr:
        return [], [fail(f"module_boundaries.adr must be a non-empty string; got {adr!r}")]
    modules = config.get("modules")
    if not isinstance(modules, list) or not modules:
        return [], [fail("module_boundaries.modules must be a non-empty list")]
    package_coverage_roots = config.get("package_coverage_roots")
    if not _str_list_ok(package_coverage_roots, allow_empty=False):
        return [], [fail("module_boundaries.package_coverage_roots must be a non-empty list of strings")]

    failures: list[PolicyFailure] = []
    validated: list[dict] = []
    seen_ids: set[str] = set()
    seen_roots: set[str] = set()
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            failures.append(fail(f"module_boundaries.modules[{index}] must be a mapping"))
            continue
        module_id = module.get("id")
        root = module.get("root")
        ok = True
        if not _is_str(module_id) or not module_id:
            failures.append(fail(f"module_boundaries.modules[{index}].id must be a non-empty string"))
            ok = False
        elif module_id in seen_ids:
            failures.append(fail(f"module_boundaries.modules[{index}].id '{module_id}' is duplicated"))
            ok = False
        if not _is_str(root) or not root:
            failures.append(fail(f"module_boundaries.modules[{index}].root must be a non-empty string"))
            ok = False
        elif root in seen_roots:
            failures.append(fail(f"module_boundaries.modules[{index}].root '{root}' is duplicated"))
            ok = False
        else:
            safe_root = _safe_repo_path(repo_root, str(root))
            if safe_root is None:
                failures.append(
                    fail(f"module_boundaries.modules[{index}].root '{root}' must be a safe repo-relative path")
                )
                ok = False
            elif not safe_root.is_dir():
                failures.append(
                    fail(f"module_boundaries.modules[{index}].root '{root}' must resolve to an existing directory")
                )
                ok = False
        allowed = module.get("allowed_top_level_imports", [])
        forbidden = module.get("forbidden_import_prefixes", [])
        if not _str_list_ok(allowed, allow_empty=True):
            failures.append(
                fail(f"module_boundaries.modules[{index}].allowed_top_level_imports must be a list of strings")
            )
            ok = False
        if not _str_list_ok(forbidden, allow_empty=True):
            failures.append(
                fail(f"module_boundaries.modules[{index}].forbidden_import_prefixes must be a list of strings")
            )
            ok = False
        public_imports = module.get("public_import_prefixes", {})
        if public_imports is None:
            public_imports = {}
        if not isinstance(public_imports, dict):
            failures.append(fail(f"module_boundaries.modules[{index}].public_import_prefixes must be a mapping"))
            ok = False
        elif any(
            not _is_str(key) or not _str_list_ok(value, allow_empty=False) for key, value in public_imports.items()
        ):
            failures.append(
                fail(
                    f"module_boundaries.modules[{index}].public_import_prefixes values must be non-empty "
                    "lists of strings"
                )
            )
            ok = False
        if not ok:
            continue
        seen_ids.add(str(module_id))
        seen_roots.add(str(root))
        validated.append(
            {
                "id": str(module_id),
                "root": str(root),
                "allowed_top_level_imports": frozenset(str(item) for item in allowed),
                "forbidden_import_prefixes": tuple(str(item) for item in forbidden),
                "public_import_prefixes": {
                    str(key): tuple(str(prefix) for prefix in value) for key, value in public_imports.items()
                },
            }
        )
    if failures:
        return validated, failures
    for coverage_root in package_coverage_roots:
        safe_coverage_root = _safe_repo_path(repo_root, str(coverage_root))
        if safe_coverage_root is None:
            failures.append(
                fail(
                    f"module_boundaries.package_coverage_roots entry '{coverage_root}' must be a safe repo-relative path"
                )
            )
            continue
        if not safe_coverage_root.is_dir():
            failures.append(
                fail(
                    f"module_boundaries.package_coverage_roots entry '{coverage_root}' "
                    "must resolve to an existing directory"
                )
            )
            continue
        for package_root in sorted(path for path in safe_coverage_root.iterdir() if path.is_dir()):
            if not (package_root / "__init__.py").is_file():
                continue
            rel_package_root = package_root.relative_to(repo_root).as_posix()
            if rel_package_root not in seen_roots:
                failures.append(
                    fail(
                        f"package root '{rel_package_root}' is missing from module_boundaries.modules; "
                        "every first-party package must have an ADR-backed module boundary"
                    )
                )
    return validated, failures


def _check_module_boundaries(
    repo_root: Path,
    policy: dict,
    changed: list[str],
    *,
    check_set: str,
) -> list[PolicyFailure]:
    rules, config_failures = _validate_module_boundary_config(repo_root, policy.get("module_boundaries"))
    if config_failures or not rules:
        return config_failures

    known_modules = frozenset(rule["id"] for rule in rules)
    failures: list[PolicyFailure] = []
    candidate_paths = _module_boundary_candidate_paths(repo_root, rules, changed, check_set=check_set)
    for rule in rules:
        for rel_path in candidate_paths:
            if not rel_path.endswith(".py") or not path_matches_prefix(rel_path, rule["root"]):
                continue
            path = repo_root / rel_path
            if not path.is_file():
                continue
            tree = parse_python_source(path, rel_path)
            failures.extend(_check_module_imports(rel_path, rule, known_modules, tree))
            if rule["id"] == "raes_backend_protocols":
                failures.extend(_check_backend_protocol_contract_annotations(rel_path, tree))
    return failures


def _module_boundary_candidate_paths(
    repo_root: Path,
    rules: list[dict],
    changed: list[str],
    *,
    check_set: str,
) -> list[str]:
    if check_set != "full":
        return changed

    paths: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        root = repo_root / rule["root"]
        for path in sorted(root.rglob("*.py")):
            if not path.is_file():
                continue
            rel_path = path.relative_to(repo_root).as_posix()
            if rel_path in seen:
                continue
            seen.add(rel_path)
            paths.append(rel_path)
    return paths


def _check_module_imports(
    rel_path: str,
    rule: dict,
    known_modules: frozenset[str],
    tree: ast.Module,
) -> list[PolicyFailure]:
    return [
        PolicyFailure(rule_id, message, rel_path)
        for imported in _imported_names(tree)
        if (violation := boundary_violation(rule, known_modules, imported)) is not None
        for rule_id, message in (violation,)
    ]


def _imported_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            for alias in node.names:
                if alias.name == "*":
                    names.append(node.module)
                    continue
                names.append(f"{node.module}.{alias.name}")
    return names


def _check_backend_protocol_contract_annotations(rel_path: str, tree: ast.Module) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for class_node in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        if not any(_base_name(base) == "Protocol" for base in class_node.bases):
            continue
        for function in (item for item in class_node.body if isinstance(item, ast.FunctionDef)):
            for annotation in _function_signature_annotations(function):
                if _annotation_uses_any(annotation):
                    failures.append(
                        PolicyFailure(
                            "backend-protocol-untyped-contract",
                            (
                                f"{class_node.name}.{function.name} uses Any in its public protocol signature; "
                                "backend protocols must use neutral contract DTOs from raes_contracts"
                            ),
                            rel_path,
                        )
                    )
                    break
    return failures


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ""


def _function_signature_annotations(function: ast.FunctionDef) -> Iterator[ast.expr]:
    for arg in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]:
        if arg.arg == "self":
            continue
        if arg.annotation is not None:
            yield arg.annotation
    if function.args.vararg is not None and function.args.vararg.annotation is not None:
        yield function.args.vararg.annotation
    if function.args.kwarg is not None and function.args.kwarg.annotation is not None:
        yield function.args.kwarg.annotation
    if function.returns is not None:
        yield function.returns


def _annotation_uses_any(annotation: ast.expr) -> bool:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "Any":
            return True
    return False


CHANGELOG_HEADING_RE = re.compile(r"^## \[(.+?)\]", re.MULTILINE)
SECTION_CONTENT_RE = re.compile(r"^###\s", re.MULTILINE)


def _check_changelog_versioned(repo_root: Path) -> list[PolicyFailure]:
    changelog = repo_root / "CHANGELOG.md"
    if not changelog.exists():
        return []
    text = read_repository_text(changelog, "CHANGELOG.md")
    for match in CHANGELOG_HEADING_RE.finditer(text):
        label = match.group(1)
        if label.lower() == "unreleased":
            heading_end = match.end()
            next_heading = CHANGELOG_HEADING_RE.search(text, heading_end)
            section_text = text[heading_end : next_heading.start()] if next_heading else text[heading_end:]
            if SECTION_CONTENT_RE.search(section_text):
                return [
                    PolicyFailure(
                        "changelog-unreleased-content",
                        "CHANGELOG.md has content under [Unreleased]; assign a version number and date",
                        "CHANGELOG.md",
                    )
                ]
    return []


# ADR-file parsing (header regex, status/date extraction, status normalisation)
# lives in ``tools/policy/adr.py`` and is imported above so this README↔index
# check and the ADR pin gate (ADR-059) parse ADRs identically. ``README_ROW_RE``
# stays here because it parses the README index table, not an ADR file.
README_ROW_RE = re.compile(
    r"^\| \[(\d{3})\]\(([^)]+)\) \| (.+?) \| (.+?) \| (\d{4}-\d{2}-\d{2}) \|$",
    re.MULTILINE,
)
ADR_TEMPLATE_PATH = "docs/decisions/adrs/TEMPLATE.md"
ADR_TEMPLATE_REQUIRED_SECTIONS = (
    "Status",
    "Date",
    "Context",
    "Decision",
    "Alternatives Considered",
    "Consequences",
)
ADR_TEMPLATE_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _check_adr_template(repo_root: Path, changed: list[str]) -> list[PolicyFailure]:
    if not any(path.startswith("docs/decisions/adrs/") or path == "tools/policy/repo_policy.py" for path in changed):
        return []

    template = repo_root / ADR_TEMPLATE_PATH
    if not template.exists():
        return [
            PolicyFailure(
                "adr-template-missing",
                "ADR template is missing",
                ADR_TEMPLATE_PATH,
            )
        ]

    text = read_repository_text(template, ADR_TEMPLATE_PATH)
    headings = {match.group(1).strip() for match in ADR_TEMPLATE_HEADING_RE.finditer(text)}
    missing = [section for section in ADR_TEMPLATE_REQUIRED_SECTIONS if section not in headings]
    if missing:
        return [
            PolicyFailure(
                "adr-template-section-missing",
                f"ADR template is missing required section(s): {', '.join(missing)}",
                ADR_TEMPLATE_PATH,
            )
        ]
    return []


def _check_adr_index(repo_root: Path, policy: dict, changed: list[str]) -> list[PolicyFailure]:
    index_path = policy["adr_index"]["index_path"]
    if not any(path.startswith("docs/decisions/adrs/") for path in changed):
        return []

    adr_dir = repo_root / "docs" / "decisions" / "adrs"
    adr_files = sorted(path for path in adr_dir.glob("adr-*.md") if path.name != "README.md")
    expected: dict[str, tuple[str, str, str, str]] = {}
    for adr_file in adr_files:
        number, title, status, date_value = _parse_adr_file(adr_file)
        expected[number] = (adr_file.name, title, status, date_value)

    readme_text = read_repository_text(repo_root / index_path, index_path)
    actual = {
        number: (
            Path(link).name,
            title.strip(),
            _normalize_adr_status(status),
            date_value,
        )
        for number, link, title, status, date_value in README_ROW_RE.findall(readme_text)
    }

    if expected != actual:
        return [
            PolicyFailure(
                "adr-index-sync",
                "ADR index is out of sync with the ADR documents",
                index_path,
            )
        ]
    return []
