"""The partial-inventory delivery owns exact contract records, not all docs."""

from pathlib import Path

import yaml
from tools.policy.requirement_governance import _check_path_ownership, match_phase


def test_partial_inventory_contract_records_have_bounded_semantics_ownership():
    root = Path(__file__).resolve().parents[3]
    policy = yaml.safe_load((root / "tools/policy/requirement_order.yaml").read_text())
    phase = match_phase(policy, "SEM-218")
    assert (
        _check_path_ownership(
            policy,
            phase,
            [
                "docs/requirements/DSL-132/requirement.md",
                "docs/requirements/DSL-134/requirement.md",
                "docs/requirements/DSL-136/requirement.md",
                "docs/requirements/DSL-137/requirement.md",
                "docs/decisions/adrs/adr-048-datastore-service-runtime-inventory.md",
                "docs/explain/sdl/issue-1207-clause-mapping.md",
                "tools/policy/historical_identity_records.json",
                "specs/sdl/runtime-inventory.md",
                "contracts/schema-publication/entries/sdl-authoring-input-v1.json",
            ],
        )
        == []
    )
    forbidden = [
        "docs/requirements/GOV-941/requirement.md",
        "docs/decisions/adrs/adr-001-unrelated.md",
        "implementations/python/packages/raes_reference_backend/target.py",
    ]
    failures = _check_path_ownership(policy, phase, forbidden)
    assert {row.path for row in failures} == set(forbidden)
