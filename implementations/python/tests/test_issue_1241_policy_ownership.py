"""Operational provenance owns bounded delivery surfaces, not arbitrary backends."""

from pathlib import Path

import yaml
from tools.policy.requirement_governance import _check_path_ownership, match_phase


def test_materialization_provenance_delivery_has_bounded_ownership():
    root = Path(__file__).resolve().parents[3]
    policy = yaml.safe_load((root / "tools/policy/requirement_order.yaml").read_text())
    phase = match_phase(policy, "SEM-225")
    assert phase.phase_id == "materialization-provenance"
    allowed = [
        "implementations/python/packages/raes_operations/run_artifacts.py",
        "implementations/python/packages/raes_runtime/backend_materialization.py",
        "implementations/python/packages/raes_runtime/control_plane_configuration.py",
        "contracts/schemas/sdl/materialized-scenario-v1.json",
        "contracts/schema-publication/entries/materialized-scenario-v1.json",
        "docs/research/formal-semantic-validation/bundles/retest-v16.json",
    ]
    assert not _check_path_ownership(policy, phase, allowed)
    forbidden = [
        "implementations/python/packages/raes_backend_libvirt/target.py",
        "implementations/python/packages/raes_reference_backend/target.py",
        "contracts/schemas/concept-authority/unrelated-contract.json",
        "docs/requirements/GOV-941/requirement.md",
        "docs/research/unrelated-study/results.md",
    ]
    assert {failure.path for failure in _check_path_ownership(policy, phase, forbidden)} == set(forbidden)
