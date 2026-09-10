"""Revision-pinned SDL lineage and provenance contract tests."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.check_sdl_lineage as lineage_checker  # noqa: E402
from raes_contracts.provenance import SDLLineageLedgerModel  # noqa: E402
from tools.check_sdl_lineage import (  # noqa: E402
    _canonical_subjects,
    _validate_authorities,
    _validate_bibliography,
    _validate_current_prose,
    _validate_internal_paths,
    evaluate,
)

LEDGER_PATH = REPO_ROOT / "contracts/provenance/sdl-lineage-ledger-v1.json"


def _payload() -> dict[str, object]:
    payload = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    projected = lineage_checker.project_historical_ledger_to_current_contract(payload)
    assert isinstance(projected, dict)
    return projected


def test_real_lineage_ledger_is_valid_and_covers_exact_current_subject_set() -> None:
    ledger = SDLLineageLedgerModel.model_validate(_payload())
    current = {subject.subject_id for subject in ledger.subjects if subject.disposition.value == "current"}
    assert current == _canonical_subjects(REPO_ROOT)
    assert len(current) == 89
    assert {subject.subject_id for subject in ledger.subjects if subject.disposition.value == "removed"} == {
        "sdl-field:evaluations",
        "sdl-field:goals",
        "sdl-field:metrics",
        "sdl-field:tlos",
        "sdl-field:vulnerabilities",
    }


def test_real_lineage_policy_gate_is_clean() -> None:
    assert evaluate(REPO_ROOT) == []


def test_git_source_requires_full_revision_pin() -> None:
    payload = _payload()
    payload["sources"][0]["commit"] = "fe83e828"
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        SDLLineageLedgerModel.model_validate(payload)


def test_artifact_code_claim_requires_notice_disposition() -> None:
    payload = _payload()
    payload["third_party_dispositions"] = []
    with pytest.raises(ValidationError, match="lacks notice disposition"):
        SDLLineageLedgerModel.model_validate(payload)


def test_artifact_code_claim_rejects_unresolved_notice_disposition() -> None:
    payload = _payload()
    payload["third_party_dispositions"][0]["notice_decision"] = "unknown"
    del payload["third_party_dispositions"][0]["notice_artifact"]
    with pytest.raises(ValidationError, match="unresolved notice disposition"):
        SDLLineageLedgerModel.model_validate(payload)


def test_artifact_code_claim_must_be_covered_by_audited_derivation_scope() -> None:
    payload = _payload()
    claim = next(
        claim for subject in payload["subjects"] for claim in subject["claims"] if claim["plane"] == "artifact_code"
    )
    claim["raes_boundaries"] = [
        {
            "artifact": "implementations/python/packages/raes/accounts.py",
            "symbol_or_pointer": "Account",
        }
    ]
    with pytest.raises(ValidationError, match="outside the audited derivation scope"):
        SDLLineageLedgerModel.model_validate(payload)


def test_third_party_disposition_is_unique_per_source() -> None:
    payload = _payload()
    payload["third_party_dispositions"].append(deepcopy(payload["third_party_dispositions"][0]))
    with pytest.raises(ValidationError, match="third-party disposition source ids must be unique"):
        SDLLineageLedgerModel.model_validate(payload)


def test_git_source_urls_are_pinned_to_the_declared_commit() -> None:
    payload = _payload()
    payload["sources"][0]["canonical_url"] = "https://github.com/Open-Cyber-Range/SDL-parser"
    with pytest.raises(ValidationError, match="declared commit"):
        SDLLineageLedgerModel.model_validate(payload)


def test_git_license_url_is_pinned_to_the_declared_commit() -> None:
    payload = _payload()
    payload["sources"][0]["license_url"] = "https://github.com/Open-Cyber-Range/SDL-parser/LICENSE"
    with pytest.raises(ValidationError, match="license_url must contain the declared commit"):
        SDLLineageLedgerModel.model_validate(payload)


def test_required_notice_disposition_requires_notice_artifact() -> None:
    payload = _payload()
    del payload["third_party_dispositions"][0]["notice_artifact"]
    with pytest.raises(ValidationError, match="required notice disposition must name notice_artifact"):
        SDLLineageLedgerModel.model_validate(payload)


@pytest.mark.parametrize("decision", ["not_required", "unknown"])
def test_non_required_notice_disposition_rejects_notice_artifact(decision: str) -> None:
    payload = _payload()
    payload["third_party_dispositions"][0]["notice_decision"] = decision
    with pytest.raises(ValidationError, match="notice_artifact is valid only when a required notice is included"):
        SDLLineageLedgerModel.model_validate(payload)


def test_native_claim_cannot_smuggle_external_source_or_compatibility() -> None:
    payload = _payload()
    native_subject = next(
        subject for subject in payload["subjects"] if subject["claims"][0]["classification"] == "raes_native"
    )
    native_subject["claims"][0]["source_refs"] = [payload["sources"][0]["source_id"]]
    native_subject["claims"][0]["compatibility"] = "compatible"
    with pytest.raises(ValidationError, match="RAES-native claims"):
        SDLLineageLedgerModel.model_validate(payload)


def test_native_claim_requires_internal_authority_refs() -> None:
    payload = _payload()
    native_claim = next(
        claim
        for subject in payload["subjects"]
        for claim in subject["claims"]
        if claim["classification"] == "raes_native"
    )
    native_claim["internal_authority_refs"] = []
    with pytest.raises(ValidationError, match="RAES-native claims require internal authority refs"):
        SDLLineageLedgerModel.model_validate(payload)


def test_native_claim_rejects_source_compatibility_relation() -> None:
    payload = _payload()
    native_claim = next(
        claim
        for subject in payload["subjects"]
        for claim in subject["claims"]
        if claim["classification"] == "raes_native"
    )
    native_claim["compatibility"] = "partial"
    with pytest.raises(ValidationError, match="no source compatibility relation"):
        SDLLineageLedgerModel.model_validate(payload)


def test_native_claim_rejects_source_compatibility_direction() -> None:
    payload = _payload()
    native_claim = next(
        claim
        for subject in payload["subjects"]
        for claim in subject["claims"]
        if claim["classification"] == "raes_native"
    )
    native_claim["compatibility_direction"] = "raes_relative_to_source"
    with pytest.raises(ValidationError, match="no source compatibility direction"):
        SDLLineageLedgerModel.model_validate(payload)


def test_non_native_claim_requires_source_boundary_and_citation_refs() -> None:
    payload = _payload()
    claim = next(claim for subject in payload["subjects"] for claim in subject["claims"] if claim["source_refs"])
    claim["source_boundaries"] = []
    with pytest.raises(ValidationError, match="non-native claims require source, source boundary, and citation refs"):
        SDLLineageLedgerModel.model_validate(payload)


@pytest.mark.parametrize(
    ("classification", "plane", "message"),
    [
        ("adopted_syntax", "semantics", "adopted_syntax is valid only on the syntax plane"),
        ("adopted_semantics", "syntax", "adopted_semantics is valid only on the semantics plane"),
    ],
)
def test_adopted_classification_requires_matching_claim_plane(
    classification: str,
    plane: str,
    message: str,
) -> None:
    payload = _payload()
    claim = next(claim for subject in payload["subjects"] for claim in subject["claims"] if claim["source_refs"])
    claim["classification"] = classification
    claim["plane"] = plane
    with pytest.raises(ValidationError, match=message):
        SDLLineageLedgerModel.model_validate(payload)


def test_non_native_claim_requires_explicit_compatibility_direction() -> None:
    payload = _payload()
    claim = next(
        claim
        for subject in payload["subjects"]
        for claim in subject["claims"]
        if claim["classification"] != "raes_native"
    )
    claim["compatibility_direction"] = "not_applicable"
    with pytest.raises(ValidationError, match="assess RAES relative"):
        SDLLineageLedgerModel.model_validate(payload)


def test_subject_namespace_must_match_declared_kind() -> None:
    payload = _payload()
    payload["subjects"][0]["subject_kind"] = "runtime_family"
    with pytest.raises(ValidationError, match="namespace .* does not match subject_kind"):
        SDLLineageLedgerModel.model_validate(payload)


def test_claim_citations_must_identify_the_claimed_sources() -> None:
    payload = _payload()
    claim = next(claim for subject in payload["subjects"] for claim in subject["claims"] if claim["source_refs"])
    claim["citation_refs"] = ["crack-cose-2020"]
    with pytest.raises(ValidationError, match="citation refs do not identify its sources"):
        SDLLineageLedgerModel.model_validate(payload)


def test_native_internal_authority_refs_must_resolve() -> None:
    payload = _payload()
    native_claim = next(
        claim
        for subject in payload["subjects"]
        for claim in subject["claims"]
        if claim["classification"] == "raes_native"
    )
    native_claim["internal_authority_refs"] = ["specs/sdl/does-not-exist.md"]
    ledger = SDLLineageLedgerModel.model_validate(payload)
    failures = _validate_internal_paths(REPO_ROOT, ledger)
    assert any(
        failure.rule_id == "lineage-internal-artifact-missing" and "specs/sdl/does-not-exist.md" in failure.message
        for failure in failures
    )


def test_authority_contract_id_must_match_published_schema_path() -> None:
    payload = _payload()
    subject = next(item for item in payload["subjects"] if item["authority"].get("contract_id"))
    subject["authority"]["contract_id"] = "semantic-profile-v1"
    ledger = SDLLineageLedgerModel.model_validate(payload)
    failures = _validate_authorities(REPO_ROOT, ledger)
    assert any(failure.rule_id == "lineage-authority-contract-mismatch" for failure in failures)


def test_planned_subject_cannot_claim_current_compatibility() -> None:
    payload = _payload()
    subject = deepcopy(payload["subjects"][0])
    subject["subject_id"] = "sdl-field:future"
    subject["disposition"] = "planned"
    subject["claims"][0]["compatibility"] = "compatible"
    payload["subjects"].append(subject)
    with pytest.raises(ValidationError, match="planned subject"):
        SDLLineageLedgerModel.model_validate(payload)


def test_crack_publications_have_distinct_verified_identities() -> None:
    citations = {item["citation_id"]: item for item in _payload()["citations"]}
    assert citations["crack-nca-2018"]["doi"] == "10.1109/NCA.2018.8548324"
    assert citations["crack-nca-2018"]["title"] == "Scenario Design and Validation for Next Generation Cyber Ranges"
    assert citations["crack-cose-2020"]["doi"] == "10.1016/j.cose.2020.101837"
    assert citations["crack-cose-2020"]["title"] == "Building next generation Cyber Ranges with CRACK"


def test_bibliography_rejects_conflicting_identity_for_one_doi() -> None:
    payload = _payload()
    citations = {item["citation_id"]: item for item in payload["citations"]}
    citations["crack-cose-2020"]["doi"] = citations["crack-nca-2018"]["doi"]
    citations["crack-cose-2020"]["canonical_url"] = citations["crack-nca-2018"]["canonical_url"]
    ledger = SDLLineageLedgerModel.model_validate(payload)
    failures = _validate_bibliography(ledger)
    assert [failure.rule_id for failure in failures] == ["lineage-doi-identity-conflict"]


def test_bibliography_rejects_doi_url_mismatch() -> None:
    payload = _payload()
    citation = next(item for item in payload["citations"] if item.get("doi"))
    citation["canonical_url"] = "https://example.org/wrong-publication"
    ledger = SDLLineageLedgerModel.model_validate(payload)
    failures = _validate_bibliography(ledger)
    assert [failure.rule_id for failure in failures] == ["lineage-doi-url-mismatch"]


@pytest.mark.parametrize(
    ("mutation", "expected_rule"),
    [
        ("missing", "lineage-current-subjects-missing"),
        ("unexpected", "lineage-current-subjects-unexpected"),
    ],
)
def test_evaluate_rejects_bidirectional_current_subject_drift(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_rule: str,
) -> None:
    payload = _payload()
    if mutation == "missing":
        payload["subjects"][0]["disposition"] = "removed"
    else:
        subject = deepcopy(payload["subjects"][0])
        subject["subject_id"] = "sdl-field:future"
        payload["subjects"].append(subject)

    original_load_json = lineage_checker._load_json

    def load_json(repo_root: Path, rel_path: str) -> object:
        if rel_path == lineage_checker.LEDGER_PATH:
            return payload
        return original_load_json(repo_root, rel_path)

    monkeypatch.setattr(lineage_checker, "_load_json", load_json)
    failures = lineage_checker.evaluate(REPO_ROOT)
    assert expected_rule in {failure.rule_id for failure in failures}


def test_prose_doi_label_year_must_match_verified_identity(tmp_path: Path) -> None:
    prose_path = tmp_path / "lineage.md"
    prose_path.write_text(
        "[Russo et al. 2018](https://doi.org/10.1016/j.cose.2020.101837)\n",
        encoding="utf-8",
    )
    ledger = SDLLineageLedgerModel.model_validate(_payload())
    failures = _validate_current_prose(tmp_path, ledger, ("lineage.md",))
    assert [failure.rule_id for failure in failures] == ["lineage-doi-label-year-mismatch"]
