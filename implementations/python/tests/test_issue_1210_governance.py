"""Migration delivery is governed without granting unrelated runtime ownership."""

from pathlib import Path

import pytest
from tools.policy.repository_requirements import RepositoryRequirementClient
from tools.policy.requirement_governance import evaluate_requirement_governance

ROOT = Path(__file__).resolve().parents[3]


def test_progressive_migration_has_governed_delivery_scope():
    client = RepositoryRequirementClient(ROOT)
    paths = [
        "implementations/python/packages/raes/semantic_revisions.py",
        "implementations/python/tests/test_issue_1210_semantic_revisions.py",
        "contracts/provenance/sdl-lineage-ledger-v2.json",
    ]
    assert not evaluate_requirement_governance(ROOT, paths, client=client, requirement_uid="GOV-903")
    rejected = evaluate_requirement_governance(
        ROOT,
        ["implementations/python/packages/raes_control_plane/unrelated.py"],
        client=client,
        requirement_uid="GOV-903",
    )
    assert "requirement-ownership-mismatch" in {failure.rule_id for failure in rejected}


@pytest.mark.parametrize("uid", ["GOV-917", "GOV-918", "GOV-919", "GOV-920", "GOV-921", "GOV-922", "RUN-311"])
def test_migration_cannot_edit_prerequisite_or_unrelated_requirement_records(uid):
    failures = evaluate_requirement_governance(
        ROOT,
        [f"docs/requirements/{uid}/requirement.md"],
        client=RepositoryRequirementClient(ROOT),
        requirement_uid="GOV-903",
    )
    assert "requirement-ownership-mismatch" in {failure.rule_id for failure in failures}
