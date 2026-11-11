from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_agent_guidance import (  # noqa: E402
    AGENT_GUIDANCE_RELATIVE_PATH,
    ALLOWED_AUDIENCES,
    REQUIRED_CATEGORIES,
    REQUIREMENT_REF,
    evaluate_agent_guidance,
)

_GOOD_GUIDANCE = """profile: raes-agent-guidance
version: 1
requirement_refs: [AUT-811]
source_refs: [AGENTS.md]
recommended_workflow: [raes_tool_surface, raes_agent_guidance]
guidance:
  scope_boundaries:
    - id: scope
      audience: [contributor, operator]
      surfaces: [mcp]
      statement: This entry describes a substantive scope boundary for agents.
      source_refs: [AGENTS.md]
  invariants:
    - id: invariant
      audience: [contributor]
      surfaces: [policy]
      statement: This entry describes a substantive invariant for contributors.
      source_refs: [.gc/plan-rules.md]
  review_priorities:
    - id: review
      audience: [contributor]
      surfaces: [tests]
      statement: This entry describes a substantive review priority for work.
      source_refs: [docs/explain/reference/coding-standards.md]
  safe_operating_expectations:
    - id: safe
      audience: [operator]
      surfaces: [mcp]
      statement: This entry describes a substantive safe operating expectation.
      source_refs: [docs/explain/getting-started.md]
"""


def _seed_repo(tmp_path: Path, body: str = _GOOD_GUIDANCE) -> Path:
    path = tmp_path / AGENT_GUIDANCE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return tmp_path


def _flagged(failures, marker: str) -> bool:
    needle = marker.lower()
    return any(failure.rule_id == marker or needle in failure.render().lower() for failure in failures)


def test_good_guidance_has_no_failures(tmp_path: Path) -> None:
    assert evaluate_agent_guidance(_seed_repo(tmp_path)) == []


def test_requirement_ref_is_aut_811() -> None:
    assert REQUIREMENT_REF == "AUT-811"


def test_allowed_audiences_are_contributor_and_operator() -> None:
    assert {"contributor", "operator"} == ALLOWED_AUDIENCES


def test_required_categories_cover_aut_811_clauses() -> None:
    assert REQUIRED_CATEGORIES == (
        "scope_boundaries",
        "invariants",
        "review_priorities",
        "safe_operating_expectations",
    )


def test_missing_category_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_GUIDANCE.replace(
        """  invariants:
    - id: invariant
      audience: [contributor]
      surfaces: [policy]
      statement: This entry describes a substantive invariant for contributors.
      source_refs: [.gc/plan-rules.md]
""",
        "  invariants: []\n",
    )
    failures = evaluate_agent_guidance(_seed_repo(tmp_path, body))
    assert _flagged(failures, "agent-guidance-category")


def test_invalid_audience_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_GUIDANCE.replace("audience: [operator]", "audience: [auditor]", 1)
    failures = evaluate_agent_guidance(_seed_repo(tmp_path, body))
    assert _flagged(failures, "agent-guidance-entry-audience")


def test_duplicate_entry_ids_are_flagged(tmp_path: Path) -> None:
    body = _GOOD_GUIDANCE.replace("id: invariant", "id: scope", 1)
    failures = evaluate_agent_guidance(_seed_repo(tmp_path, body))
    assert _flagged(failures, "agent-guidance-entry-duplicate")


def test_main_reports_a_malformed_waiver_date_as_a_message(tmp_path: Path, capsys) -> None:
    from tools.check_agent_guidance import main

    repo_root = _seed_repo(tmp_path, _GOOD_GUIDANCE.replace("id: invariant", "id: scope", 1))
    waivers = repo_root / "tools" / "policy" / "exceptions.yaml"
    waivers.parent.mkdir(parents=True)
    waivers.write_text(
        "exceptions:\n  - rule_id: agent-guidance-entry-duplicate\n    expires_at: not-a-date\n", encoding="utf-8"
    )

    assert main(["--repo-root", str(repo_root)]) == 1
    assert "agent-guidance: policy exception expires_at must be an ISO date" in capsys.readouterr().err
