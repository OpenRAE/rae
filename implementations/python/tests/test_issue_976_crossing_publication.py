"""Published participant-crossing facts are projections of the two admitted records."""

import json
import re
from pathlib import Path

import pytest
from raes_contracts.behavioral_relations import (
    load_behavioral_relation_catalog,
    load_behavioral_relation_catalog_revision,
    validate_behavioral_claim_binding,
)
from raes_contracts.contracts.base import BehavioralClaimBindingModel
from raes_contracts.errors import EvidenceIntegrityError
from raes_contracts.scientific_completeness import (
    CURRENT_ASSESSMENT_REVISION,
    evaluate_profile_completeness,
    load_scientific_completeness_assessment,
    load_scientific_completeness_taxonomy,
)

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "docs/public/participant-control.md"
RELATION = "divergence-preserving-branching-bisimulation"


def marked_json(name: str) -> dict:
    match = re.search(
        rf"<!-- {name}:start -->\s*```json\s*(.*?)\s*```\s*<!-- {name}:end -->",
        GUIDE.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match is not None, name
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def admitted():
    from implementations.formal.participant_crossing import machine_check, publication
    from implementations.formal.participant_crossing.counterexample_corpus import decoded

    bundle, subject = machine_check.load_retained(ROOT)
    machine_check.admit_bundle(ROOT, bundle, subject)
    return decoded(bundle["result.json"]), publication.publication_facts(ROOT)


def test_public_claim_is_the_admitted_original_claim(admitted):
    from implementations.formal.participant_crossing.export import PROFILE_PATH
    from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel

    result, _ = admitted
    published = marked_json("participant-crossing-claim")
    assert published == result["claim"]
    profile = BehavioralRelationProfileModel.model_validate_json((ROOT / PROFILE_PATH).read_bytes())
    binding = validate_behavioral_claim_binding(
        BehavioralClaimBindingModel.model_validate(published),
        catalog=load_behavioral_relation_catalog_revision(published["taxonomy_revision"]),
        profile=profile,
    )
    assert binding.relation_id == RELATION
    assert binding.assurance_axis == binding.evidence_scope == "model-check"
    assert binding.assurance_status == "model-checked"
    assert {"unbounded-proof", "runtime-realization", "backend-conformance", "noninterference", "opacity"} <= set(
        binding.explicit_non_claims
    )


def test_public_facts_equal_the_admitted_records(admitted):
    _, facts = admitted
    assert marked_json("participant-crossing-evidence") == facts
    assert facts["equivalent"] is True
    assert facts["complete_reachable_fixed_point"] is True
    assert facts["reproduction"]["decision"] == "accepted-bounded-reproduction"
    assert facts["reproduction"]["authenticity"] == facts["machine_check"]["authenticity"] == "unsigned"
    assert set(facts["mutation_cases"].values()) == {False}


def test_facts_come_only_from_admitted_reproduction_records(monkeypatch):
    from implementations.formal.participant_crossing import publication, reproduction_record
    from implementations.formal.participant_crossing.counterexample_corpus import decoded, encoded

    original = reproduction_record.load_record

    def self_approved(root):
        bundle, pin = original(root)
        review = decoded(bundle["review.json"])
        review["reviewer_ref"] = review["producer_ref"]
        return {**bundle, "review.json": encoded(review)}, pin

    monkeypatch.setattr(reproduction_record, "load_record", self_approved)
    with pytest.raises(EvidenceIntegrityError):
        publication.publication_facts(ROOT)


def test_catalog_records_only_the_finite_model_check_axis():
    catalog = load_behavioral_relation_catalog()
    relation = catalog.relations[RELATION]
    assurance = relation.assurance
    assert catalog.taxonomy_revision == "rev14"
    assert assurance.model_check_status == "model-checked"
    assert assurance.proof_status == "deliberately-unproved"
    assert assurance.runtime_enforcement_status == "not-enforced"
    assert assurance.backend_realization_status == "not-realized"
    assert assurance.backend_conformance_status == "not-tested"
    assert all((ROOT / ref).is_file() for ref in assurance.evidence_refs)
    previous = load_behavioral_relation_catalog_revision("rev13").relations[RELATION]
    assert previous.assurance.model_check_status == "not-model-checked"
    surface = next(item for item in catalog.claim_surfaces if item.surface_id == "participant-crossing-bisimulation")
    assert {"policy-noninterference", "participant-predicate-opacity"} <= set(surface.prohibited_relation_ids)


def test_new_assessment_adds_evidence_without_promoting_profiles():
    current = load_scientific_completeness_assessment()
    retained = load_scientific_completeness_assessment("2026-07-12")
    taxonomy = load_scientific_completeness_taxonomy()
    assert current.assessment_revision == CURRENT_ASSESSMENT_REVISION == "2026-10-31"
    assert retained.assessment_revision == "2026-07-12"
    by_id = {item.concern_id: item for item in current.concerns}
    evidence = {item.path for item in by_id["behavioral-relation-taxonomy"].evidence}
    assert "implementations/python/tests/test_issue_976_crossing_publication.py" in evidence
    assert by_id["participant-action-observation"].status.value == "partial"
    assert [result.complete for result in evaluate_profile_completeness(taxonomy, current)] == [
        result.complete for result in evaluate_profile_completeness(taxonomy, retained)
    ]
