"""Admission of closed binary profiles and preservation of unary profiles."""

from copy import deepcopy

import pytest
from crossing_model_fixtures import profile_payload
from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel
from raes_contracts.behavioral_relations import (
    load_behavioral_relation_catalog_revision,
    validate_behavioral_claim_binding,
)
from raes_contracts.contracts.base import BehavioralClaimBindingModel


def test_admit_complete_profile():
    payload = profile_payload()
    profile = BehavioralRelationProfileModel.model_validate(payload)
    assert profile.model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "name,valid",
    [
        ("valid/participant-crossing.json", True),
        ("invalid/incomplete-crossing-domain.json", False),
        ("invalid/overlapping-crossing-labels.json", False),
        ("invalid/shared-crossing-authority.json", False),
    ],
)
def test_published_crossing_fixtures(name, valid):
    import json

    from crossing_model_fixtures import ROOT
    from raes_conformance.conformance import _fixture_case_diagnostics

    payload = json.loads((ROOT / "contracts/fixtures/profiles/behavioral-relation-profile-v1" / name).read_bytes())
    diagnostics = _fixture_case_diagnostics("behavioral-relation-profile-v1", payload)
    assert (not diagnostics) == valid


def test_profile_loader_rejects_symlink(tmp_path):
    import json

    from raes_contracts.behavioral_relation_profiles import load_behavioral_relation_profile_from_path

    target = tmp_path / "profile.json"
    target.write_text(json.dumps(profile_payload()))
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="invalid"):
        load_behavioral_relation_profile_from_path("participant-crossing-dpbb-finite-v1", link)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-domain",
        "truncated-inputs",
        "sample",
        "incomplete",
        "duplicate-visible",
        "overlap",
        "native-tau",
        "same-authority",
        "same-source",
        "unsafe-path",
        "unsafe-id",
        "long-id",
        "bool-ordinal",
        "wrong-left",
        "wrong-relation",
        "wrong-projection",
        "wrong-revision",
    ],
)
def test_reject_incomplete_or_unsafe_profile(mutation):
    payload = deepcopy(profile_payload())
    params = payload["parameters"]
    if mutation == "missing-domain":
        del params["domains"]["audience"]
    elif mutation == "truncated-inputs":
        params["domains"]["input_class"].pop()
    elif mutation == "sample":
        params["depth_or_sample_bound"] = 2
    elif mutation == "incomplete":
        params["complete_carrier"] = False
    elif mutation == "duplicate-visible":
        params["visible_labels"].append("crossing.request")
    elif mutation == "overlap":
        params["hidden_labels"][0] = "crossing.request"
    elif mutation == "native-tau":
        params["visible_labels"][0] = "tau"
    elif mutation == "same-authority":
        params["right"] = deepcopy(params["left"])
    elif mutation == "same-source":
        params["right"]["source_digest"] = params["left"]["source_digest"]
    elif mutation == "unsafe-path":
        params["left"]["source_path"] = "../../private"
    elif mutation in {"unsafe-id", "long-id"}:
        params["left"]["model_id"] = "../unsafe" if mutation == "unsafe-id" else "x" * 500
    elif mutation == "bool-ordinal":
        params["left"]["initial_state_ordinal"] = False
    elif mutation == "wrong-left":
        payload["left_carrier_ref"] = "different-carrier"
    elif mutation == "wrong-relation":
        payload["relation_id"] = "participant-predicate-opacity"
    elif mutation == "wrong-projection":
        payload["observation_projection_revision"] = "rev2"
    else:
        payload["profile_revision"] = "rev1"
    with pytest.raises(ValueError):
        BehavioralRelationProfileModel.model_validate(payload)


def crossing_binding(profile):
    return BehavioralClaimBindingModel(
        taxonomy_id=profile.taxonomy_id,
        taxonomy_revision=profile.taxonomy_revision,
        relation_id=profile.relation_id,
        subject="Synthetic binding validation; no equivalence result.",
        left_carrier_ref=profile.left_carrier_ref,
        right_carrier_ref=profile.parameters.right.model_id,
        observation_projection_ref=profile.observation_projection_ref,
        observation_projection_revision=profile.observation_projection_revision,
        relation_parameter_profile_ref=profile.profile_id,
        relation_parameter_profile_revision=profile.profile_revision,
        quantifier_scope="finite-cases",
        evidence_scope="structural",
        assurance_axis="definition",
        evidence_boundary="Synthetic contract fixture only.",
        assurance_status="defined",
        limitations=["No comparison executed."],
        explicit_non_claims=["No equivalence result."],
    )


def test_binary_binding_checks_both_carriers():
    profile = BehavioralRelationProfileModel.model_validate(profile_payload())
    binding = crossing_binding(profile)
    catalog = load_behavioral_relation_catalog_revision("rev8")
    validate_behavioral_claim_binding(binding, catalog=catalog, profile=profile)
    with pytest.raises(ValueError, match="right carrier"):
        validate_behavioral_claim_binding(
            binding.model_copy(update={"right_carrier_ref": "wrong"}), catalog=catalog, profile=profile
        )


def test_opacity_consumers_reject_binary_profile_before_accessing_parameters():
    from types import SimpleNamespace

    from raes_contracts.participant_opacity_runtime import validate_participant_opacity_runtime_enforcement
    from raes_processor.participant_opacity import ParticipantOpacityOperationalError, _model_check_admission, _service
    from test_issue_964_participant_opacity_runtime import _binding, _support

    profile = BehavioralRelationProfileModel.model_validate(profile_payload())
    request = SimpleNamespace(analysis_profile=_service.ANALYSIS_PROFILE, profile_id="participant-opacity-baseline-v1")
    with pytest.raises(ParticipantOpacityOperationalError, match="opacity parameter profile"):
        _service._validate_profile_admission(request, profile)
    catalog = load_behavioral_relation_catalog_revision("rev8")
    request.analysis_profile = _model_check_admission.ANALYSIS_PROFILE
    from raes_contracts.canonical import canonical_json_digest

    request.catalog_digest = canonical_json_digest(catalog.model_dump(mode="json"))
    with pytest.raises(ParticipantOpacityOperationalError, match="opacity parameter profile"):
        _model_check_admission.validate_admission(request, profile, catalog)
    with pytest.raises(ValueError, match="profile"):
        validate_participant_opacity_runtime_enforcement(
            _binding(),
            support=_support(),
            participant_address="participant-0",
            audience_scope_ref="audience-0",
            profile=profile,
        )


@pytest.mark.parametrize("consumer", ["analysis", "model-check"])
def test_opacity_rejects_crossing_profile_with_matching_claim_and_coordinates(consumer):
    from types import SimpleNamespace

    from raes_contracts.canonical import canonical_json_digest
    from raes_processor.participant_opacity import ParticipantOpacityOperationalError, _model_check_admission, _service

    profile = BehavioralRelationProfileModel.model_validate(profile_payload())
    catalog = load_behavioral_relation_catalog_revision("rev8")
    request = SimpleNamespace(
        analysis_profile=_service.ANALYSIS_PROFILE
        if consumer == "analysis"
        else _model_check_admission.ANALYSIS_PROFILE,
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        claim=crossing_binding(profile),
        catalog_digest=canonical_json_digest(catalog.model_dump(mode="json")),
        assumptions=None,
        declared_counts=None,
    )
    with pytest.raises(ParticipantOpacityOperationalError, match="opacity parameter profile"):
        if consumer == "analysis":
            _service._validate_profile_admission(request, profile)
            _service._validate_profile_domains(request, profile)
        else:
            _model_check_admission.validate_admission(request, profile, catalog)
