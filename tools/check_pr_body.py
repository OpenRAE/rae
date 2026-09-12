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
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RULE_SECTION = "required-section"
RULE_SUMMARY = "plain-language-summary"
RULE_ISSUES = "issue-tracking"
RULE_VERIFICATION = "substantive-verification"

_CHECKBOX_ONLY = re.compile(r"^[ \t]*[-*][ \t]+\[[ xX]\][ \t]*", re.MULTILINE)
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


@dataclass(frozen=True)
class IssueFacts:
    """Issue identity, lifecycle and authoritative requirement scope."""

    exists: bool
    is_open: bool
    requirement_uids: tuple[str, ...] = ()


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


def _summary_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        bullet = line.lstrip()
        if len(bullet) < 3 or bullet[0] not in "-*" or not bullet[1].isspace():
            continue
        label, separator, value = bullet[2:].lstrip().partition(":")
        if not separator:
            continue
        label = label.strip().removeprefix("**").removesuffix("**").casefold()
        value = value.lstrip().removeprefix("**").lstrip()
        if label in {"context", "problem", "fix"}:
            fields[label] = value
    return fields


def _meaningful(text: str, *, minimum_words: int = 3) -> bool:
    normalized = re.sub(r"[*_`#]", "", text).strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", normalized)
    return len(normalized) >= 12 and len(words) >= minimum_words and not _PLACEHOLDER.search(normalized)


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


def _requirement_lines(body: str) -> Iterator[str]:
    """Select the first level 2–4 Requirements section, including subheadings."""
    level: int | None = None
    for line in body.splitlines():
        heading = re.fullmatch(r"(#{1,6})\s(.+)", line)
        if heading:
            depth = len(heading[1])
            if level is not None and depth <= level:
                break
            if level is None and 2 <= depth <= 4 and heading[2].strip().casefold() == "requirements":
                level = depth
            continue
        if level is not None:
            yield line


def _leading_uids(line: str) -> Iterator[str]:
    bullet = re.fullmatch(r"\s*[-*+]\s+(\S.*)", line)
    if not bullet:
        return
    for token in re.split(r"[\s,;]+", bullet[1]):
        uid = token.lstrip("`[(").rstrip("`)].:")
        if len(uid) > 50 or not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[A-Z0-9]*[0-9]", uid):
            break
        yield uid


def requirement_uids(body: str) -> tuple[str, ...]:
    """Read authoritative issue scope using the delivery workflow convention.

    A same-or-higher heading ends the first Requirements section; only the
    leading UID run of each bullet declares scope. This is not a PR claim.
    """
    return tuple(dict.fromkeys(uid for line in _requirement_lines(body) for uid in _leading_uids(line)))


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


def _tracking_sections(sections: dict[str, list[str]]) -> list[str]:
    """Accept the former heading while existing PRs and tooling migrate."""

    return [
        content for name in ("issue tracking", "issues closed", "related issues") for content in sections.get(name, [])
    ]


def _validate_required_sections(sections: dict[str, list[str]]) -> list[BodyViolation]:
    violations: list[BodyViolation] = []
    for name in ("plain-language summary", "verification"):
        count = len(sections.get(name, []))
        if count != 1:
            violations.append(
                BodyViolation(
                    RULE_SECTION,
                    f"PR body must contain exactly one '## {name.title()}' section; found {count}.",
                )
            )
    tracking_count = len(_tracking_sections(sections))
    if tracking_count != 1:
        violations.append(
            BodyViolation(
                RULE_SECTION,
                "PR body must contain exactly one '## Issue Tracking' section; "
                f"found {tracking_count} ('## Related Issues' and the former '## Issues Closed' are also accepted).",
            )
        )
    return violations


def _validate_summary(sections: dict[str, list[str]]) -> list[BodyViolation]:
    summaries = sections.get("plain-language summary", [])
    if len(summaries) != 1:
        return []
    fields = _summary_fields(summaries[0])
    return [
        BodyViolation(
            RULE_SUMMARY,
            f"Plain-language summary needs a non-placeholder {field.title()} bullet.",
        )
        for field in ("context", "problem", "fix")
        if field not in fields or not _meaningful(fields[field])
    ]


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


def _validate_issues(sections: dict[str, list[str]], issue_lookup: IssueLookup, body: str) -> list[BodyViolation]:
    tracking = _tracking_sections(sections)
    violations: list[BodyViolation] = []
    if len(tracking) == 1:
        content = tracking[0]
        declarations = [
            (keyword, number) for keyword in ("Closes", "Refs") for number in _issue_numbers(content, keyword)
        ]
        reasons = no_issue_reasons(content)
        if declarations and reasons:
            violations.append(
                BodyViolation(
                    RULE_ISSUES,
                    "Issue tracking must use either issue references or one 'No issue: ...' declaration, not both.",
                )
            )
        elif declarations:
            violations.extend(
                violation
                for keyword, number in declarations
                if (violation := _inspect_issue(number, keyword, issue_lookup)) is not None
            )
        elif len(reasons) != 1 or not _meaningful(reasons[0], minimum_words=2):
            violations.append(
                BodyViolation(
                    RULE_ISSUES,
                    "Issue tracking needs open same-repository 'Closes #N' or 'Refs #N' lines or one substantive "
                    "'No issue: ...' declaration.",
                )
            )
        violations.extend(_validate_closing_routes(body, content))
    return violations


def _validate_closing_routes(body: str, content: str) -> list[BodyViolation]:
    # Another section or alternate GitHub closing keyword cannot bypass the
    # declared lifecycle route. Comments and examples have already been removed.
    tracking_lines = {line.strip() for line in content.splitlines()}
    violations: list[BodyViolation] = []
    for line in body.splitlines():
        closing = re.search(
            r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+(?:https://github\.com/|[\w.-]+/[\w.-]+#|#)[0-9\w]",
            line,
            re.IGNORECASE,
        )
        if closing and (not closing_issue_numbers(line) or line.strip() not in tracking_lines):
            violations.append(
                BodyViolation(RULE_ISSUES, "Closing references must use standalone 'Closes #N' in Issue tracking.")
            )
    return violations


def _validate_verification(sections: dict[str, list[str]]) -> list[BodyViolation]:
    verification = sections.get("verification", [])
    if len(verification) != 1:
        return []
    content = _CHECKBOX_ONLY.sub("", verification[0]).strip()
    if _meaningful(content, minimum_words=2) and _EVIDENCE_HINT.search(content):
        return []
    return [
        BodyViolation(
            RULE_VERIFICATION,
            "Verification must record substantive commands, checks, or a reason a check was not run.",
        )
    ]


def validate_pr_body(body: str, issue_lookup: IssueLookup) -> list[BodyViolation]:
    """Validate the human-authored body against the repository policy."""

    cleaned = _strip_ignored(body)
    sections = _sections(cleaned)
    violations = _validate_required_sections(sections)
    violations.extend(_validate_summary(sections))
    violations.extend(_validate_issues(sections, issue_lookup, cleaned))
    violations.extend(_validate_verification(sections))
    return violations


class GitHubIssueLookup:
    """Read-only lookup for issues in exactly one GitHub repository."""

    def __init__(self, repository: str, token: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("GITHUB_REPOSITORY must have owner/repository form")
        if not token:
            raise ValueError("GH_TOKEN is required to verify closing issues")
        self._repository = repository
        self._token = token

    def __call__(self, number: int) -> IssueFacts:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self._repository}/issues/{number}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "OpenRAE-pr-body-guard",
            },
        )
        try:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler())
            with opener.open(request, timeout=15) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return IssueFacts(False, False)
            raise RuntimeError(f"GitHub returned HTTP {exc.code}") from exc
        if (
            not isinstance(payload, dict)
            or "body" not in payload
            or payload["body"] is not None
            and not isinstance(payload["body"], str)
        ):
            raise RuntimeError("GitHub returned a malformed issue response")
        # Pull requests also appear through the issues endpoint and cannot be
        # used to satisfy an issue-closing requirement.
        exists = "pull_request" not in payload
        return IssueFacts(
            exists,
            exists and payload.get("state") == "open",
            requirement_uids(payload["body"] or ""),
        )


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
    return _validation_result(validate_pr_body(body, lookup))


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
