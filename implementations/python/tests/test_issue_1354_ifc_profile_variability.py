"""Bounded #1354 witnesses; synthetic owner profiles are not published support."""

from dataclasses import replace

import pytest
from ifc_profile_variability_model import (
    Encoding,
    Grant,
    Requirement,
    Support,
    admit,
    check_execution,
    release,
)
from jsonschema import Draft202012Validator
from raes_contracts.contracts import ParticipantBoundaryFlowPolicyProfileModel, schema_bundle
from raes_contracts.participant_flow_policy_profiles import load_participant_boundary_flow_policy_profile
from sem233_boundary_flow_model import (
    FlowGateState,
    FlowOperation,
    FlowProfile,
    FlowValue,
    SinkPolicy,
    UnsupportedFlow,
    carry,
    derive,
    may_flow_at_sink,
)

PROFILE = FlowProfile(
    "example-owner-ifc",
    "rev1",
    "ifc-profile-variability/rev1",
    frozenset({"conf:A", "conf:B", "conf:deny-unresolved"}),
    frozenset({"int:A", "int:B", "int:deny-unresolved"}),
)
ENCODING = Encoding(PROFILE, (("A", "conf:A"), ("B", "conf:B")), (("A", "int:A"), ("B", "int:B")))
REQUIREMENT = Requirement(
    frozenset({"A", "B"}),
    frozenset({"A", "B"}),
    frozenset({"source:A", "source:B", "flow:memory", "sink:action"}),
    frozenset({"explicit-boundary-flow"}),
)
SUPPORT = Support(ENCODING.pin, "configuration:1", REQUIREMENT.coverage, REQUIREMENT.guarantees)
GRANT_A = Grant(
    "authority:A",
    frozenset({"conf:A"}),
    frozenset({"int:A"}),
    "sink:action",
    "cut:1",
    "summary:AB",
    (PROFILE.profile_id, PROFILE.profile_revision),
)


def value(owner):
    return FlowValue(
        f"value:{owner}",
        PROFILE.label(confidentiality={f"conf:{owner}"}, integrity={f"int:{owner}"}),
        frozenset({f"source:{owner}"}),
        frozenset({f"writer:{owner}"}),
        "participant:1",
        "episode:1",
        "policy:1",
        "rev1",
        "cut:1",
    )


def combined():
    return derive(
        PROFILE,
        result_ref="summary:AB",
        inputs=(value("A"), value("B")),
        participant_ref="participant:1",
        episode_ref="episode:1",
        policy_ref="policy:1",
        policy_revision="rev1",
        state_cut_ref="cut:1",
    )


def sink(confidentiality, integrity):
    return SinkPolicy(
        "sink:action",
        "destination:1",
        PROFILE.profile_id,
        "rev1",
        "policy:1",
        "rev1",
        "cut:1",
        frozenset(confidentiality),
        frozenset(integrity),
    )


def test_finite_owner_encoding_admits_only_evidenced_coverage():
    assert admit(REQUIREMENT, ENCODING, SUPPORT) == SUPPORT
    for missing in REQUIREMENT.coverage:
        incomplete = replace(SUPPORT, coverage=SUPPORT.coverage - {missing})
        with pytest.raises(UnsupportedFlow, match="realization"):
            admit(REQUIREMENT, ENCODING, incomplete)
    unresolved = replace(SUPPORT, resolved=False)
    with pytest.raises(UnsupportedFlow, match="realization"):
        admit(REQUIREMENT, ENCODING, unresolved)
    no_guarantees = replace(SUPPORT, guarantees=frozenset())
    with pytest.raises(UnsupportedFlow, match="realization"):
        admit(REQUIREMENT, ENCODING, no_guarantees)


@pytest.mark.parametrize("coordinate,prefix", [("confidentiality", "conf"), ("integrity", "int")])
@pytest.mark.parametrize("bad_mapping", ["collapsed", "missing", "unknown", "unresolved", "duplicate"])
def test_independent_obligations_cannot_be_collapsed_or_invented(coordinate, prefix, bad_mapping):
    maps = {
        "collapsed": (("A", f"{prefix}:A"), ("B", f"{prefix}:A")),
        "missing": (("A", f"{prefix}:A"),),
        "unknown": (("A", f"{prefix}:A"), ("B", f"{prefix}:C")),
        "unresolved": (("A", f"{prefix}:A"), ("B", f"{prefix}:deny-unresolved")),
        "duplicate": (("A", f"{prefix}:A"), ("A", f"{prefix}:B"), ("B", f"{prefix}:B")),
    }
    invalid_encoding = replace(ENCODING, **{coordinate: maps[bad_mapping]})
    with pytest.raises(UnsupportedFlow, match="expression"):
        admit(REQUIREMENT, invalid_encoding, SUPPORT)


def test_admitted_bounded_guarantee_is_distinct_from_unexpected_weakening():
    bounded = admit(REQUIREMENT, ENCODING, SUPPORT)
    assert check_execution(bounded, SUPPORT) == "resolved"
    stronger = replace(SUPPORT, guarantees=SUPPORT.guarantees | {"extra-instrumentation"})
    admitted_stronger = admit(REQUIREMENT, ENCODING, stronger)
    # Still meeting the author's floor does not erase an admitted promise.
    assert check_execution(admitted_stronger, SUPPORT) == "weakened"
    assert check_execution(bounded, replace(SUPPORT, coverage=SUPPORT.coverage - {"flow:memory"})) == "weakened"
    exact_required = replace(REQUIREMENT, guarantees=stronger.guarantees)
    with pytest.raises(UnsupportedFlow, match="realization"):
        admit(exact_required, ENCODING, SUPPORT)


@pytest.mark.parametrize(
    "change",
    [
        {"profile_pin": ("another-profile", "rev1", "digest:example")},
        {"configuration": "configuration:2"},
        {"resolved": False},
    ],
)
def test_changed_or_unresolved_binding_requires_new_admission(change):
    changed_support = replace(SUPPORT, **change)
    assert check_execution(SUPPORT, changed_support) == "unsupported"
    if "profile_pin" in change:
        with pytest.raises(UnsupportedFlow, match="realization"):
            admit(REQUIREMENT, ENCODING, changed_support)


@pytest.mark.parametrize(
    "reader,obligations,expected",
    [
        ("Alice", {"conf:A"}, False),
        ("Bob", {"conf:A", "conf:B"}, True),
        ("Carol", {"conf:B"}, False),
    ],
)
def test_combination_intersects_permitted_readers(reader, obligations, expected):
    destination = replace(sink(obligations, {"int:A", "int:B"}), destination_ref=reader)
    assert may_flow_at_sink(PROFILE, combined(), destination, FlowGateState.allowing()) is expected


def test_selective_release_preserves_other_owner_coordinate_and_history():
    source = combined()
    result = release(
        PROFILE,
        source,
        GRANT_A,
        result_ref="released:A",
        operation=FlowOperation.DECLASSIFICATION,
        confidentiality=frozenset({"conf:A"}),
    )
    assert result.label.confidentiality == frozenset({"conf:B"})
    assert result.label.integrity == source.label.integrity
    assert result.influence_refs == source.influence_refs
    assert source.provenance_refs <= result.provenance_refs
    assert source.label.confidentiality == frozenset({"conf:A", "conf:B"})
    assert may_flow_at_sink(PROFILE, result, sink({"conf:B"}, {"int:A", "int:B"}), FlowGateState.allowing())
    other_owner = frozenset({"conf:B"})
    with pytest.raises(UnsupportedFlow, match="authority"):
        release(
            PROFILE,
            source,
            GRANT_A,
            result_ref="release:B",
            operation=FlowOperation.DECLASSIFICATION,
            confidentiality=other_owner,
        )


def test_endorsement_is_owner_scoped_and_observation_does_not_clear_influence():
    source = combined()
    result = release(
        PROFILE,
        source,
        GRANT_A,
        result_ref="endorsed:A",
        operation=FlowOperation.ENDORSEMENT,
        integrity=frozenset({"int:A"}),
    )
    assert result.label.integrity == frozenset({"int:B"})
    assert result.label.confidentiality == source.label.confidentiality
    assert result.influence_refs == source.influence_refs
    assert not may_flow_at_sink(PROFILE, result, sink({"conf:A", "conf:B"}, set()), FlowGateState.allowing())
    assert may_flow_at_sink(PROFILE, result, sink({"conf:A", "conf:B"}, {"int:B"}), FlowGateState.allowing())
    assert result.label.integrity == frozenset({"int:B"})
    other_influence = frozenset({"int:B"})
    with pytest.raises(UnsupportedFlow, match="authority"):
        release(
            PROFILE,
            source,
            GRANT_A,
            result_ref="endorse:B",
            operation=FlowOperation.ENDORSEMENT,
            integrity=other_influence,
        )


@pytest.mark.parametrize("changes", [{"cut": "cut:2"}, {"sink": "sink:other"}])
def test_release_authority_is_bound_to_exact_sink_and_cut(changes):
    source = combined()
    changed_grant = replace(GRANT_A, **changes)
    discharged = frozenset({"conf:A"})
    with pytest.raises(UnsupportedFlow, match="authority"):
        release(
            PROFILE,
            source,
            changed_grant,
            result_ref="release:new",
            operation=FlowOperation.DECLASSIFICATION,
            confidentiality=discharged,
        )


@pytest.mark.parametrize("changed", ["source", "profile"])
def test_release_grant_cannot_be_reused_for_another_source_or_profile(changed):
    source, profile = combined(), PROFILE
    if changed == "source":
        source = replace(source, value_ref="different:source")
    else:
        profile = replace(PROFILE, profile_id="different-profile")
        source = replace(source, label=replace(source.label, profile_id=profile.profile_id))
    discharged = frozenset({"conf:A"})
    with pytest.raises(UnsupportedFlow, match="authority"):
        release(
            profile,
            source,
            GRANT_A,
            result_ref="release:new",
            operation=FlowOperation.DECLASSIFICATION,
            confidentiality=discharged,
        )


def test_retained_memory_and_unknown_inputs_cannot_launder_owner_obligations():
    source = combined()
    retained = carry(
        PROFILE,
        source,
        result_ref="memory:next",
        participant_ref="participant:2",
        episode_ref="episode:2",
        policy_ref="policy:1",
        policy_revision="rev1",
        state_cut_ref="cut:1",
    )
    assert retained.label == source.label
    assert source.influence_refs <= retained.influence_refs
    unknown = replace(retained, supported=False)
    assert not may_flow_at_sink(
        PROFILE, unknown, sink(PROFILE.confidentiality_universe, PROFILE.integrity_universe), FlowGateState.allowing()
    )


def test_schema_valid_owner_token_is_not_a_published_profile():
    original = load_participant_boundary_flow_policy_profile("participant-boundary-flow-policy-v1")
    payload = original.model_dump(mode="json")
    payload["confidentiality_obligation_refs"] = sorted(
        [*payload["confidentiality_obligation_refs"], "confidentiality:owner-a"]
    )
    schema = schema_bundle()["participant-boundary-flow-policy-v1"]
    Draft202012Validator(schema).validate(payload)
    with pytest.raises(ValueError, match="exact published"):
        ParticipantBoundaryFlowPolicyProfileModel.model_validate(payload)
    assert load_participant_boundary_flow_policy_profile(original.profile_id) == original
