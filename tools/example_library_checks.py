"""Entry metadata and validated-content checks for the AUT-806 example library gate."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from raes import Scenario, load_sdl_fragment, parse_sdl, parse_sdl_file

from tools.policy.common import PolicyFailure
from tools.sdl_catalog_parity._paths import _COMPOSITION_FIELDS, _METADATA_FIELDS

CATALOG_RELATIVE_PATH = "examples/library/catalog.yaml"
VALIDATED = "validated"
GUIDANCE = "guidance"
VALIDATION_STATUSES: tuple[str, ...] = (VALIDATED, GUIDANCE)
REQUIRED_VALIDATION_STATUS: dict[str, str] = {
    "templates": VALIDATED,
    "patterns": GUIDANCE,
}
INTENDED_USERS: tuple[str, ...] = ("sdl-author",)
# Top-level SDL fields that specs/sdl/sections.md classifies as metadata or
# composition rather than as sections. The SDL catalog parity gate keeps these
# sets in step with that catalog.
NON_SECTION_FIELDS = _METADATA_FIELDS | _COMPOSITION_FIELDS


def _fail(rule_id: str, message: str, path: str = CATALOG_RELATIVE_PATH) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _text_list(value: object) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return list(value)
    return None


@cache
def _sdl_section_names() -> frozenset[str]:
    return frozenset(Scenario.model_fields) - NON_SECTION_FIELDS


def check_entry_metadata(field: str, entry: dict[str, Any], owner: str) -> list[PolicyFailure]:
    """Check the validation status, SDL sections, intended user, and limits of one catalog entry."""
    failures: list[PolicyFailure] = []
    allowed_statuses = (
        (REQUIRED_VALIDATION_STATUS[field],) if field in REQUIRED_VALIDATION_STATUS else VALIDATION_STATUSES
    )
    status = entry.get("validation_status")
    if status not in allowed_statuses:
        failures.append(
            _fail(
                "example-library-entry-status",
                f"{owner}.validation_status must be one of {list(allowed_statuses)}; got {status!r}",
            )
        )
    user = entry.get("intended_user")
    if user not in INTENDED_USERS:
        failures.append(
            _fail(
                "example-library-entry-user",
                f"{owner}.intended_user must be one of {list(INTENDED_USERS)}; got {user!r}",
            )
        )
    if not _text_list(entry.get("limits")):
        failures.append(_fail("example-library-entry-limits", f"{owner}.limits must be a non-empty list of strings"))
    sections = _text_list(entry.get("sdl_sections"))
    if not sections or len(set(sections)) != len(sections):
        failures.append(
            _fail("example-library-entry-sections", f"{owner}.sdl_sections must be a non-empty list of distinct names")
        )
    elif unknown := sorted(set(sections) - _sdl_section_names()):
        failures.append(
            _fail(
                "example-library-entry-sections",
                f"{owner}.sdl_sections names values that are not SDL sections: {unknown}",
            )
        )
    return failures


def _check_declared_sections(
    entry: dict[str, Any], document: dict[str, Any], relative_path: str
) -> list[PolicyFailure]:
    # Names that are not SDL sections already fail check_entry_metadata.
    declared = set(_text_list(entry.get("sdl_sections")) or []) & _sdl_section_names()
    absent = sorted(declared - set(document))
    if absent:
        return [
            _fail(
                "example-library-entry-sections",
                f"sdl_sections of entry {entry.get('id')!r} lists sections absent from the validated SDL: {absent}",
                relative_path,
            )
        ]
    return []


def _check_sdl(source: str | Path, relative_path: str, *, kind: str, subject: str) -> list[PolicyFailure]:
    """Parse SDL text, or an SDL file through the file boundary, and fail on errors or advisories."""
    try:
        scenario = parse_sdl_file(source) if isinstance(source, Path) else parse_sdl(source)
    except Exception as exc:  # noqa: BLE001 - render parser/validator failures as policy failures
        return [_fail(f"example-library-{kind}-body", f"{subject} is not valid SDL: {exc}", relative_path)]
    failures: list[PolicyFailure] = []
    if scenario.advisories:
        failures.append(
            _fail(
                f"example-library-{kind}-advisory",
                f"{subject} produced advisories: " + "; ".join(scenario.advisories),
                relative_path,
            )
        )
    return failures


def check_template_body(entry: dict[str, Any], body: dict[str, Any], relative_path: str) -> list[PolicyFailure]:
    """Validate a template body as SDL and check the entry's declared sections against it."""
    failures = _check_sdl(
        yaml.safe_dump(body, sort_keys=False), relative_path, kind="template", subject="template body"
    )
    return failures or _check_declared_sections(entry, body, relative_path)


def check_worked_example_file(path: Path, relative_path: str, entry: dict[str, Any]) -> list[PolicyFailure]:
    """Require the worked-example file and, for a validated entry, validate it as SDL."""
    if not path.is_file():
        return [
            _fail("example-library-path-missing", f"referenced path does not exist: {relative_path}", relative_path)
        ]
    if entry.get("validation_status") != VALIDATED:
        return []
    failures = _check_sdl(path, relative_path, kind="worked-example", subject="worked example")
    # Use the sdl-yaml/v1 loader that parse_sdl_file used; YAML 1.1 yaml.safe_load can reject valid SDL.
    return failures or _check_declared_sections(
        entry, load_sdl_fragment(path.read_text(encoding="utf-8")), relative_path
    )
