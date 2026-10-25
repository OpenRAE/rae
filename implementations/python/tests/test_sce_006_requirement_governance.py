"""SCE-006 uses normal requirement status and traceability enforcement."""

from pathlib import Path

import pytest
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("path", "expected_rules"),
    [
        ("docs/requirements/SCE-006/requirement.md", []),
        ("docs/explain/reference/scenario-variation-and-trial-realization.md", []),
        (
            "implementations/python/packages/raes_processor/unlinked_scheduler.py",
            ["traceability-missing-implements"],
        ),
    ],
)
def test_batch_scheduling_changes_retain_requirement_governance(path: str, expected_rules: list[str]) -> None:
    failures = evaluate_requirement_governance(
        REPO_ROOT,
        [path],
        client=RepositoryRequirementClient(REPO_ROOT),
        requirement_uid="SCE-006",
    )

    assert [failure.rule_id for failure in failures] == expected_rules
