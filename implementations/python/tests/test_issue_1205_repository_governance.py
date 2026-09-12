"""Software semantics own generic contracts, never backend implementation."""

from pathlib import Path

import pytest
from tools.policy.requirement_governance import _check_path_ownership, load_policy, match_phase

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "path",
    [
        "contracts/schemas/plans/provisioning-plan-v1.json",
        "contracts/schema-publication/entries/provisioning-plan-v1.json",
        "implementations/python/packages/raes_contracts/software_versions.py",
        "specs/sdl/software-requirements.md",
        "docs/decisions/adrs/adr-034-runtime-software-component-inventory.md",
        "docs/research/specification-coverage/execution-snapshot-v8.json",
        "docs/research/formal-semantic-validation/execution-snapshot-v9.json",
        "implementations/python/uv.lock",
        "implementations/tooling/python/smoke/linux-arm64-cp314.txt",
    ],
)
def test_software_semantics_can_update_its_contract_and_evidence_owners(path):
    policy = load_policy(ROOT)
    phase = match_phase(policy, "SEM-218")
    assert phase.phase_id == "software-requirement-semantics"
    assert phase.phase["blocked_until"] == ["reference-implementations"]
    assert _check_path_ownership(policy, phase, [path]) == []


@pytest.mark.parametrize(
    "path",
    [
        "implementations/python/packages/raes_backend_stubs/native_installer.py",
        "implementations/downstream/scenario.yaml",
        "contracts/schemas/control-plane/control-plane-v1.json",
    ],
)
def test_software_semantics_does_not_authorize_backend_or_unrelated_contract_changes(path):
    policy = load_policy(ROOT)
    failures = _check_path_ownership(policy, match_phase(policy, "SEM-218"), [path])
    assert [failure.rule_id for failure in failures] == ["requirement-ownership-mismatch"]


def test_software_ownership_does_not_expand_other_semantics_requirements():
    policy = load_policy(ROOT)
    phase = match_phase(policy, "SEM-219")
    assert phase.phase_id == "semantics-expansion"
    assert _check_path_ownership(policy, phase, ["implementations/python/uv.lock"])


def test_software_architecture_change_is_recorded_in_the_accepted_adr():
    from tools.check_adr_immutability import content_hash
    from tools.policy.common import load_yaml

    manifest = load_yaml(ROOT / "docs/decisions/adrs/adr-index.yaml")
    entry = next(item for item in manifest["adrs"] if item["id"] == "ADR-034")
    text = (ROOT / entry["path"]).read_text(encoding="utf-8")
    assert "## Software requirement refinements (issue #1205)" in text
    assert "| 2026-09-12 | #1205 |" in text
    assert any(item["ref"] == "#1205" for item in entry["amendments"])
    assert entry["pin"] == content_hash(text)
