"""Description semantics own contracts and evidence, without owning backends."""

from pathlib import Path

import yaml
from tools.policy.requirement_governance import _check_path_ownership, match_phase


def test_description_semantics_ownership_includes_contracts_and_excludes_backends():
    root = Path(__file__).resolve().parents[3]
    policy = yaml.safe_load((root / "tools/policy/requirement_order.yaml").read_text())
    phase = match_phase(policy, "SEM-218")
    paths = [
        "implementations/python/packages/raes_contracts/contracts/realization_descriptions.py",
        "implementations/python/packages/raes_runtime/observation_results.py",
        "contracts/schemas/experiment-core/experiment-evidence-record-v1.json",
        "contracts/schema-publication/entries/experiment-run-v1.json",
        "contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/partial-description.json",
        "docs/requirements/SEM-218/requirement.md",
        "docs/decisions/issue-1209-clause-mapping.md",
        "specs/sdl/recursive-realization-constraints.md",
    ]
    assert _check_path_ownership(policy, phase, paths) == []
    forbidden = [
        "implementations/python/packages/raes_reference_backend/target.py",
        "implementations/python/packages/raes_backend_stubs/stubs.py",
    ]
    failures = _check_path_ownership(policy, phase, forbidden)
    assert {(failure.rule_id, failure.path) for failure in failures} == {
        ("requirement-ownership-mismatch", path) for path in forbidden
    }
