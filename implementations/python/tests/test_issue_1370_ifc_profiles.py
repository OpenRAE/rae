"""Real finite-profile readers and owner-qualified SEM-233 context checks."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ParticipantFlowControlRelationModel
from raes_contracts.contracts.participant_flow_control_validation import validate_participant_flow_control_context
from raes_contracts.participant_flow_policy_profiles import (
    load_participant_boundary_flow_policy_profile,
    load_participant_boundary_flow_policy_profile_revision,
)
from test_sem_233_flow_control_contracts import _context_relation_payload, _validation_context

OWNER_PROFILE = "participant-owner-flow-policy-v1"
CA, CB = "confidentiality:owner-a", "confidentiality:owner-b"
IA, IB = "integrity:owner-a:untrusted", "integrity:owner-b:untrusted"
EA = "integrity:owner-a:endorsed"


def owner_relation(*, reader="reader:carol", observation=True, base_relation=None, base_context=None):
    from raes_contracts.contracts.participant_owner_flow import (
        ParticipantFlowObligationAuthorityCoordinate,
        ParticipantOwnerFlowSinkResolution,
    )

    profile = load_participant_boundary_flow_policy_profile(OWNER_PROFILE)
    pin = dict(
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        authority_revision=profile.authority_revision,
    )
    payload = base_relation.model_dump(mode="json") if base_relation is not None else _context_relation_payload()
    payload["profile"] = pin
    for records in (
        payload["labels"],
        payload["derivations"],
        payload["releases"],
        payload["bindings"],
        payload["sink_decisions"],
    ):
        for item in records:
            item["profile"] = pin
    coordinates = [([CA], [IA]), ([CB], [IB]), ([CA, CB], [IA, IB]), ([CB], [IA, IB]), ([CB], [EA, IB])]
    for label, (confidentiality, integrity) in zip(payload["labels"], coordinates, strict=True):
        label["confidentiality_obligation_refs"] = sorted(confidentiality)
        label["integrity_obligation_refs"] = sorted(integrity)
    payload["releases"][0]["removed_confidentiality_obligation_refs"] = [CA]
    payload["releases"][1]["integrity_obligation_replacements"] = [
        dict(source_obligation_ref=IA, result_obligation_ref=EA)
    ]
    payload["sink_decisions"][0].update(
        confidentiality_result="satisfied" if reader in {"reader:bob", "reader:carol"} else "deny",
        integrity_result="satisfied" if observation else "deny",
        final_disposition="permit" if observation and reader in {"reader:bob", "reader:carol"} else "deny",
    )
    relation = ParticipantFlowControlRelationModel.model_validate(payload)
    old = base_context or _validation_context()
    sink = next(iter(old.known_sinks))
    grants = tuple(
        ParticipantFlowObligationAuthorityCoordinate(
            release_digest=canonical_json_digest(release.model_dump(mode="json")),
            owner_ref="owner:a",
            obligation_ref=obligation,
        )
        for release, obligation in zip(relation.releases, (CA, IA), strict=True)
    )
    context = replace(
        old,
        profiles={(profile.profile_id, profile.profile_revision): profile},
        source_labels={label.label_id: label for label in relation.labels[:2]},
        owner_release_authorities=grants,
        owner_sink_resolutions={
            sink: ParticipantOwnerFlowSinkResolution(
                readers=frozenset({reader}), accepts_untrusted_integrity=observation
            )
        },
    )
    return relation, context


def test_flow_crossing_carrier_accepts_the_runtime_digest_identity():
    from raes_contracts.contracts.participant_flow_control import ParticipantCrossingOccurrenceFlowBindingModel

    payload = _context_relation_payload()["bindings"][-1]
    payload["subject_revision"] = None
    payload["subject_digest"] = "sha256:" + "a" * 64
    assert ParticipantCrossingOccurrenceFlowBindingModel.model_validate(payload).subject_revision is None
    payload["subject_digest"] = None
    with pytest.raises(ValueError, match="revision or digest"):
        ParticipantCrossingOccurrenceFlowBindingModel.model_validate(payload)


def test_owner_publication_loads_exactly_and_preserves_legacy():
    legacy = load_participant_boundary_flow_policy_profile("participant-boundary-flow-policy-v1")
    profile = load_participant_boundary_flow_policy_profile(OWNER_PROFILE)
    assert {clause.owner_ref for clause in profile.owner_clauses} == {"owner:a", "owner:b"}
    assert len(profile.confidentiality_obligation_refs) == 3
    assert profile == load_participant_boundary_flow_policy_profile_revision(
        OWNER_PROFILE, "rev1", profile.canonical_digest
    )
    with pytest.raises(ValueError, match="digest"):
        load_participant_boundary_flow_policy_profile_revision(OWNER_PROFILE, "rev1", legacy.canonical_digest)
    assert legacy.confidentiality_obligation_refs == ("confidentiality:restricted", "confidentiality:unknown")
    with pytest.raises(ValueError, match="frozen"):
        profile.title = "mutated cached profile"
    with pytest.raises(ValueError, match="frozen"):
        legacy.title = "mutated cached profile"
    rule = legacy.derivation_rule.model_copy()
    with pytest.raises(ValueError, match="frozen"):
        rule.rule_ref = "changed published meaning"


def test_flow_relation_graph_is_bounded_before_recursive_validation():
    payload = _context_relation_payload()
    prototype = payload["labels"][0]
    payload["labels"].extend({**prototype, "label_id": f"extra-label-{i}"} for i in range(257))
    with pytest.raises(ValueError, match="256"):
        ParticipantFlowControlRelationModel.model_validate(payload)


@pytest.mark.parametrize("reader", ["reader:alice", "reader:bob", "reader:carol"])
@pytest.mark.parametrize("observation", [False, True])
def test_selective_release_and_endorsement_preserve_b_and_provenance(reader, observation):
    relation, context = owner_relation(reader=reader, observation=observation)
    validate_participant_flow_control_context(relation, context)
    original, result = relation.labels[2], relation.labels[-1]
    assert original.confidentiality_obligation_refs == (CA, CB)
    assert result.confidentiality_obligation_refs == (CB,)
    assert result.integrity_obligation_refs == (EA, IB)
    assert set(original.provenance_refs) <= set(result.provenance_refs)
    assert set(original.influence_refs) <= set(result.influence_refs)


@pytest.mark.parametrize("change", ["missing", "other-owner", "other-token", "other-release", "other-cut"])
def test_owner_grants_are_per_obligation_and_bind_the_entire_release(change):
    relation, context = owner_relation()
    grants = context.owner_release_authorities
    if change == "missing":
        grants = grants[:1]
    elif change == "other-owner":
        grants = (replace(grants[0], owner_ref="owner:b"), grants[1])
    elif change == "other-token":
        grants = (replace(grants[0], obligation_ref=CB), grants[1])
    elif change == "other-release":
        grants = (replace(grants[0], release_digest=grants[1].release_digest), grants[1])
    else:
        payload = relation.model_dump(mode="json")
        for records in (
            payload["labels"],
            payload["derivations"],
            payload["releases"],
            payload["bindings"],
            payload["sink_decisions"],
        ):
            for item in records:
                item["policy"]["decision_cut_revision"] = "new-cut"
        relation = ParticipantFlowControlRelationModel.model_validate(payload)
        context = replace(
            context,
            policy_cuts={relation.labels[0].policy.decision_cut_ref: relation.labels[0].policy},
            source_labels={label.label_id: label for label in relation.labels[:2]},
        )
    with pytest.raises(ValueError, match="owner|obligation"):
        validate_participant_flow_control_context(relation, replace(context, owner_release_authorities=grants))


def test_provider_cannot_self_certify_audience_or_accept_untrusted_action_influence():
    relation, context = owner_relation(reader="reader:alice", observation=False)
    forged = relation.model_dump(mode="json")
    forged["sink_decisions"][0].update(
        confidentiality_result="satisfied", integrity_result="satisfied", final_disposition="permit"
    )
    with pytest.raises(ValueError, match="owner.*sink|owner.*coordinate"):
        validate_participant_flow_control_context(ParticipantFlowControlRelationModel.model_validate(forged), context)
    with pytest.raises(ValueError, match="owner.*sink"):
        validate_participant_flow_control_context(relation, replace(context, owner_sink_resolutions={}))


def test_owner_endorsement_cannot_replace_a_with_b_or_clear_provenance():
    relation, context = owner_relation()
    payload = relation.model_dump(mode="json")
    payload["releases"][1]["integrity_obligation_replacements"][0]["result_obligation_ref"] = (
        "integrity:owner-b:endorsed"
    )
    payload["labels"][-1]["integrity_obligation_refs"] = ["integrity:owner-b:endorsed", IB]
    forged = ParticipantFlowControlRelationModel.model_validate(payload)
    with pytest.raises(ValueError, match="endorsement|replacement"):
        validate_participant_flow_control_context(forged, context)
    payload = relation.model_dump(mode="json")
    payload["labels"][-1]["provenance_refs"] = ["provenance:new"]
    with pytest.raises(ValueError, match="provenance"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_unpublished_third_owner_and_unknown_source_never_gain_support():
    relation, context = owner_relation()
    payload = relation.model_dump(mode="json")
    for label in payload["labels"]:
        label["confidentiality_obligation_refs"] = sorted(
            [*label["confidentiality_obligation_refs"], "confidentiality:owner-c"]
        )
    forged = ParticipantFlowControlRelationModel.model_validate(payload)
    with pytest.raises(ValueError, match="outside the exact profile"):
        validate_participant_flow_control_context(forged, context)
    profile = next(iter(context.profiles.values()))
    changed = deepcopy(profile.model_dump(mode="json"))
    changed["owner_clauses"][0]["reader_refs"] = ["reader:carol"]
    with pytest.raises(ValueError, match="exact published"):
        type(profile).model_validate(changed)


def test_api_424_owner_fact_resolves_exact_relation_profile_label_and_sink():
    from participant_control_contract_fixtures import ref
    from raes_contracts.contracts.participant_control_resolution import _validate_security_fact
    from raes_contracts.contracts.participant_control_results import ControlOwnerSecurityFactModel
    from test_api_424_security_profile import security_record_and_context

    relation, owner_context = owner_relation()
    legacy, context = security_record_and_context()
    fact = ControlOwnerSecurityFactModel(
        kind="ifc-fact",
        domain="owner-ifc/rev1",
        profile={**ref(OWNER_PROFILE, "profile"), "digest": relation.profile.profile_digest},
        relation={
            **ref(relation.document_id, "flow-relation"),
            "digest": canonical_json_digest(relation.model_dump(mode="json")),
        },
        label_ref=relation.labels[-1].label_id,
        sink_decision_ref=relation.sink_decisions[0].decision_id,
        sink_disposition="permit",
    )
    context = replace(
        context, flow_relations={relation.document_id: relation}, flow_contexts={relation.document_id: owner_context}
    )
    _validate_security_fact(fact, legacy.request.context, context)
    forged = fact.model_copy(update={"sink_disposition": "deny"})
    with pytest.raises(ValueError, match="sink binding"):
        _validate_security_fact(forged, legacy.request.context, context)
    with pytest.raises(ValueError, match="exact incumbent relation"):
        _validate_security_fact(fact, legacy.request.context, replace(context, flow_contexts={}))


def test_owner_schema_publication_and_conformance_use_the_exact_profile_reader():
    import json

    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT
    from raes_conformance.conformance.validators import validate_contract_payload
    from raes_contracts.contracts import schema_bundle

    schema = schema_bundle()[OWNER_PROFILE]
    assert (
        json.loads((REPO_ROOT / "contracts/schemas/profiles/participant-owner-flow-policy-v1.json").read_text())
        == schema
    )
    valid = load_participant_boundary_flow_policy_profile(OWNER_PROFILE).model_dump(mode="json")
    Draft202012Validator(schema).validate(valid)
    assert not validate_contract_payload(OWNER_PROFILE, valid)
    valid["owner_clauses"][0]["reader_refs"] = ["reader:carol"]
    Draft202012Validator(schema).validate(valid)  # Shape alone proves no publication.
    assert validate_contract_payload(OWNER_PROFILE, valid)


def test_new_specification_capture_analyses_bind_their_own_snapshot_identities():
    import json

    from paths import REPO_ROOT
    from tools.specification_coverage._analysis import _validate_analysis

    scope = json.loads((REPO_ROOT / "docs/governance/requirement-scopes/1370.json").read_text())
    captures = [
        path
        for path in scope["bindings"]
        if "/specification-coverage/captures/" in path and path.endswith("/manifest.json")
    ]
    assert captures
    for path in captures:
        manifest = json.loads((REPO_ROOT / path).read_text())
        protocol, snapshot, analysis = (
            json.loads((REPO_ROOT / manifest[key + "_path"]).read_text())
            for key in ("protocol", "snapshot", "analysis")
        )
        failures = []
        _validate_analysis(protocol, snapshot, analysis, failures, path)
        assert failures == [], [(item.rule_id, item.message) for item in failures]
