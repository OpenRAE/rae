"""Reusable-asset trust/authenticity/integrity policy contract tests (GOV-913).

These tests validate the ``reusable-asset-trust-policy-v1`` contract: its shape,
its complete coverage of the canonical reusable asset families, the per-family
invariants (required integrity, unique evidence classes, threshold-backed
authenticity), and its registration in the published schema bundle + publication
manifest. The contract declares policy over the *existing* RAES trust mechanisms;
it carries no evidence payload and no key material (see ADR-071 and
``specs/authority/reusable-asset-trust-integrity.md``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import REUSABLE_ASSET_FAMILIES, ReusableAssetTrustPolicyModel
from raes_contracts.versions import REUSABLE_ASSET_TRUST_POLICY_SCHEMA_VERSION
from raes_schemas import schema_bundle
from tools.check_schema_publication import load_schema_publication_catalog

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ID = "reusable-asset-trust-policy-v1"
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "asset-trust" / f"{CONTRACT_ID}.json"
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures" / "asset-trust" / CONTRACT_ID
VALID_DIR = FIXTURES_ROOT / "valid"
INVALID_DIR = FIXTURES_ROOT / "invalid"

_INTEGRITY_CLASSES = {"integrity_digest", "artifact_checksum"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_version_constant():
    assert REUSABLE_ASSET_TRUST_POLICY_SCHEMA_VERSION == "reusable-asset-trust-policy/v1"


def test_reference_policy_validates_and_covers_every_family():
    policy = ReusableAssetTrustPolicyModel.model_validate(_load(VALID_DIR / "reference.json"))
    declared = {family.asset_family for family in policy.families}
    assert declared == set(REUSABLE_ASSET_FAMILIES)


def test_every_family_declares_a_required_integrity_class():
    """GOV-913 baseline: integrity evidence is required for every reusable asset family."""
    policy = ReusableAssetTrustPolicyModel.model_validate(_load(VALID_DIR / "reference.json"))
    for family in policy.families:
        required_integrity = [
            requirement
            for requirement in family.evidence_requirements
            if requirement.evidence_class in _INTEGRITY_CLASSES and requirement.enforcement == "required"
        ]
        assert required_integrity, f"family {family.asset_family} must require an integrity evidence class"


def test_enforced_authenticity_requires_threshold_policy():
    policy = ReusableAssetTrustPolicyModel.model_validate(_load(VALID_DIR / "reference.json"))
    for family in policy.families:
        enforced = any(
            requirement.evidence_class == "authenticity_signature"
            and requirement.enforcement in {"required", "recommended"}
            for requirement in family.evidence_requirements
        )
        if enforced:
            assert family.authenticity_policy is not None
            assert family.authenticity_policy.threshold >= 1


def test_contract_registered_in_schema_bundle_and_matches_published_schema():
    bundle = schema_bundle()
    assert CONTRACT_ID in bundle
    assert bundle[CONTRACT_ID] == _load(SCHEMA_PATH)


def test_published_schema_enforces_security_invariants():
    """The published schema is the portable contract external consumers validate
    against; it MUST reject the same invariant violations the model rejects, not
    just the Python reference implementation (issue #115 review)."""
    import jsonschema

    schema = _load(SCHEMA_PATH)
    jsonschema.validate(_load(VALID_DIR / "reference.json"), schema)
    for path in sorted(INVALID_DIR.glob("*.json")):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_load(path), schema)


def test_manifest_entry_registered_with_consistent_ledger():
    """Exact canonical-hash parity is enforced by tools/check_schema_publication.py;
    here we assert the entry exists, points at the published schema, and its
    last_change ledger hash is self-consistent with the entry content_hash."""
    manifest = load_schema_publication_catalog(REPO_ROOT)
    entry = next(item for item in manifest["schemas"] if item["contract_id"] == CONTRACT_ID)
    assert entry["schema_path"] == "contracts/schemas/asset-trust/reusable-asset-trust-policy-v1.json"
    assert len(entry["content_hash"]) == 64
    assert entry["last_change"]["content_hash"] == entry["content_hash"]


def test_valid_fixtures_pass_validation():
    paths = sorted(VALID_DIR.glob("*.json"))
    assert paths, "expected valid fixtures to exist"
    for path in paths:
        model = ReusableAssetTrustPolicyModel.model_validate(_load(path))
        assert model.families, f"valid fixture {path.name} should declare families"


def test_invalid_fixtures_fail_validation():
    paths = sorted(INVALID_DIR.glob("*.json"))
    assert paths, "expected invalid fixtures to exist"
    for path in paths:
        with pytest.raises(ValidationError):
            ReusableAssetTrustPolicyModel.model_validate(_load(path))


def test_missing_family_fixture_reports_coverage_gap():
    with pytest.raises(ValidationError, match="cover|missing"):
        ReusableAssetTrustPolicyModel.model_validate(_load(INVALID_DIR / "missing-family.json"))


def test_duplicate_evidence_class_fixture_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        ReusableAssetTrustPolicyModel.model_validate(_load(INVALID_DIR / "duplicate-evidence-class.json"))


def test_missing_integrity_fixture_rejected():
    with pytest.raises(ValidationError, match="integrity"):
        ReusableAssetTrustPolicyModel.model_validate(_load(INVALID_DIR / "missing-integrity.json"))


def test_authenticity_without_threshold_fixture_rejected():
    with pytest.raises(ValidationError, match="authenticity_policy|threshold"):
        ReusableAssetTrustPolicyModel.model_validate(_load(INVALID_DIR / "authenticity-without-threshold.json"))


def test_secret_bearing_fixture_rejected():
    """A closed contract rejects unknown (secret-smuggling) fields."""
    with pytest.raises(ValidationError):
        ReusableAssetTrustPolicyModel.model_validate(_load(INVALID_DIR / "secret-bearing.json"))


def test_behavior_vocabulary_requires_governance_source():
    with pytest.raises(ValidationError, match="governance_source"):
        ReusableAssetTrustPolicyModel.model_validate(_load(INVALID_DIR / "vocabulary-missing-governance-source.json"))
    reference = ReusableAssetTrustPolicyModel.model_validate(_load(VALID_DIR / "reference.json"))
    vocab = next(f for f in reference.families if f.asset_family == "behavior_vocabulary")
    assert any(
        r.evidence_class == "governance_source" and r.enforcement == "required" for r in vocab.evidence_requirements
    )
