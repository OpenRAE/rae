"""Tests for base-ref pull request body governance."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.check_pr_body as pr_body  # noqa: E402
import tools.pr_body_issue_scope as issue_scope  # noqa: E402
from tools.check_pr_body import (  # noqa: E402
    REQUIRED_SECTIONS,
    RULE_ISSUES,
    RULE_SECTION,
    RULE_SUMMARY,
    RULE_VERIFICATION,
    IssueFacts,
    closing_issue_numbers,
    closing_references,
    is_exempt_automation,
    main,
    no_issue_reasons,
)

CHECKER = REPO_ROOT / "tools/check_pr_body.py"
TEMPLATE = REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md"
REPOSITORY = "OpenRAE/rae"

# Verbatim gc_render_pr_body output for a requirement-free quickfix run and a
# requirement-backed implement run, both with test notes.
GROUND_CONTROL_REQUIREMENT_FREE = """## Summary

The body guard now validates the section structure that Ground Control renders.

## Requirement UIDs

- (none — bug/refactor/maintenance run; see Traceability section below)

## Related Issues

Closes #123

## ADR Impact

- No ADR required

## Changes

- Fixed the closing-route detection for prose issue mentions

## Test Plan

- [x] Unit tests pass
- [x] Integration tests pass if applicable
- [x] Configured completion command passes
- [x] No coverage regression

Ran `pytest implementations/python/tests/test_pr_body_guard.py`: passed.

## Ground Control Checks

- [x] Configured repository policy command passes
- [x] Pre-push code review and test-quality review not run for this lane; CI and repository policy gates enforced

## Traceability

- IMPLEMENTS: (none — bug/refactor/maintenance run)
- TESTS: (none — documentation/configuration/structural-invariant run)

## Checklist

- [x] Code follows the project's coding standards
- [x] Changelog: owned by Release Please (generated from the Conventional Commit PR title; no per-PR fragment)
- [x] Architectural docs updated if stack, package structure, or key behaviors changed"""

GROUND_CONTROL_REQUIREMENT_BACKED = """## Summary

The participant-opacity proof lane admits Isabelle through verified native-client inputs.

## Requirement UIDs

- `SEM-218`

## Related Issues

Refs #123

## ADR Impact

- ADR-103

## Changes

- Corrected the issue 1219 legacy migration for group-writable caches

## Test Plan

- [x] Unit tests pass
- [x] Integration tests pass if applicable
- [x] Configured completion command passes
- [x] No coverage regression

`nox -s verify-completion` and `make policy` passed on the merged tree.

## Ground Control Checks

- [x] Configured repository policy command passes
- [x] Pre-push code review and test-quality review completed; all findings fixed or dispositioned

## Traceability

- IMPLEMENTS: tools/isabelle_tool.py
- TESTS: implementations/python/tests/test_isabelle_tool.py

## Checklist

- [x] Code follows the project's coding standards
- [x] Changelog: owned by Release Please (generated from the Conventional Commit PR title; no per-PR fragment)
- [x] Architectural docs updated if stack, package structure, or key behaviors changed

## Documentation

Verified unchanged: no documentation surface in scope."""


def _body(issue: int = 123) -> str:
    return GROUND_CONTROL_REQUIREMENT_FREE.replace("Closes #123", f"Closes #{issue}")


def validate_pr_body(body: str, lookup) -> list[pr_body.BodyViolation]:
    return pr_body.validate_pr_body(body, lookup, repository=REPOSITORY)


def _lookup(states: dict[int, str]):
    def lookup(number: int) -> IssueFacts:
        state = states.get(number)
        return IssueFacts(state is not None, state == "open")

    return lookup


def _rules(body: str, states: dict[int, str] | None = None) -> set[str]:
    lookup = _lookup({123: "open"} if states is None else states)
    return {violation.rule_id for violation in validate_pr_body(body, lookup)}


def test_complete_body_passes() -> None:
    assert validate_pr_body(_body(), _lookup({123: "open"})) == []


@pytest.mark.parametrize(
    ("body", "requirements"),
    [(GROUND_CONTROL_REQUIREMENT_FREE, ()), (GROUND_CONTROL_REQUIREMENT_BACKED, ("SEM-218",))],
)
def test_ground_control_rendered_bodies_pass_unmodified(body: str, requirements: tuple[str, ...]) -> None:
    assert validate_pr_body(body, lambda _number: IssueFacts(True, True, requirements)) == []


def test_template_declares_the_ground_control_section_structure() -> None:
    headings = [
        line[3:].strip() for line in TEMPLATE.read_text(encoding="utf-8").splitlines() if line.startswith("## ")
    ]
    assert headings == [*REQUIRED_SECTIONS, "Documentation"]


def test_unfilled_template_is_rejected() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    assert _rules(template) == {RULE_SECTION, RULE_SUMMARY, RULE_ISSUES, RULE_VERIFICATION}


def test_legacy_plain_language_structure_no_longer_satisfies_policy() -> None:
    legacy = """## Plain-language summary

- **Context:** Contributors need one reviewable delivery contract.
- **Problem:** Empty pull request bodies hide delivery scope and evidence.
- **Fix:** The base-ref checker validates structured human-authored content.

## Issue tracking

No issue: Corrects a small documentation typo.

## Verification

- `pytest tests/test_pr_body_guard.py`: passed
"""
    assert RULE_SECTION in _rules(legacy)


def test_requirement_backed_refs_pass_through_real_issue_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    class Opener:
        def open(self, *_args, **_kwargs) -> io.StringIO:
            return io.StringIO(json.dumps({"state": "open", "body": "## Requirements\n- SEM-218"}))

    monkeypatch.setattr(issue_scope.urllib.request, "build_opener", lambda *_args: Opener())
    lookup = pr_body.GitHubIssueLookup("OpenRAE/rae", "test-token")
    body = _body().replace("Closes #123", "Refs #123")
    assert validate_pr_body(body, lookup) == []


def test_requirement_backed_closing_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class Opener:
        def open(self, *_args, **_kwargs) -> io.StringIO:
            return io.StringIO(json.dumps({"state": "open", "body": "## Requirements\n- SEM-218"}))

    monkeypatch.setattr(issue_scope.urllib.request, "build_opener", lambda *_args: Opener())
    lookup = pr_body.GitHubIssueLookup("OpenRAE/rae", "test-token")
    assert RULE_ISSUES in {item.rule_id for item in validate_pr_body(_body(), lookup)}


@pytest.mark.parametrize("requirements", [(), ("SEM-218",)])
@pytest.mark.parametrize("keyword", ["Refs", "Closes"])
def test_issue_lifecycle_route_matrix(requirements: tuple[str, ...], keyword: str) -> None:
    body = _body().replace("Closes", keyword)
    violations = validate_pr_body(body, lambda _number: IssueFacts(True, True, requirements))
    assert bool(violations) is (keyword != ("Refs" if requirements else "Closes"))


@pytest.mark.parametrize("reference", ["Refs #123", "Closes #123", "fixes #123", "Resolves OpenRAE/rae#123"])
def test_refs_cannot_hide_a_second_closing_route(reference: str) -> None:
    body = _body().replace("Closes #123", "Refs #123") + f"\n## Notes\n{reference}\n"
    violations = validate_pr_body(body, lambda _number: IssueFacts(True, True, ("SEM-218",)))
    # Repeating a non-closing reference is harmless; every closing variant is not.
    assert bool(violations) is (reference != "Refs #123")


@pytest.mark.parametrize(
    "keyword", ["close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved"]
)
@pytest.mark.parametrize("separator", [" ", ": ", ":"])
@pytest.mark.parametrize("target", ["#123", "OpenRAE/rae#123", "https://github.com/OpenRAE/rae/issues/123"])
def test_all_closing_aliases_are_rejected_for_requirement_backed_work(
    keyword: str, separator: str, target: str
) -> None:
    body = _body().replace("Closes #123", "Refs #123") + f"\n## Notes\n{keyword}{separator}{target}\n"
    assert validate_pr_body(body, lambda _number: IssueFacts(True, True, ("SEM-218",)))


def test_prose_keyword_cannot_hide_a_later_closing_reference() -> None:
    body = _body().replace("Closes #123", "Refs #123") + "\n## Notes\nWe fix tracking; this closes #123.\n"
    assert validate_pr_body(body, lambda _number: IssueFacts(True, True, ("SEM-218",)))


def test_repeated_standalone_closing_line_outside_related_issues_is_rejected() -> None:
    assert RULE_ISSUES in _rules(_body() + "\n## Notes\nCloses #123\n")


def test_non_standalone_closing_reference_inside_related_issues_is_rejected() -> None:
    body = _body().replace("Closes #123", "Closes #123\nThis also fixes #123.")
    assert RULE_ISSUES in _rules(body)


@pytest.mark.parametrize("requirements", [(), ("SEM-218",)])
@pytest.mark.parametrize(
    "mention",
    [
        "Corrected the #1219 legacy migration",
        "Follow-up to #1219 legacy migration",
        "Fixed in #1219, the legacy migration",
        "Fixed issue #1219 legacy migration",
        "Prefixed #1219 labels in the migration",
        "Fixed #1219abc labels in the migration",
        "Fixes other-org/other-repo#1219 upstream",
        "Fixes OpenRAE/rae-docs#1219 upstream",
        "Fixed https://github.com/OpenRAE/rae/pull/1219 review feedback",
        "Fixed https://github.com/OpenRAE/rae-docs/issues/1219 upstream",
    ],
)
def test_prose_issue_mentions_that_github_does_not_close_are_accepted(
    mention: str, requirements: tuple[str, ...]
) -> None:
    body = _body().replace("- Fixed the closing-route detection", f"- {mention}; fixed the closing-route detection")
    seen: list[int] = []

    def lookup(number: int) -> IssueFacts:
        seen.append(number)
        return IssueFacts(True, True, requirements)

    route = "Refs" if requirements else "Closes"
    assert validate_pr_body(body.replace("Closes #123", f"{route} #123"), lookup) == []
    assert seen == [123]


@pytest.mark.parametrize("requirements", [(), ("SEM-218",)])
def test_github_closing_keyword_in_a_change_bullet_is_rejected(requirements: tuple[str, ...]) -> None:
    # GitHub reads "Fixed #1219" as closing #1219 wherever it appears, which
    # would bypass the declared Related Issues route for that issue.
    route = "Refs" if requirements else "Closes"
    body = _body().replace("Closes #123", f"{route} #123")
    body = body.replace("- Fixed the closing-route detection", "- Fixed #1219 legacy migration; fixed the detection")
    violations = validate_pr_body(body, lambda _number: IssueFacts(True, True, requirements))
    assert [item.rule_id for item in violations] == [RULE_ISSUES]
    assert "'Fixed #1219' is a GitHub closing reference" in violations[0].message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("fixes openrae/RAE#5 and Resolves: #6", ("fixes openrae/RAE#5", "Resolves: #6")),
        (
            "CLOSED https://github.com/OpenRAE/rae/issues/7#issuecomment-1",
            ("CLOSED https://github.com/OpenRAE/rae/issues/7",),
        ),
        ("hotfixes #8, fixes #9x, fixes #10", ("fixes #10",)),
    ],
)
def test_closing_references_follow_github_keyword_grammar(text: str, expected: tuple[str, ...]) -> None:
    assert closing_references(text, REPOSITORY) == expected


@pytest.mark.parametrize("repository", ["", "OpenRAE", "OpenRAE/rae/extra", "Open RAE/rae"])
def test_malformed_repository_is_a_configuration_error_before_lookup(repository: str) -> None:
    def unexpected_lookup(_number: int) -> IssueFacts:
        raise AssertionError("a malformed repository must not query GitHub")

    with pytest.raises(ValueError, match="owner/repository"):
        pr_body.validate_pr_body(_body(), unexpected_lookup, repository=repository)


@pytest.mark.parametrize(
    "declaration",
    [
        "Refs #123\nCloses #123",
        "Refs #123\nNo issue: Small documentation typo correction.",
        "Refs OpenRAE/rae#123",
        "Refs #0123",
        "Refs #123 extra",
        "Refs #１２３",
        "<!-- Refs #123 -->",
        "```\nRefs #123\n```",
    ],
)
def test_requirement_routes_reject_ambiguous_or_hidden_tracking(declaration: str) -> None:
    body = _body().replace("Closes #123", declaration)
    assert validate_pr_body(body, lambda _number: IssueFacts(True, True, ("SEM-218",)))


@pytest.mark.parametrize("facts", [IssueFacts(False, False), IssueFacts(True, False, ("SEM-218",))])
def test_refs_still_require_an_open_issue(facts: IssueFacts) -> None:
    body = _body().replace("Closes #123", "Refs #123")
    assert validate_pr_body(body, lambda _number: facts)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("## Requirements\n- SEM-218 — title", ("SEM-218",)),
        ("### REQUIREMENTS\n* `APP-2`, SEM-218; (GC-O007). title\n* APP-2", ("APP-2", "SEM-218", "GC-O007")),
        ("## Requirements\n### Group\n+ SEM-218\n## Other\n- RUN-311", ("SEM-218",)),
        ("## Requirements\nNo requirements.\n## Requirements\n- SEM-218", ()),
        ("# Requirements\n- SEM-218", ()),
        ("##### Requirements\n- SEM-218", ()),
        ("## Requirements\n- Some prose about SEM-218", ()),
        ("## Requirements\n- SEM-218 description mentions RUN-311", ("SEM-218",)),
        ("## Requirements\n- [ ] SEM-218", ()),
        ("## Requirements\n- sem-218\n- GOV-ABC\n- " + "A" * 49 + "-1", ()),
        ("## Other\n- SEM-218", ()),
    ],
)
def test_authoritative_requirement_scope_convention(body: str, expected: tuple[str, ...]) -> None:
    assert pr_body.requirement_uids(body) == expected


@pytest.mark.parametrize("payload", [{"state": "open"}, {"state": "open", "body": []}])
def test_missing_or_malformed_issue_body_cannot_be_treated_as_requirement_free(
    payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Opener:
        def open(self, *_args, **_kwargs) -> io.StringIO:
            return io.StringIO(json.dumps(payload))

    monkeypatch.setattr(issue_scope.urllib.request, "build_opener", lambda *_args: Opener())
    lookup = pr_body.GitHubIssueLookup("OpenRAE/rae", "test-token")
    assert validate_pr_body(_body(), lookup)


def test_refs_audit_distinguishes_deliberately_non_closing_links() -> None:
    body = _body().replace("Closes #123", "Refs #123")
    report = pr_body._open_issue_report(body, _lookup({123: "open"}), 7)
    assert "Non-closing references" in report
    assert "post-merge requirement verification" in report
    assert "#123" in report
    assert "No issue-tracking declaration" not in report


def test_failed_audit_lookup_never_claims_all_issues_closed() -> None:
    def fail(_number: int) -> IssueFacts:
        raise RuntimeError("unavailable")

    report = pr_body._open_issue_report(_body(), fail, 7)
    assert "All declared closing issues are closed" not in report
    assert "No issue-tracking declaration" not in report
    assert "Inspection errors" in report


def test_missing_audit_issue_is_not_reported_as_closed() -> None:
    report = pr_body._open_issue_report(_body(), _lookup({}), 7)
    assert "All declared closing issues are closed" not in report
    assert "Inspection errors" in report


@pytest.mark.parametrize("heading", REQUIRED_SECTIONS)
def test_each_required_section_is_mandatory_and_unique(heading: str) -> None:
    missing = _body().replace(f"## {heading}\n", "### Removed\n", 1)
    duplicate = _body() + f"\n## {heading}\nExtra content that must not create ambiguity.\n"
    assert RULE_SECTION in _rules(missing)
    assert RULE_SECTION in _rules(duplicate)


@pytest.mark.parametrize(
    "heading", [heading for heading in REQUIRED_SECTIONS if heading not in {"Summary", "Related Issues", "Test Plan"}]
)
def test_placeholder_only_sections_are_rejected(heading: str) -> None:
    sections = _body().split("\n## ")
    index = next(i for i, section in enumerate(sections) if section.startswith(f"{heading}\n"))
    sections[index] = f"{heading}\n\n<!-- Fill in {heading}. -->\n"
    assert _rules("\n## ".join(sections)) == {RULE_SECTION}


@pytest.mark.parametrize(
    "summary",
    ["TODO", "", "<!-- Describe the change. -->", "Small fix.", "TBD: brief description", "N/A", "#N: TODO, TBD"],
)
def test_summary_rejects_placeholders(summary: str) -> None:
    body = _body().replace(
        "The body guard now validates the section structure that Ground Control renders.",
        summary,
    )
    assert RULE_SUMMARY in _rules(body)


def test_summary_prose_mentioning_placeholder_words_is_accepted() -> None:
    body = _body().replace(
        "The body guard now validates the section structure that Ground Control renders.",
        "The guard requires a non-placeholder Summary and removes the TODO marker from the parser.",
    )
    assert validate_pr_body(body, _lookup({123: "open"})) == []


@pytest.mark.parametrize(
    "invalid_line",
    ["Related: Closes #123", "123", "Closes #0123", "Closes #123 extra"],
)
def test_only_standalone_closing_lines_count(invalid_line: str) -> None:
    body = _body().replace("Closes #123", invalid_line)
    assert closing_issue_numbers(body) == ()
    assert RULE_ISSUES in _rules(body)


def test_closing_line_allows_whitespace_and_deduplicates() -> None:
    body = _body().replace("Closes #123", "Closes   #123\n\tCloses\t#123")
    assert closing_issue_numbers(body) == (123,)


def test_substantive_no_issue_declaration_passes_without_lookup() -> None:
    body = _body().replace("Closes #123", "No issue: Corrects a small documentation typo.")

    def unexpected_lookup(_number: int) -> IssueFacts:
        raise AssertionError("no issue declaration must not query GitHub")

    assert no_issue_reasons(body) == ("Corrects a small documentation typo.",)
    assert validate_pr_body(body, unexpected_lookup) == []


@pytest.mark.parametrize(
    "declaration",
    ["No issue:", "No issue: TODO", "No issue: not needed\nNo issue: duplicate declaration"],
)
def test_no_issue_declaration_must_be_unique_and_substantive(declaration: str) -> None:
    body = _body().replace("Closes #123", declaration)
    assert RULE_ISSUES in _rules(body)


def test_no_issue_declaration_cannot_be_mixed_with_closing_references() -> None:
    body = _body().replace("Closes #123", "Closes #123\nNo issue: Corrects a small documentation typo.")
    assert RULE_ISSUES in _rules(body)


@pytest.mark.parametrize("state", ["closed", "missing"])
def test_closing_reference_must_be_an_open_same_repository_issue(state: str) -> None:
    states = {} if state == "missing" else {123: state}
    assert RULE_ISSUES in _rules(_body(), states)


def test_comments_and_fenced_code_cannot_satisfy_policy() -> None:
    hidden = f"<!--\n{_body()}\n-->\n```markdown\n{_body()}\n```\n"
    rules = _rules(hidden)
    assert RULE_SECTION in rules


def test_comments_and_fenced_examples_do_not_add_fake_issue_references() -> None:
    body = _body() + "\n<!-- Closes #999 -->\n```text\nCloses #888\n```\n"
    seen: list[int] = []

    def lookup(number: int) -> IssueFacts:
        seen.append(number)
        return IssueFacts(number == 123, number == 123)

    assert validate_pr_body(body, lookup) == []
    assert seen == [123]


@pytest.mark.parametrize(
    "evidence", ["", "- [x] Ran `pytest` and it passed", "<!-- `pytest`: passed -->", "Looks good to me."]
)
def test_test_plan_checklist_without_evidence_is_rejected(evidence: str) -> None:
    body = _body().replace(
        "Ran `pytest implementations/python/tests/test_pr_body_guard.py`: passed.",
        evidence,
    )
    assert _rules(body) == {RULE_VERIFICATION}


@pytest.mark.parametrize(
    ("author", "sender", "head", "expected"),
    [
        ("dependabot[bot]", "maintainer", "dependabot/pip/x", True),
        ("release-please[bot]", "maintainer", "release-please--branches--dev", True),
        ("github-actions[bot]", "maintainer", "release-please--branches--dev", True),
        ("github-actions[bot]", "maintainer", "feature", False),
        ("human", "github-actions[bot]", "release-please--branches--dev", False),
        ("renovate[bot]", "renovate[bot]", "renovate/x", False),
        ("human", "human", "feature", False),
    ],
)
def test_automation_exemptions_follow_pr_author(author: str, sender: str, head: str, expected: bool) -> None:
    event = {
        "sender": {"login": sender},
        "pull_request": {"user": {"login": author}, "head": {"ref": head}},
    }
    assert is_exempt_automation(event) is expected


def test_cli_uses_event_and_issue_fixture(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    issues = tmp_path / "issues.json"
    event.write_text(
        json.dumps(
            {
                "repository": {"full_name": "OpenRAE/rae"},
                "sender": {"login": "human"},
                "pull_request": {"number": 7, "body": _body(), "user": {"login": "human"}},
            }
        ),
        encoding="utf-8",
    )
    issues.write_text(json.dumps({"123": "open"}), encoding="utf-8")
    assert main(["--event-path", str(event), "--issues-file", str(issues)]) == 0


def test_lookup_failures_and_http_shapes_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOpener:
        def __init__(self, payload: str) -> None:
            self._payload = payload

        def open(self, *_args, **_kwargs) -> io.StringIO:
            return io.StringIO(self._payload)

    def use_payload(payload: str) -> None:
        monkeypatch.setattr(
            issue_scope.urllib.request,
            "build_opener",
            lambda *_args, **_kwargs: FakeOpener(payload),
        )

    with pytest.raises(ValueError, match="owner/repository"):
        pr_body.GitHubIssueLookup("invalid", "token")
    with pytest.raises(ValueError, match="GH_TOKEN"):
        pr_body.GitHubIssueLookup("OpenRAE/rae", "")

    lookup = pr_body.GitHubIssueLookup("OpenRAE/rae", "token")
    use_payload('{"state":"open","body":null}')
    assert lookup(12) == IssueFacts(True, True)
    use_payload('{"state":"open","body":null,"pull_request":{}}')
    assert lookup(12) == IssueFacts(False, False)
    use_payload("[]")
    with pytest.raises(RuntimeError, match="malformed"):
        lookup(12)


def test_validation_and_report_record_lookup_errors() -> None:
    def failing(_number: int) -> IssueFacts:
        raise RuntimeError("offline")

    violations = validate_pr_body(_body(), failing)
    assert any("Could not verify issue #123" in item.message for item in violations)
    report = pr_body._open_issue_report(_body(), failing, 7)
    assert "Inspection errors" in report
    assert "never closes issues" in report
    assert "All declared closing issues are closed" in pr_body._open_issue_report(_body(), _lookup({123: "closed"}), 7)
    assert "No issue-tracking declaration" in pr_body._open_issue_report("No references", _lookup({}), 7)


def test_report_mode_recognizes_no_issue_declaration() -> None:
    body = _body().replace("Closes #123", "No issue: Corrects a small documentation typo.")
    report = pr_body._open_issue_report(body, _lookup({}), 7)
    assert "declared that no issue was required" in report


def test_cli_rejects_missing_or_malformed_events(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert main([]) == 2
    assert main(["--event-path", str(tmp_path / "missing.json")]) == 2
    malformed = tmp_path / "event.json"
    malformed.write_text("[]", encoding="utf-8")
    assert main(["--event-path", str(malformed)]) == 2
    linked = tmp_path / "linked.json"
    linked.symlink_to(malformed)
    assert main(["--event-path", str(linked)]) == 2
    assert "configuration error" in capsys.readouterr().err


def test_cli_exempts_trusted_automation_before_api_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "sender": {"login": "maintainer"},
                "pull_request": {"body": "", "user": {"login": "dependabot[bot]"}},
            }
        ),
        encoding="utf-8",
    )
    assert main(["--event-path", str(event)]) == 0
    assert "exempt trusted automation" in capsys.readouterr().out


def test_cli_renders_rejections_and_stdout_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    event = tmp_path / "event.json"
    issues = tmp_path / "issues.json"
    event.write_text(
        json.dumps({"repository": {"full_name": REPOSITORY}, "pull_request": {"number": 9, "body": "incomplete"}}),
        encoding="utf-8",
    )
    issues.write_text("{}", encoding="utf-8")
    args = ["--event-path", str(event), "--issues-file", str(issues)]
    assert main(args) == 1
    assert "rejected pull request body" in capsys.readouterr().err
    assert main([*args, "--report-open-closing-issues"]) == 0
    assert "Closing-issue audit for PR #9" in capsys.readouterr().out


def test_report_mode_is_read_only_and_lists_open_issues(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    issues = tmp_path / "issues.json"
    summary = tmp_path / "summary.md"
    event.write_text(
        json.dumps(
            {
                "repository": {"full_name": "OpenRAE/rae"},
                "pull_request": {"number": 7, "body": _body()},
            }
        ),
        encoding="utf-8",
    )
    issues.write_text(json.dumps({"123": "open"}), encoding="utf-8")
    assert (
        main(
            [
                "--event-path",
                str(event),
                "--issues-file",
                str(issues),
                "--report-open-closing-issues",
                "--summary-file",
                str(summary),
            ]
        )
        == 0
    )
    assert "`#123`" in summary.read_text(encoding="utf-8")
    assert "read-only" in summary.read_text(encoding="utf-8")


def test_report_mode_rejects_symbolic_link_destination(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    issues = tmp_path / "issues.json"
    target = tmp_path / "target.md"
    summary = tmp_path / "summary.md"
    event.write_text(json.dumps({"pull_request": {"number": 7, "body": _body()}}), encoding="utf-8")
    issues.write_text(json.dumps({"123": "open"}), encoding="utf-8")
    target.write_text("unchanged", encoding="utf-8")
    summary.symlink_to(target)

    result = main(
        [
            "--event-path",
            str(event),
            "--issues-file",
            str(issues),
            "--report-open-closing-issues",
            "--summary-file",
            str(summary),
        ]
    )

    assert result == 2
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_workflows_use_trusted_code_and_read_only_permissions() -> None:
    guard_source = (REPO_ROOT / ".github/workflows/pr-body-policy.yml").read_text(encoding="utf-8")
    audit_source = (REPO_ROOT / ".github/workflows/post-merge-closing-issue-audit.yml").read_text(encoding="utf-8")
    guard = yaml.safe_load(guard_source)
    audit = yaml.safe_load(audit_source)

    assert "pull_request_target" not in guard_source
    checkout = guard["jobs"]["body-guard"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert guard["permissions"] == {"contents": "read", "issues": "read", "pull-requests": "read"}
    assert audit["permissions"] == {"contents": "read", "issues": "read", "pull-requests": "read"}
    assert "gh issue close" not in audit_source
    assert "--method" not in audit_source


@pytest.mark.integration
def test_checker_runs_as_a_standalone_stdlib_script(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    issues = tmp_path / "issues.json"
    event.write_text(
        json.dumps(
            {
                "repository": {"full_name": "OpenRAE/rae"},
                "sender": {"login": "human"},
                "pull_request": {"body": _body(), "user": {"login": "human"}},
            }
        ),
        encoding="utf-8",
    )
    issues.write_text(json.dumps({"123": "open"}), encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key != "GH_TOKEN"}
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--event-path", str(event), "--issues-file", str(issues)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
