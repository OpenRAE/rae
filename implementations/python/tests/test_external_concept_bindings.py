"""Portable external concept-binding contract and resolver tests (issue #986)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.external_concept_subjects import external_concept_subjects
from raes.scenarios import load_scenario
from raes_conformance.conformance import _fixture_case_diagnostics, validate_contract_payload
from raes_conformance.conformance.validators import (
    _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS,
    _STRUCTURAL_ONLY_VALIDATORS,
)
from raes_contracts.contracts import ExternalConceptBindingDocumentModel, schema_bundle
from raes_contracts.contracts.external_concept_bindings import (
    ExternalConceptApproximationPosture,
    ExternalConceptConfidencePosture,
    ExternalConceptParticipantAvailabilityKind,
    ExternalConceptRelationshipKind,
    ExternalConceptReviewStatus,
)
from raes_contracts.controlled_vocabularies import load_controlled_vocabulary_catalog
from raes_contracts.external_concept_bindings import (
    ExternalConceptResolutionOutcome,
    adapt_activitystreams_activity_types_snapshot,
    adapt_attack_enterprise_tactics_snapshot,
    adapt_fipa_communicative_acts_snapshot,
    adapt_nist_csf_defensive_categories_snapshot,
    admit_external_concept_bindings,
)
from raes_contracts.semantic_binding_effects import ExternalKnowledgeBindingEffect
from raes_contracts.vocabulary_sources import (
    load_activitystreams_activity_types_source,
    load_attack_enterprise_tactics_source,
    load_fipa_communicative_acts_source,
    load_nist_csf_defensive_categories_source,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "concept-authority" / "external-concept-bindings-v1"
VALID_ROOT = FIXTURE_ROOT / "valid"
INVALID_ROOT = FIXTURE_ROOT / "invalid"
SUBJECT_PATH = FIXTURE_ROOT / "context" / "subject.sdl.yaml"
AUTONOMOUS_BEHAVIOR_SUBJECT_PATH = FIXTURE_ROOT / "context" / "autonomous-behavior-subject.sdl.yaml"
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "concept-authority" / "external-concept-bindings-v1.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document(path: Path) -> ExternalConceptBindingDocumentModel:
    return ExternalConceptBindingDocumentModel.model_validate(_load_json(path))


def _subjects():
    return (
        *external_concept_subjects(load_scenario(SUBJECT_PATH)),
        *external_concept_subjects(load_scenario(AUTONOMOUS_BEHAVIOR_SUBJECT_PATH)),
    )


def _snapshots():
    return (
        adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source()),
        adapt_nist_csf_defensive_categories_snapshot(load_nist_csf_defensive_categories_source()),
        adapt_activitystreams_activity_types_snapshot(load_activitystreams_activity_types_source()),
        adapt_fipa_communicative_acts_snapshot(load_fipa_communicative_acts_source()),
    )


@pytest.mark.parametrize("path", sorted(VALID_ROOT.glob("*.json")), ids=lambda path: path.stem)
def test_unrelated_scheme_fixtures_share_contract_and_schema(path: Path) -> None:
    payload = _load_json(path)
    document = ExternalConceptBindingDocumentModel.model_validate(payload)
    published_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(published_schema).validate(document.model_dump(mode="json", exclude_none=True))

    assert document.schema_version == "external-concept-bindings/v1"
    assert len(document.bindings) == 1
    assert validate_contract_payload("external-concept-bindings-v1", payload) == ()
    assert {diagnostic.code for diagnostic in _fixture_case_diagnostics("external-concept-bindings-v1", payload)} == {
        "conformance.semantic-context-required"
    }


@pytest.mark.parametrize("path", sorted(VALID_ROOT.glob("*.json")), ids=lambda path: path.stem)
def test_unrelated_scheme_fixtures_use_same_offline_semantic_admission(path: Path) -> None:
    report = admit_external_concept_bindings(
        _document(path),
        subjects=_subjects(),
        scheme_snapshots=_snapshots(),
    )

    assert report.admitted
    assert {result.outcome for result in report.results} == {ExternalConceptResolutionOutcome.RESOLVED_CURRENT}
    assert all(result.active for result in report.results)
    assert all(not result.diagnostics for result in report.results)


@pytest.mark.parametrize(
    "filename",
    [
        "unknown-relationship.json",
        "missing-provenance.json",
        "impermissible-participant-disclosure.json",
    ],
)
def test_structurally_invalid_fixtures_fail_closed(filename: str) -> None:
    payload = _load_json(INVALID_ROOT / filename)
    published_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        ExternalConceptBindingDocumentModel.model_validate(payload)
    assert not Draft202012Validator(published_schema).is_valid(payload)


def test_stale_scheme_fixture_fails_current_semantic_admission() -> None:
    report = admit_external_concept_bindings(
        _document(INVALID_ROOT / "stale-scheme-revision.json"),
        subjects=_subjects(),
        scheme_snapshots=_snapshots(),
    )

    assert not report.admitted
    assert report.results[0].outcome == ExternalConceptResolutionOutcome.STALE
    assert not report.results[0].active


def test_ambiguous_subject_fixture_preserves_collision_and_fails() -> None:
    document = _document(INVALID_ROOT / "ambiguous-subject.json")
    subjects = _subjects()
    matching_subject = next(subject for subject in subjects if subject.canonical_ref == "nodes.web")

    report = admit_external_concept_bindings(
        document,
        subjects=(*subjects, matching_subject),
        scheme_snapshots=_snapshots(),
    )

    assert not report.admitted
    assert report.results[0].outcome == ExternalConceptResolutionOutcome.AMBIGUOUS
    assert "nodes.web" not in report.results[0].diagnostics[0].message


def test_unavailable_scheme_remains_parseable_but_inactive_without_lookup() -> None:
    report = admit_external_concept_bindings(
        _document(VALID_ROOT / "attack-enterprise.json"),
        subjects=_subjects(),
        scheme_snapshots=(),
    )

    assert not report.admitted
    assert report.results[0].outcome == ExternalConceptResolutionOutcome.UNAVAILABLE
    assert not report.results[0].active


def test_unknown_concept_fails_without_echoing_the_identifier() -> None:
    document = _document(VALID_ROOT / "attack-enterprise.json")
    binding = document.bindings["attack-execution"]
    mutated_binding = binding.model_copy(
        update={"scheme": binding.scheme.model_copy(update={"concept_id": "ATTACKER-CONTROLLED-SECRET"})}
    )
    mutated = document.model_copy(update={"bindings": {"attack-execution": mutated_binding}})

    report = admit_external_concept_bindings(
        mutated,
        subjects=_subjects(),
        scheme_snapshots=_snapshots(),
    )

    assert report.results[0].outcome == ExternalConceptResolutionOutcome.UNKNOWN_CONCEPT
    assert "ATTACKER-CONTROLLED-SECRET" not in report.results[0].diagnostics[0].message


def test_superseded_concept_is_not_automatically_rewritten() -> None:
    document = _document(VALID_ROOT / "attack-enterprise.json")
    attack = _snapshots()[0]
    superseded_terms = [
        term.model_copy(update={"status": "superseded", "successor_concept_ids": ["TA9999"]})
        if term.concept_id == "TA0002"
        else term
        for term in attack.concepts
    ]
    superseded = attack.model_copy(update={"concepts": superseded_terms})

    report = admit_external_concept_bindings(
        document,
        subjects=_subjects(),
        scheme_snapshots=(superseded,),
    )

    assert report.results[0].outcome == ExternalConceptResolutionOutcome.SUPERSEDED
    assert not report.results[0].active
    assert report.results[0].resolved_concept_id == "TA0002"


def test_adapter_preserves_duplicate_concept_candidates_and_admission_rejects_ambiguity() -> None:
    source = load_attack_enterprise_tactics_source()
    execution = next(term for term in source.tactics if term.tactic_id == "TA0002")
    duplicate_source = source.model_copy(update={"tactics": [*source.tactics, execution]})
    duplicate_snapshot = adapt_attack_enterprise_tactics_snapshot(duplicate_source)

    assert sum(term.concept_id == "TA0002" for term in duplicate_snapshot.concepts) == 2

    report = admit_external_concept_bindings(
        _document(VALID_ROOT / "attack-enterprise.json"),
        subjects=_subjects(),
        scheme_snapshots=(duplicate_snapshot,),
    )

    assert not report.admitted
    assert report.results[0].outcome == ExternalConceptResolutionOutcome.AMBIGUOUS
    assert "TA0002" not in report.results[0].diagnostics[0].message


@pytest.mark.parametrize(
    "source_locator",
    [
        "relative/path.json",
        "file:///tmp/scheme.json",
        "data:application/json,%7B%7D",
        "https://user:password@example.test/scheme.json",
        "https://example.test/scheme.json?access_token=secret",
        "https://example.test/scheme.json#concept",
    ],
)
def test_scheme_locators_are_inert_and_secret_safe(source_locator: str) -> None:
    payload = _load_json(VALID_ROOT / "attack-enterprise.json")
    payload["bindings"]["attack-execution"]["scheme"]["source_locator"] = source_locator
    published_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        ExternalConceptBindingDocumentModel.model_validate(payload)
    assert not Draft202012Validator(published_schema).is_valid(payload)


def _schema_invariant_payload(case: str) -> dict[str, object]:
    payload = _load_json(VALID_ROOT / "attack-enterprise.json")
    binding = payload["bindings"]["attack-execution"]
    if case == "unsafe-locator":
        binding["scheme"]["source_locator"] = "https://example.test/scheme.json?access_token=secret"
    elif case == "unpinned-source":
        del binding["scheme"]["source_locator"]
        del binding["scheme"]["source_digest"]
    elif case == "duplicate-participants":
        binding["perspective"]["participant_availability"] = {
            "kind": "eligibility-only",
            "participant_refs": ["participants.blue", "participants.blue"],
            "basis_refs": [{"ref_kind": "other", "ref_id": "eligibility-policy", "ref_version": "v1"}],
        }
    elif case == "unpaired-confidence":
        binding["confidence"]["score"] = 0.8
    elif case == "calibration-without-score":
        binding["confidence"]["calibration_profile_ref"] = {
            "ref_kind": "profile",
            "ref_id": "confidence-calibration",
            "ref_version": "v1",
        }
    elif case == "missing-loss":
        binding["approximation"] = {"posture": "approximate", "loss_details": []}
    elif case == "exact-with-loss":
        binding["approximation"] = {"posture": "exact", "loss_details": ["contradictory loss"]}
    elif case == "unsubstantiated-review":
        binding["review"] = {"status": "accepted", "review_refs": []}
    elif case == "unreviewed-with-reference":
        binding["review"] = {
            "status": "unreviewed",
            "review_refs": [{"ref_kind": "other", "ref_id": "premature-review", "ref_version": "v1"}],
        }
    else:
        raise AssertionError(f"unknown invariant case: {case}")
    return payload


@pytest.mark.parametrize(
    "case",
    [
        "unsafe-locator",
        "unpinned-source",
        "duplicate-participants",
        "unpaired-confidence",
        "calibration-without-score",
        "missing-loss",
        "exact-with-loss",
        "unsubstantiated-review",
        "unreviewed-with-reference",
    ],
)
def test_normative_schema_enforces_local_runtime_invariants(case: str) -> None:
    payload = _schema_invariant_payload(case)
    published_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        ExternalConceptBindingDocumentModel.model_validate(payload)
    assert not Draft202012Validator(published_schema).is_valid(payload)


def test_normative_schema_publishes_cross_entry_binding_identity_invariant() -> None:
    published_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    invariants = {entry["id"]: entry for entry in published_schema["x-raes-invariants"]}

    assert "external-concept-binding-identities" in invariants


def test_binding_map_key_must_equal_stable_binding_id() -> None:
    payload = _load_json(VALID_ROOT / "attack-enterprise.json")
    payload["bindings"]["other-id"] = payload["bindings"].pop("attack-execution")

    with pytest.raises(ValidationError, match="binding id"):
        ExternalConceptBindingDocumentModel.model_validate(payload)


def test_binding_set_rejects_duplicate_semantic_assertions() -> None:
    payload = _load_json(VALID_ROOT / "attack-enterprise.json")
    duplicate = json.loads(json.dumps(payload["bindings"]["attack-execution"]))
    duplicate["binding_id"] = "duplicate-attack-execution"
    payload["bindings"]["duplicate-attack-execution"] = duplicate

    with pytest.raises(ValidationError, match="duplicate semantic assertions"):
        ExternalConceptBindingDocumentModel.model_validate(payload)


def test_sdl_subject_adapter_uses_canonical_declaration_identity_and_digest() -> None:
    subjects = _subjects()
    web = next(subject for subject in subjects if subject.canonical_ref == "nodes.web")

    assert web.subject_kind == "node"
    assert web.owning_contract_id == "sdl-authoring-input-v1"
    assert web.lifecycle_phase == "normalized-authoring"
    assert web.artifact_digest.startswith("sha256:")
    assert not any(subject.canonical_ref == "web" for subject in subjects)


@pytest.mark.parametrize(
    ("filename", "canonical_ref"),
    [
        ("activitystreams-behavior.json", "behavior_specifications.service-publication"),
        ("fipa-behavior.json", "behavior_specifications.agent-request"),
    ],
)
def test_autonomous_scheme_fixtures_target_exact_behavior_specifications(
    filename: str,
    canonical_ref: str,
) -> None:
    document = _document(VALID_ROOT / filename)
    binding = next(iter(document.bindings.values()))
    subject = binding.subject
    available_subjects = _subjects()

    assert subject.subject_kind == "behavior_specifications"
    assert subject.owning_contract_id == "sdl-authoring-input-v1"
    assert subject.lifecycle_phase == "normalized-authoring"
    assert subject.canonical_ref == canonical_ref
    assert subject.artifact_digest.startswith("sha256:")
    assert sum(candidate == subject for candidate in available_subjects) == 1

    report = admit_external_concept_bindings(
        document,
        subjects=available_subjects,
        scheme_snapshots=_snapshots(),
    )
    assert report.admitted
    assert report.results[0].outcome == ExternalConceptResolutionOutcome.RESOLVED_CURRENT


@pytest.mark.parametrize(
    ("vocabulary_id", "enum_type"),
    [
        ("external-concept-relationship-kinds", ExternalConceptRelationshipKind),
        ("external-knowledge-binding-effects", ExternalKnowledgeBindingEffect),
        ("external-concept-confidence-postures", ExternalConceptConfidencePosture),
        ("external-concept-approximation-postures", ExternalConceptApproximationPosture),
        ("external-concept-review-statuses", ExternalConceptReviewStatus),
        ("external-concept-participant-availability-kinds", ExternalConceptParticipantAvailabilityKind),
    ],
)
def test_python_vocabulary_is_parity_checked_against_authority(vocabulary_id: str, enum_type: type) -> None:
    definition = load_controlled_vocabulary_catalog().vocabularies[vocabulary_id]

    assert {member.value for member in enum_type} == set(definition.terms)


def test_schema_bundle_publishes_external_concept_bindings_contract() -> None:
    assert schema_bundle()["external-concept-bindings-v1"] == json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_contract_is_registered_with_canonical_conformance_boundaries() -> None:
    payload = _load_json(VALID_ROOT / "attack-enterprise.json")

    assert "external-concept-bindings-v1" in _STRUCTURAL_ONLY_VALIDATORS
    assert "external-concept-bindings-v1" in _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS
    assert validate_contract_payload("external-concept-bindings-v1", payload) == ()
    assert {diagnostic.code for diagnostic in _fixture_case_diagnostics("external-concept-bindings-v1", payload)} == {
        "conformance.semantic-context-required"
    }
    assert "exact RAES subjects" in _fixture_case_diagnostics("external-concept-bindings-v1", payload)[0].message
