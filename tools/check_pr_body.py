#!/usr/bin/env python3
"""Validate pull request bodies with checker code loaded from the base ref.

The GitHub event payload and pull request body are untrusted input.  This
module deliberately uses only the standard library, never executes body text,
and performs read-only GitHub API requests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Resolve only the script's own base-owned bundle, including under python -I.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.pr_body_issue_scope import GitHubIssueLookup, IssueFacts, requirement_uids  # noqa: E402

RULE_SECTION = "required-section"
RULE_SUMMARY = "substantive-summary"
RULE_ISSUES = "issue-tracking"
RULE_VERIFICATION = "substantive-verification"

# The section structure rendered by Ground Control's gc_render_pr_body. The
# optional trailing Documentation section is not required.
REQUIRED_SECTIONS = (
    "Summary",
    "Requirement UIDs",
    "Related Issues",
    "ADR Impact",
    "Changes",
    "Test Plan",
    "Ground Control Checks",
    "Traceability",
    "Checklist",
)
SUMMARY_SECTION = "summary"
TRACKING_SECTION = "related issues"
VERIFICATION_SECTION = "test plan"

_CHECKBOX_LINE = re.compile(r"^[ \t]*[-*+][ \t]+\[[ xX]\].*$", re.MULTILINE)
_PLACEHOLDER = re.compile(
    r"(?:\b(?:todo|tbd|placeholder|n/?a)\b|brief description|add (?:context|details)|"
    r"describe (?:the )?(?:problem|fix|verification)|#(?:xx|n)\b)",
    re.IGNORECASE,
)
_EVIDENCE_HINT = re.compile(
    r"(?:`[^`]+`|\b(?:pass(?:ed|es)?|test(?:ed|s)?|verify|verified|verification|"
    r"nox|pytest|ruff|mypy|manual(?:ly)?|not run|not applicable|build|smoke)\b)",
    re.IGNORECASE,
)
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


IssueLookup = Callable[[int], IssueFacts]


@dataclass(frozen=True)
class BodyViolation:
    """One stable, machine-readable body-policy violation."""

    rule_id: str
    message: str


def _strip_ignored(text: str) -> str:
    """Remove HTML comments and fenced code before interpreting policy text."""

    without_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    kept: list[str] = []
    fence: tuple[str, int] | None = None
    for line in without_comments.splitlines():
        marker = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if fence is None:
            if marker:
                token = marker.group(1)
                fence = (token[0], len(token))
                continue
            kept.append(line)
            continue
        if marker:
            token = marker.group(1)
            if token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
    return "\n".join(kept)


def _level_two_heading(line: str) -> str | None:
    if not line.startswith("##") or len(line) < 3 or line[2] not in " \t":
        return None
    name = line[3:].strip().casefold()
    return name or None


def _sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        name = _level_two_heading(line)
        if name is None:
            current_lines.append(line)
            continue
        if current_name is not None:
            sections.setdefault(current_name, []).append("\n".join(current_lines).strip())
        current_name = name
        current_lines = []
    if current_name is not None:
        sections.setdefault(current_name, []).append("\n".join(current_lines).strip())
    return sections


def _meaningful(text: str, *, minimum_words: int = 3) -> bool:
    # Placeholder phrases carry no content, so judge only the text that remains.
    # Prose that merely mentions such a word (for example "non-placeholder")
    # still counts.
    remaining = re.sub(r"[*_`#]", "", _PLACEHOLDER.sub(" ", text)).strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", remaining)
    return len(remaining) >= 12 and len(words) >= minimum_words


def _issue_numbers(body: str, keyword: str) -> tuple[int, ...]:
    """Return unique standalone same-repository references in source order."""

    cleaned = _strip_ignored(body)
    numbers: list[int] = []
    for line in cleaned.splitlines():
        parts = line.strip(" \t").split()
        if len(parts) != 2 or parts[0] != keyword or not parts[1].startswith("#"):
            continue
        reference = parts[1].removeprefix("#")
        if reference.isascii() and reference.isdecimal() and not reference.startswith("0"):
            numbers.append(int(reference))
    return tuple(dict.fromkeys(numbers))


def closing_issue_numbers(body: str) -> tuple[int, ...]:
    """Return unique standalone ``Closes #N`` references in source order."""

    return _issue_numbers(body, "Closes")


def no_issue_reasons(body: str) -> tuple[str, ...]:
    """Return reasons from standalone ``No issue: ...`` declarations."""

    cleaned = _strip_ignored(body)
    reasons: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip(" \t")
        prefix = "No issue:"
        if stripped.startswith(prefix):
            reasons.append(stripped.removeprefix(prefix).strip())
    return tuple(reasons)


def _closing_reference_pattern(repository: str) -> re.Pattern[str]:
    """Match the closing references GitHub reads for issues in ``repository``.

    GitHub links an issue for closure when a closing keyword, optionally
    followed by a colon, is directly followed by a reference to an issue: the
    short ``#N`` form, ``owner/repository#N``, or the issue URL. Other mentions
    of an issue, and references to another repository, do not close an issue in
    this repository.
    """

    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("repository must have owner/repository form")
    name = re.escape(repository)
    return re.compile(
        r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)(?::[ \t]*|[ \t]+)"
        rf"(?:{name}#|https?://github\.com/{name}/issues/|#)\d+(?!\w)",
        re.IGNORECASE,
    )


def closing_references(text: str, repository: str) -> tuple[str, ...]:
    """Return the GitHub closing references in ``text`` for ``repository``."""

    return tuple(match.group(0) for match in _closing_reference_pattern(repository).finditer(text))


def is_exempt_automation(event: dict[str, Any]) -> bool:
    """Limit exemptions to Dependabot and the repository release-please lane."""

    pull_request = event.get("pull_request", {})
    if not isinstance(pull_request, dict):
        return False
    author = str(pull_request.get("user", {}).get("login", ""))
    head = pull_request.get("head", {})
    head_ref = str(head.get("ref", "")) if isinstance(head, dict) else ""
    trusted_release_action = author == "github-actions[bot]" and head_ref.startswith("release-please--branches--")
    return author in {"dependabot[bot]", "release-please[bot]"} or trusted_release_action


def _validate_required_sections(sections: dict[str, list[str]]) -> list[BodyViolation]:
    violations: list[BodyViolation] = []
    for heading in REQUIRED_SECTIONS:
        name = heading.casefold()
        contents = sections.get(name, [])
        if len(contents) != 1:
            violations.append(
                BodyViolation(
                    RULE_SECTION,
                    f"PR body must contain exactly one '## {heading}' section; found {len(contents)}.",
                )
            )
        # Summary, Related Issues and Test Plan have their own content rules.
        elif not contents[0] and name not in {
            SUMMARY_SECTION,
            TRACKING_SECTION,
            VERIFICATION_SECTION,
        }:
            violations.append(
                BodyViolation(
                    RULE_SECTION,
                    f"'## {heading}' must not be empty or placeholder-only.",
                )
            )
    return violations


def _validate_summary(sections: dict[str, list[str]]) -> list[BodyViolation]:
    summaries = sections.get(SUMMARY_SECTION, [])
    if len(summaries) != 1 or _meaningful(summaries[0]):
        return []
    return [BodyViolation(RULE_SUMMARY, "Summary must describe the change in non-placeholder prose.")]


def _inspect_issue(number: int, keyword: str, issue_lookup: IssueLookup) -> BodyViolation | None:
    # Fail closed on API and configuration errors from the injected lookup.
    try:
        issue = issue_lookup(number)
    except Exception as exc:
        violation = BodyViolation(RULE_ISSUES, f"Could not verify issue #{number}: {exc}")
    else:
        violation = None
        if not issue.exists:
            violation = BodyViolation(
                RULE_ISSUES,
                f"{keyword} #{number} does not target an issue in this repository.",
            )
        elif not issue.is_open:
            violation = BodyViolation(
                RULE_ISSUES,
                f"{keyword} #{number} targets an issue that is not open.",
            )
        elif keyword != (expected := "Refs" if issue.requirement_uids else "Closes"):
            violation = BodyViolation(
                RULE_ISSUES,
                f"Issue #{number} requires '{expected} #{number}' for its requirement scope.",
            )
    return violation


def _validate_issues(sections: dict[str, list[str]], issue_lookup: IssueLookup) -> list[BodyViolation]:
    tracking = sections.get(TRACKING_SECTION, [])
    if len(tracking) != 1:
        return []
    content = tracking[0]
    declarations = [(keyword, number) for keyword in ("Closes", "Refs") for number in _issue_numbers(content, keyword)]
    reasons = no_issue_reasons(content)
    if declarations and reasons:
        return [
            BodyViolation(
                RULE_ISSUES,
                "Related Issues must use either issue references or one 'No issue: ...' declaration, not both.",
            )
        ]
    if declarations:
        return [
            violation
            for keyword, number in declarations
            if (violation := _inspect_issue(number, keyword, issue_lookup)) is not None
        ]
    if len(reasons) != 1 or not _meaningful(reasons[0], minimum_words=2):
        return [
            BodyViolation(
                RULE_ISSUES,
                "Related Issues needs open same-repository 'Closes #N' or 'Refs #N' lines or one substantive "
                "'No issue: ...' declaration.",
            )
        ]
    return []


def _validate_closing_routes(body: str, pattern: re.Pattern[str]) -> list[BodyViolation]:
    # A closing reference anywhere else in the body, or a non-standalone one in
    # Related Issues, would bypass the declared lifecycle route. Comments and
    # fenced examples have already been removed.
    violations: list[BodyViolation] = []
    section: str | None = None
    for line in body.splitlines():
        section = _level_two_heading(line) or section
        if section == TRACKING_SECTION and closing_issue_numbers(line):
            continue
        violations.extend(
            BodyViolation(
                RULE_ISSUES,
                f"'{match.group(0)}' is a GitHub closing reference; declare closure only as a standalone "
                "'Closes #N' line in Related Issues, or reword the mention.",
            )
            for match in pattern.finditer(line)
        )
    return violations


def _validate_verification(sections: dict[str, list[str]]) -> list[BodyViolation]:
    verification = sections.get(VERIFICATION_SECTION, [])
    if len(verification) != 1:
        return []
    # Checklist attestations are not evidence; the remaining text must be.
    content = _CHECKBOX_LINE.sub("", verification[0]).strip()
    if _meaningful(content, minimum_words=2) and _EVIDENCE_HINT.search(content):
        return []
    return [
        BodyViolation(
            RULE_VERIFICATION,
            "Test Plan must record substantive commands and outcomes, or a reason a check was not run, "
            "beyond its checklist.",
        )
    ]


def validate_pr_body(body: str, issue_lookup: IssueLookup, *, repository: str) -> list[BodyViolation]:
    """Validate a body in the Ground Control rendered structure for ``repository``."""

    closing_pattern = _closing_reference_pattern(repository)
    cleaned = _strip_ignored(body)
    sections = _sections(cleaned)
    violations = _validate_required_sections(sections)
    violations.extend(_validate_summary(sections))
    violations.extend(_validate_issues(sections, issue_lookup))
    violations.extend(_validate_closing_routes(cleaned, closing_pattern))
    violations.extend(_validate_verification(sections))
    return violations


def _read_json_object(path: Path, description: str) -> dict[str, Any]:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError(f"{description} must not be a symbolic link")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{description} must be a regular file")
    with resolved.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object")
    return payload


def _event(path: Path) -> dict[str, Any]:
    return _read_json_object(path, "event payload")


def _fixture_lookup(path: Path) -> IssueLookup:
    payload = _read_json_object(path, "issues fixture")

    def lookup(number: int) -> IssueFacts:
        value = payload.get(str(number))
        state = value.get("state") if isinstance(value, dict) else value
        body = value.get("body", "") if isinstance(value, dict) else ""
        if not isinstance(body, str):
            raise ValueError("fixture issue body must be a string")
        return IssueFacts(state is not None, state == "open", requirement_uids(body))

    return lookup


def _open_issue_report(body: str, issue_lookup: IssueLookup, pr_number: int | str) -> str:
    numbers = closing_issue_numbers(body)
    references = _issue_numbers(body, "Refs")
    reasons = no_issue_reasons(body)
    open_numbers: list[int] = []
    errors: list[str] = []
    for number in numbers:
        # A failed lookup must be visible in the audit without mutating issues.
        try:
            issue = issue_lookup(number)
        except Exception as exc:
            errors.append(f"- Could not inspect `#{number}`: {exc}")
            continue
        if not issue.exists:
            errors.append(f"- Could not inspect `#{number}`: no same-repository issue found")
        elif issue.is_open:
            open_numbers.append(number)
    lines = [f"## Closing-issue audit for PR #{pr_number}", ""]
    if open_numbers:
        lines.append("The following declared closing issues remain open:")
        lines.extend(f"- `#{number}`" for number in open_numbers)
    elif numbers and not errors:
        lines.append("All declared closing issues are closed.")
    elif reasons:
        lines.append("The pull request declared that no issue was required.")
    elif not numbers and not references:
        lines.append("No issue-tracking declaration was found.")
    if errors:
        lines.extend(("", "Inspection errors:", *errors))
    if references:
        lines.extend(
            (
                "",
                "Non-closing references (closure requires post-merge requirement verification):",
            )
        )
        lines.extend(f"- `#{number}`" for number in references)
    lines.extend(("", "This audit is read-only and never closes issues."))
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-path", type=Path, default=None)
    parser.add_argument("--issues-file", type=Path, default=None)
    parser.add_argument("--report-open-closing-issues", action="store_true")
    parser.add_argument("--summary-file", type=Path, default=None)
    return parser


def _event_path(argument: Path | None) -> Path:
    configured = os.getenv("GITHUB_EVENT_PATH")
    path = argument or (Path(configured) if configured else None)
    if path is None:
        raise ValueError("GITHUB_EVENT_PATH or --event-path is required")
    return path


def _write_report(args: argparse.Namespace, body: str, lookup: IssueLookup, pr_number: int | str) -> None:
    report = _open_issue_report(body, lookup, pr_number)
    if args.summary_file:
        requested = args.summary_file.expanduser()
        destination = requested.parent.resolve(strict=True) / requested.name
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError("summary file must be a regular file and not a symbolic link")
        destination.write_text(report, encoding="utf-8")
    else:
        print(report, end="")


def _validation_result(violations: list[BodyViolation]) -> int:
    result = 0
    if violations:
        print("pr-body-guard: rejected pull request body", file=sys.stderr)
        for violation in violations:
            print(f"- [{violation.rule_id}] {violation.message}", file=sys.stderr)
        result = 1
    else:
        print("pr-body-guard: OK")
    return result


def _run(args: argparse.Namespace) -> int:
    event = _event(_event_path(args.event_path))
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ValueError("event has no pull_request object")
    body = pull_request.get("body")
    if not isinstance(body, str):
        raise ValueError("event pull_request.body must be a string")
    if not args.report_open_closing_issues and is_exempt_automation(event):
        print("pr-body-guard: exempt trusted automation")
        return 0
    repository = str(event.get("repository", {}).get("full_name") or os.getenv("GITHUB_REPOSITORY", ""))
    lookup = (
        _fixture_lookup(args.issues_file)
        if args.issues_file
        else GitHubIssueLookup(repository, os.getenv("GH_TOKEN", ""))
    )
    if args.report_open_closing_issues:
        _write_report(args, body, lookup, pull_request.get("number", "unknown"))
        return 0
    return _validation_result(validate_pr_body(body, lookup, repository=repository))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except (OSError, ValueError) as exc:
        print(f"pr-body-guard: configuration error: {exc}", file=sys.stderr)
        result = 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
