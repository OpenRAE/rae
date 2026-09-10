"""Controlled vocabulary catalog tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import (
    AtlasTacticsSourceModel,
    AttackEnterpriseTacticsSourceModel,
    ControlledVocabularyCatalogModel,
    NistCsfDefensiveCategorySourceModel,
    schema_bundle,
)
from raes_contracts.controlled_vocabularies import (
    controlled_vocabulary_catalog_path,
    load_controlled_vocabulary_catalog,
    validate_controlled_vocabulary_scope_values,
    validate_controlled_vocabulary_value,
)
from raes_contracts.vocabulary import (
    ConceptProvenanceCategory,
    ParticipantFeatureSupportLevel,
    ProcessorFeature,
    RealizationSupportMode,
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "contracts" / "concept-authority" / "controlled-vocabularies-v1.json"
ATTACK_TACTICS_SOURCE_PATH = REPO_ROOT / "contracts" / "concept-authority" / "attack-enterprise-tactics-source-v1.json"
ATLAS_TACTICS_SOURCE_PATH = REPO_ROOT / "contracts" / "concept-authority" / "atlas-tactics-source-v1.json"
NIST_CSF_DEFENSIVE_SOURCE_PATH = (
    REPO_ROOT / "contracts" / "concept-authority" / "nist-csf-defensive-categories-source-v1.json"
)
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures" / "concept-authority" / "controlled-vocabularies-v1"
VALID_DIR = FIXTURES_ROOT / "valid"
INVALID_DIR = FIXTURES_ROOT / "invalid"
ATTACK_ENTERPRISE_TACTIC_TERMS_V19_1 = [
    ("reconnaissance", "TA0043", "Reconnaissance"),
    ("resource-development", "TA0042", "Resource Development"),
    ("initial-access", "TA0001", "Initial Access"),
    ("execution", "TA0002", "Execution"),
    ("persistence", "TA0003", "Persistence"),
    ("privilege-escalation", "TA0004", "Privilege Escalation"),
    ("stealth", "TA0005", "Stealth"),
    ("defense-impairment", "TA0112", "Defense Impairment"),
    ("credential-access", "TA0006", "Credential Access"),
    ("discovery", "TA0007", "Discovery"),
    ("lateral-movement", "TA0008", "Lateral Movement"),
    ("collection", "TA0009", "Collection"),
    ("command-and-control", "TA0011", "Command and Control"),
    ("exfiltration", "TA0010", "Exfiltration"),
    ("impact", "TA0040", "Impact"),
]
ATLAS_TACTIC_TERMS_2026_06 = [
    ("reconnaissance", "AML.TA0002", "Reconnaissance"),
    ("resource-development", "AML.TA0003", "Resource Development"),
    ("initial-access", "AML.TA0004", "Initial Access"),
    ("ai-model-access", "AML.TA0000", "AI Model Access"),
    ("execution", "AML.TA0005", "Execution"),
    ("persistence", "AML.TA0006", "Persistence"),
    ("privilege-escalation", "AML.TA0012", "Privilege Escalation"),
    ("defense-evasion", "AML.TA0007", "Defense Evasion"),
    ("credential-access", "AML.TA0013", "Credential Access"),
    ("discovery", "AML.TA0008", "Discovery"),
    ("lateral-movement", "AML.TA0015", "Lateral Movement"),
    ("collection", "AML.TA0009", "Collection"),
    ("ai-attack-staging", "AML.TA0001", "AI Attack Staging"),
    ("command-and-control", "AML.TA0014", "Command and Control"),
    ("exfiltration", "AML.TA0010", "Exfiltration"),
    ("impact", "AML.TA0011", "Impact"),
]
NIST_CSF_DEFENSIVE_CATEGORY_TERMS_2_0 = [
    ("continuous-monitoring", "DE.CM", "Continuous Monitoring", "Detect"),
    ("adverse-event-analysis", "DE.AE", "Adverse Event Analysis", "Detect"),
    ("incident-management", "RS.MA", "Incident Management", "Respond"),
    ("incident-analysis", "RS.AN", "Incident Analysis", "Respond"),
    (
        "incident-response-reporting-and-communication",
        "RS.CO",
        "Incident Response Reporting and Communication",
        "Respond",
    ),
    ("incident-mitigation", "RS.MI", "Incident Mitigation", "Respond"),
    ("incident-recovery-plan-execution", "RC.RP", "Incident Recovery Plan Execution", "Recover"),
    ("incident-recovery-communication", "RC.CO", "Incident Recovery Communication", "Recover"),
]


def test_load_controlled_vocabulary_catalog():
    catalog = load_controlled_vocabulary_catalog()

    assert catalog.schema_version == "controlled-vocabularies/v1"
    assert set(catalog.vocabularies) >= {
        "processor-features",
        "participant-implementation-kinds",
        "participant-decision-surface-modes",
        "participant-defensive-behavior-activities",
        "participant-offensive-behavior-activities",
        "participant-ai-offensive-behavior-activities",
        "participant-tool-affordance-expectations",
        "participant-exposure-policy-kinds",
        "workflow-features",
        "workflow-state-predicate-features",
        "provisioner-node-types",
        "provisioner-os-families",
        "provisioner-node-architectures",
        "provisioner-content-types",
        "provisioner-account-features",
        "orchestrator-supported-sections",
        "evaluator-supported-sections",
        "realization-support-modes",
        "concept-provenance-categories",
    }


def test_controlled_vocabulary_catalog_path_resolves():
    assert controlled_vocabulary_catalog_path() == CATALOG_PATH


def test_controlled_vocabulary_catalog_matches_valid_fixture():
    payload = json.loads((VALID_DIR / "reference.json").read_text(encoding="utf-8"))
    authoritative = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert payload == authoritative
    assert ControlledVocabularyCatalogModel.model_validate(payload).vocabularies["processor-features"].terms


def test_attack_enterprise_tactics_source_pins_mitre_v19_1():
    payload = json.loads(ATTACK_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    source = AttackEnterpriseTacticsSourceModel.model_validate(payload)

    assert source.source_authority == "MITRE ATT&CK"
    assert source.source_domain == "enterprise-attack"
    assert source.source_version == "v19.1"
    assert source.source_digest == "sha256:bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"
    assert source.retrieved_at == "2026-07-01"
    assert source.license_url == "https://attack.mitre.org/resources/legal-and-branding/terms-of-use/"
    assert source.license_notice.startswith("\u00a9 2026 The MITRE Corporation.")
    assert [(term.shortname, term.tactic_id, term.name) for term in source.tactics] == (
        ATTACK_ENTERPRISE_TACTIC_TERMS_V19_1
    )


def test_nist_csf_defensive_category_source_pins_csf_2_0():
    payload = json.loads(NIST_CSF_DEFENSIVE_SOURCE_PATH.read_text(encoding="utf-8"))
    source = NistCsfDefensiveCategorySourceModel.model_validate(payload)

    assert source.source_authority == "NIST Cybersecurity Framework"
    assert source.source_version == "2.0"
    assert source.source_digest == "sha256:014492980e87f8ce2c98d80ea040540392de96a08980c2f9901114ad4108b2c3"
    assert source.retrieved_at == "2026-07-19"
    assert source.license_url == "https://www.nist.gov/copyrights-disclaimers"
    assert source.license_notice.startswith("Adapted from NIST CSF 2.0")
    assert [
        (term.term_id, term.category_id, term.title, term.function) for term in source.categories
    ] == NIST_CSF_DEFENSIVE_CATEGORY_TERMS_2_0


def test_nist_csf_defensive_category_source_rejects_duplicate_ids_and_term_ids():
    payload = json.loads(NIST_CSF_DEFENSIVE_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["categories"][1]["category_id"] = payload["categories"][0]["category_id"]
    with pytest.raises(ValidationError, match="duplicate category_id"):
        NistCsfDefensiveCategorySourceModel.model_validate(payload)

    payload = json.loads(NIST_CSF_DEFENSIVE_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["categories"][1]["term_id"] = payload["categories"][0]["term_id"]
    with pytest.raises(ValidationError, match="duplicate term_id"):
        NistCsfDefensiveCategorySourceModel.model_validate(payload)


def test_nist_csf_defensive_category_source_schema_is_published():
    schema = schema_bundle()["nist-csf-defensive-categories-source-v1"]

    assert schema["properties"]["schema_version"]["const"] == "nist-csf-defensive-categories-source/v1"


def test_attack_enterprise_tactics_source_rejects_duplicate_ids_and_shortnames():
    payload = json.loads(ATTACK_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["tactics"][1]["tactic_id"] = payload["tactics"][0]["tactic_id"]
    with pytest.raises(ValidationError, match="duplicate tactic_id"):
        AttackEnterpriseTacticsSourceModel.model_validate(payload)

    payload = json.loads(ATTACK_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["tactics"][1]["shortname"] = payload["tactics"][0]["shortname"]
    with pytest.raises(ValidationError, match="duplicate shortname"):
        AttackEnterpriseTacticsSourceModel.model_validate(payload)


def test_atlas_tactics_source_pins_mitre_atlas_2026_06():
    payload = json.loads(ATLAS_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    source = AtlasTacticsSourceModel.model_validate(payload)

    assert source.source_authority == "MITRE ATLAS"
    assert source.source_version == "2026.06"
    assert source.source_format_version == "6.0.0"
    assert source.source_digest == "sha256:b771de8b1489564b2838a709c7429849a9575dbd94073928817fe1a21661e70a"
    assert source.retrieved_at == "2026-07-02"
    assert source.collection_id == "ATLAS-collection"
    assert source.matrix_id == "ATLAS-matrix"
    assert source.license_url == "https://github.com/mitre-atlas/atlas-data/blob/main/LICENSE"
    assert source.license_notice.startswith("Copyright 2021-2026 MITRE.")
    assert [(term.shortname, term.tactic_id, term.name) for term in source.tactics] == ATLAS_TACTIC_TERMS_2026_06


def test_atlas_tactics_source_rejects_duplicate_ids_shortnames_and_positions():
    payload = json.loads(ATLAS_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["tactics"][1]["tactic_id"] = payload["tactics"][0]["tactic_id"]
    with pytest.raises(ValidationError, match="duplicate tactic_id"):
        AtlasTacticsSourceModel.model_validate(payload)

    payload = json.loads(ATLAS_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["tactics"][1]["shortname"] = payload["tactics"][0]["shortname"]
    with pytest.raises(ValidationError, match="duplicate shortname"):
        AtlasTacticsSourceModel.model_validate(payload)

    payload = json.loads(ATLAS_TACTICS_SOURCE_PATH.read_text(encoding="utf-8"))
    payload["tactics"][1]["position"] = payload["tactics"][0]["position"]
    with pytest.raises(ValidationError, match="duplicate position"):
        AtlasTacticsSourceModel.model_validate(payload)


def test_controlled_vocabulary_valid_fixtures_pass_validation():
    for path in sorted(VALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = ControlledVocabularyCatalogModel.model_validate(payload)
        assert model.vocabularies, f"Valid vocabulary fixture {path.name} should declare vocabularies"


def test_controlled_vocabulary_invalid_fixtures_fail_validation():
    for path in sorted(INVALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            ControlledVocabularyCatalogModel.model_validate(payload)


def test_closed_enum_vocabularies_match_python_enums():
    catalog = load_controlled_vocabulary_catalog()

    assert set(catalog.vocabularies["processor-features"].terms) == {feature.value for feature in ProcessorFeature}
    assert set(catalog.vocabularies["workflow-features"].terms) == {feature.value for feature in WorkflowFeature}
    assert set(catalog.vocabularies["workflow-state-predicate-features"].terms) == {
        feature.value for feature in WorkflowStatePredicateFeature
    }
    assert set(catalog.vocabularies["realization-support-modes"].terms) == {
        mode.value for mode in RealizationSupportMode
    }
    assert set(catalog.vocabularies["concept-provenance-categories"].terms) == {
        category.value for category in ConceptProvenanceCategory
    }
    assert set(catalog.vocabularies["participant-runtime-feature-support-levels"].terms) == {
        level.value for level in ParticipantFeatureSupportLevel
    }


@pytest.mark.parametrize(
    ("vocabulary", "extension"),
    [
        ("provisioner-node-types", "bare-metal"),
        ("orchestrator-supported-sections", "custom-stage"),
        ("participant-decision-surface-modes", "swarm-control"),
    ],
)
def test_governed_extension_values_are_allowed_for_extensible_vocabularies(vocabulary, extension):
    validate_controlled_vocabulary_value(vocabulary, "x-acme:" + extension)
    with pytest.raises(ValueError, match="not a permitted term"):
        validate_controlled_vocabulary_value(vocabulary, extension)


def test_behavior_specification_behavior_mode_scope_uses_decision_surface_vocabulary():
    validate_controlled_vocabulary_scope_values(
        "behavior_specifications.behavior_mode",
        ["autonomous", "human-supervised", "x-acme:swarm-control"],
    )
    with pytest.raises(ValueError, match="not a permitted term"):
        validate_controlled_vocabulary_scope_values("behavior_specifications.behavior_mode", ["swarm-control"])


@pytest.mark.parametrize(
    ("vocabulary", "terms"),
    [
        (
            "participant-offensive-behavior-activities",
            ["reconnaissance", "defense-impairment", "stealth", "exfiltration"],
        ),
        (
            "participant-ai-offensive-behavior-activities",
            ["ai-model-access", "defense-evasion", "ai-attack-staging", "impact"],
        ),
        (
            "participant-defensive-behavior-activities",
            ["continuous-monitoring", "incident-analysis", "incident-mitigation"],
        ),
    ],
)
def test_behavior_classification_catalog_accepts_only_governed_terms(vocabulary, terms):
    for term in terms:
        validate_controlled_vocabulary_value(vocabulary, term)
    with pytest.raises(ValueError, match="not a permitted term"):
        validate_controlled_vocabulary_value(vocabulary, "unregistered-activity")


def test_defensive_behavior_vocabulary_adapts_pinned_nist_csf_categories():
    catalog = load_controlled_vocabulary_catalog()
    vocabulary = catalog.vocabularies["participant-defensive-behavior-activities"]

    assert vocabulary.source is not None
    assert vocabulary.source.provenance == "adapted"
    assert vocabulary.source.authority == "NIST Cybersecurity Framework"
    assert vocabulary.source.authority_version == "2.0"
    assert (
        vocabulary.source.source_artifact_ref
        == "contracts/concept-authority/nist-csf-defensive-categories-source-v1.json"
    )
    assert vocabulary.source.source_digest == "sha256:014492980e87f8ce2c98d80ea040540392de96a08980c2f9901114ad4108b2c3"
    assert [(term_id, term.source_id, term.title) for term_id, term in vocabulary.terms.items()] == [
        (term_id, source_id, title) for term_id, source_id, title, _function in NIST_CSF_DEFENSIVE_CATEGORY_TERMS_2_0
    ]


def test_offensive_behavior_vocabulary_directly_adopts_pinned_attack_tactics():
    catalog = load_controlled_vocabulary_catalog()
    vocabulary = catalog.vocabularies["participant-offensive-behavior-activities"]

    assert vocabulary.source is not None
    assert vocabulary.source.provenance == "adopted"
    assert vocabulary.source.authority == "MITRE ATT&CK Enterprise"
    assert vocabulary.source.authority_version == "v19.1"
    assert (
        vocabulary.source.source_artifact_ref == "contracts/concept-authority/attack-enterprise-tactics-source-v1.json"
    )
    assert vocabulary.source.source_digest == "sha256:bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"
    assert [(term_id, term.source_id, term.title) for term_id, term in vocabulary.terms.items()] == (
        ATTACK_ENTERPRISE_TACTIC_TERMS_V19_1
    )
    assert vocabulary.terms["defense-impairment"].source_url == "https://attack.mitre.org/tactics/TA0112"


def test_ai_offensive_behavior_vocabulary_directly_adopts_pinned_atlas_tactics():
    catalog = load_controlled_vocabulary_catalog()
    vocabulary = catalog.vocabularies["participant-ai-offensive-behavior-activities"]

    assert vocabulary.source is not None
    assert vocabulary.source.provenance == "adopted"
    assert vocabulary.source.authority == "MITRE ATLAS"
    assert vocabulary.source.authority_version == "2026.06"
    assert vocabulary.source.source_artifact_ref == "contracts/concept-authority/atlas-tactics-source-v1.json"
    assert vocabulary.source.source_digest == "sha256:b771de8b1489564b2838a709c7429849a9575dbd94073928817fe1a21661e70a"
    assert [(term_id, term.source_id, term.title) for term_id, term in vocabulary.terms.items()] == (
        ATLAS_TACTIC_TERMS_2026_06
    )
    assert vocabulary.terms["ai-model-access"].source_url == "https://atlas.mitre.org/tactics/AML.TA0000/"


def test_old_defense_evasion_tactic_is_not_a_pinned_attack_v19_1_term():
    with pytest.raises(ValueError, match="not a permitted term"):
        [
            validate_controlled_vocabulary_value("participant-offensive-behavior-activities", term)
            for term in ["defense-evasion"]
        ]


def test_attack_and_atlas_scopes_do_not_bleed_into_each_other():
    with pytest.raises(ValueError, match="not a permitted term"):
        [
            validate_controlled_vocabulary_value("participant-offensive-behavior-activities", term)
            for term in ["ai-model-access"]
        ]
    with pytest.raises(ValueError, match="not a permitted term"):
        [
            validate_controlled_vocabulary_value("participant-ai-offensive-behavior-activities", term)
            for term in ["defense-impairment"]
        ]


def test_offensive_and_defensive_scopes_do_not_bleed_into_each_other():
    for offensive_scope in (
        "participant-offensive-behavior-activities",
        "participant-ai-offensive-behavior-activities",
    ):
        with pytest.raises(ValueError, match="not a permitted term"):
            [validate_controlled_vocabulary_value(offensive_scope, term) for term in ["continuous-monitoring"]]

    for offensive_term in ("reconnaissance", "ai-model-access"):
        with pytest.raises(ValueError, match="not a permitted term"):
            [
                validate_controlled_vocabulary_value("participant-defensive-behavior-activities", term)
                for term in [offensive_term]
            ]


def test_unguarded_extension_values_are_rejected():
    with pytest.raises(ValueError, match="not a permitted term"):
        validate_controlled_vocabulary_value("provisioner-node-types", "bare-metal")


def test_extensions_are_rejected_for_closed_vocabularies():
    with pytest.raises(ValueError, match="does not allow extensions"):
        validate_controlled_vocabulary_value("realization-support-modes", "x-acme:custom-mode")
