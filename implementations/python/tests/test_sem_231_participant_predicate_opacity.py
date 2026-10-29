"""SEM-231 relation authority and claim-binding tests."""

from __future__ import annotations

from copy import deepcopy

import pytest
from raes_contracts.behavioral_relations import (
    RelationAssuranceModel,
    load_behavioral_relation_catalog,
    load_behavioral_relation_catalog_revision,
    validate_behavioral_claim_binding,
)
from raes_contracts.contracts import BehavioralClaimBindingModel


def _opacity_binding(**overrides: object) -> BehavioralClaimBindingModel:
    payload: dict[str, object] = {
        "taxonomy_id": "raes-behavioral-relations",
        "taxonomy_revision": "rev9",
        "relation_id": "participant-predicate-opacity",
        "subject": "Participant p at the declared exact cut",
        "left_carrier_ref": "possible-point-carrier:participant-opacity-fixture-v1",
        "observation_projection_ref": "participant-opacity-observation:complete-v1",
        "observation_projection_revision": "rev1",
        "relation_parameter_profile_ref": "participant-opacity-baseline-v1",
        "relation_parameter_profile_revision": "sem-231/rev3",
        "quantifier_scope": "finite-cases",
        "evidence_scope": "finite",
        "assurance_axis": "bounded-test",
        "evidence_boundary": "The four named finite worked examples.",
        "assurance_status": "tested",
        "evidence_refs": ["specs/formal/participant-semantics/participant-predicate-opacity.md"],
        "limitations": ["No model check, proof, runtime enforcement, or backend realization."],
        "explicit_non_claims": ["No universal opacity claim."],
    }
    payload.update(overrides)
    return BehavioralClaimBindingModel.model_validate(payload)


def test_catalog_defines_one_sided_participant_predicate_opacity() -> None:
    catalog = load_behavioral_relation_catalog()
    relation = catalog.relations["participant-predicate-opacity"]

    assert catalog.taxonomy_revision == "rev13"
    assert relation.relation_class == "epistemic"
    assert relation.direction == "unary"
    assert relation.relation_parameter_profile_required is True
    assert relation.projection_required is True
    assert relation.dimensions.probability.status == "outside-scope"
    assert relation.dimensions.time.status == "parameterized"
    assert relation.dimensions.partial_order.status == "parameterized"
    assert relation.assurance.definition_status == "defined"
    assert relation.assurance.implementation_status == "implemented"
    assert relation.assurance.checker_status == "implemented"
    assert relation.assurance.test_status == "bounded"
    assert relation.assurance.model_check_status == "model-checked"
    assert relation.assurance.proof_status == "proved"
    assert relation.assurance.runtime_enforcement_status == "partial"
    assert relation.assurance.backend_declaration_status == "not-declared"
    assert relation.assurance.backend_realization_status == "not-realized"
    assert relation.assurance.backend_conformance_status == "not-tested"
    assert {
        "contracts/profiles/behavioral-relation/history/participant-opacity-baseline-v1-sem-231-rev2.json",
        "contracts/profiles/behavioral-relation/participant-opacity-theorem-v1.json",
        "contracts/schemas/formal-analysis/participant-opacity-model-check-input-v1.json",
        "contracts/schemas/formal-analysis/participant-opacity-model-check-evidence-v1.json",
        "implementations/python/packages/raes_processor/participant_opacity/_service.py",
        "implementations/python/packages/raes_processor/participant_opacity/_model_check.py",
        "implementations/python/tests/test_issue_961_participant_opacity.py",
        "implementations/python/tests/test_issue_962_participant_opacity_model_check.py",
        "implementations/python/tests/test_issue_963_participant_opacity_proof.py",
        "specs/formal/participant-semantics/participant-opacity-proof-evidence.json",
    } <= set(relation.assurance.evidence_refs)


def test_opacity_binding_requires_a_revisioned_parameter_profile_and_assurance_axis() -> None:
    catalog = load_behavioral_relation_catalog_revision("rev9")

    missing_profile = _opacity_binding().model_copy(
        update={
            "relation_parameter_profile_ref": None,
            "relation_parameter_profile_revision": None,
        }
    )
    with pytest.raises(ValueError, match="relation parameter profile"):
        validate_behavioral_claim_binding(missing_profile, catalog)

    missing_axis = _opacity_binding().model_copy(update={"assurance_axis": None})
    with pytest.raises(ValueError, match="assurance axis"):
        validate_behavioral_claim_binding(missing_axis, catalog)

    assert validate_behavioral_claim_binding(_opacity_binding(), catalog).relation_id == (
        "participant-predicate-opacity"
    )


def test_profile_coordinates_are_paired_and_existing_relations_remain_compatible() -> None:
    payload = _opacity_binding().model_dump(mode="json")
    payload["relation_parameter_profile_revision"] = None
    with pytest.raises(ValueError, match="profile ref and revision"):
        BehavioralClaimBindingModel.model_validate(payload)

    existing_payload = deepcopy(payload)
    existing_payload.update(
        {
            "relation_id": "bounded-probe-success",
            "relation_parameter_profile_ref": None,
            "relation_parameter_profile_revision": None,
            "assurance_axis": None,
        }
    )
    existing = BehavioralClaimBindingModel.model_validate(existing_payload)
    assert validate_behavioral_claim_binding(existing).relation_id == "bounded-probe-success"


def test_universal_opacity_claim_still_requires_model_check_or_proof_evidence() -> None:
    with pytest.raises(ValueError, match="universal quantification"):
        _opacity_binding(
            quantifier_scope="all-strategies",
            evidence_scope="finite",
            assurance_axis="bounded-test",
            assurance_status="tested",
        )


def test_universal_opacity_claim_accepts_model_check_evidence() -> None:
    binding = _opacity_binding(
        quantifier_scope="all-strategies",
        evidence_scope="model-check",
        assurance_axis="model-check",
        assurance_status="model-checked",
    )

    assert binding.quantifier_scope == "all-strategies"
    assert binding.evidence_scope == "model-check"


def test_deliberately_unproved_proof_binding_requires_structural_evidence() -> None:
    with pytest.raises(ValueError, match="assurance axis"):
        _opacity_binding(
            evidence_scope="finite",
            assurance_axis="proof",
            assurance_status="deliberately-unproved",
        )


@pytest.mark.parametrize(
    ("axis", "status", "evidence_scope"),
    [
        ("definition", "tested", "finite"),
        ("checker", "tested", "finite"),
        ("bounded-test", "tested", "structural"),
        ("model-check", "model-checked", "finite"),
        ("proof", "proved", "model-check"),
        ("runtime-enforcement", "implemented", "finite"),
        ("backend-declaration", "defined", "structural"),
        ("backend-realization", "implemented", "finite"),
        ("backend-conformance", "tested", "finite"),
    ],
)
def test_claim_assurance_axis_rejects_incompatible_status_or_evidence(
    axis: str,
    status: str,
    evidence_scope: str,
) -> None:
    payload = _opacity_binding().model_dump(mode="json")
    payload.update(
        {
            "assurance_axis": axis,
            "assurance_status": status,
            "evidence_scope": evidence_scope,
        }
    )

    with pytest.raises(ValueError, match="assurance axis"):
        BehavioralClaimBindingModel.model_validate(payload)


@pytest.mark.parametrize(
    ("axis", "status", "evidence_scope"),
    [
        ("definition", "defined", "structural"),
        ("checker", "implemented", "structural"),
        ("bounded-test", "tested", "finite"),
        ("model-check", "model-checked", "model-check"),
        ("proof", "proved", "proof"),
        ("runtime-enforcement", "enforced", "finite"),
        ("backend-declaration", "declared", "structural"),
        ("backend-realization", "realized", "finite"),
        ("backend-conformance", "conformant", "finite"),
    ],
)
def test_claim_assurance_axis_accepts_compatible_status_and_evidence(
    axis: str,
    status: str,
    evidence_scope: str,
) -> None:
    payload = _opacity_binding().model_dump(mode="json")
    payload.update(
        {
            "assurance_axis": axis,
            "assurance_status": status,
            "evidence_scope": evidence_scope,
        }
    )

    assert BehavioralClaimBindingModel.model_validate(payload).assurance_axis == axis


def _relation_assurance(**overrides: str) -> RelationAssuranceModel:
    payload = {
        "definition_status": "defined",
        "implementation_status": "not-implemented",
        "test_status": "bounded",
        "proof_status": "deliberately-unproved",
        "checker_status": "not-implemented",
        "model_check_status": "not-model-checked",
        "runtime_enforcement_status": "not-enforced",
        "backend_declaration_status": "not-declared",
        "backend_realization_status": "not-realized",
        "backend_conformance_status": "not-tested",
        "evidence_refs": ["specs/formal/participant-semantics/participant-predicate-opacity.md"],
    }
    payload.update(overrides)
    return RelationAssuranceModel.model_validate(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "proof_status": "model-checked",
            "model_check_status": "not-model-checked",
        },
        {
            "implementation_status": "partial",
        },
        {
            "implementation_status": "not-implemented",
            "checker_status": "implemented",
        },
        {
            "backend_realization_status": "not-realized",
            "backend_conformance_status": "bounded",
        },
        {
            "definition_status": "future",
            "checker_status": "implemented",
            "implementation_status": "partial",
        },
    ],
)
def test_relation_assurance_rejects_cross_axis_contradictions(overrides: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="assurance"):
        _relation_assurance(**overrides)


def test_relation_assurance_keeps_model_check_independent_from_proof() -> None:
    assurance = _relation_assurance(
        proof_status="deliberately-unproved",
        model_check_status="model-checked",
    )

    assert assurance.model_check_status == "model-checked"
    assert assurance.proof_status == "deliberately-unproved"


def test_relation_assurance_accepts_matching_legacy_model_check_aggregate() -> None:
    assurance = _relation_assurance(
        proof_status="model-checked",
        model_check_status="model-checked",
    )

    assert assurance.proof_status == "model-checked"
