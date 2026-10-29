"""Authored aliases cannot bypass a compiled participant visibility policy."""

from dataclasses import replace

import pytest
import yaml
from raes import parse_sdl
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    ParticipantActionResult,
    ParticipantActionResultStatus,
    iter_participant_behavior_history_violations,
)
from raes_processor.models.behavior_grounding_checks import _participant_behavior_outcome_provenance_ref_violations
from raes_processor.models.behavior_ref_checks import (
    _participant_behavior_action_result_visible_ref_violations,
    _participant_behavior_attribution_visibility_candidate_violations,
    _participant_behavior_evidence_ref_violations,
    _participant_behavior_initial_view_relation,
    _participant_behavior_visibility_detail_violations,
)
from test_sem_211_participant_action_semantics import (
    ACTION_ADDRESS,
    ACTION_INSTANCE,
    OBSERVATION_ADDRESS,
    PARTICIPANT_ADDRESS,
    _declared_effects,
    _history_payloads_for_action_result,
    _satisfied_preconditions,
    _scenario_with_hidden_action_result_ref,
)
from test_sem_211_participant_action_semantics import (
    _scenario_yaml as action_scenario,
)
from test_sem_212_participant_attribution_semantics import _attribution_edge
from test_sem_215_participant_outcome_interpretation import (
    _history_payloads,
    _outcome_record,
)
from test_sem_215_participant_outcome_interpretation import (
    _scenario_yaml as outcome_scenario,
)

AUTHORED = "nodes.web"
CANONICAL = "provision.node.web"


def _boundary(disposition, *, ambiguous=False):
    document = yaml.safe_load(action_scenario())
    boundary = document["observation_boundaries"]["red-view"]
    boundary["view_transitions"] = []
    boundary["hidden_refs"] = [AUTHORED] if disposition == "hidden" else []
    boundary["observable_refs"] = [] if disposition == "hidden" else [AUTHORED]
    boundary["view_rules"][0]["disposition"] = disposition
    if ambiguous:
        document["content"] = {"web": {"type": "file", "target": "web", "path": "/synthetic"}}
    return compile_runtime_model(parse_sdl(yaml.safe_dump(document))).observation_boundaries[OBSERVATION_ADDRESS]


def _violations(channel, boundary, ref):
    common = dict(
        locator="history",
        boundary=boundary,
        relation=_participant_behavior_initial_view_relation(boundary),
        effective_order=-1,
    )
    if channel == "result":
        return _participant_behavior_action_result_visible_ref_violations(
            **common, owner_label="effect", field_name="target_ref", refs=(ref,)
        )
    if channel == "attribution":
        edge = _attribution_edge(effect_ref=ref)
        return _participant_behavior_attribution_visibility_candidate_violations(
            **common, edge=edge, candidate=edge.effect_candidate
        )
    if channel == "provenance":
        return _participant_behavior_outcome_provenance_ref_violations(**common, record=_outcome_record(), refs=(ref,))
    return _participant_behavior_visibility_detail_violations(
        **common, detail_refs={"visible_refs": (ref,), "disclosed_refs": (), "evidence_refs": ()}
    )


@pytest.mark.parametrize("channel", ("result", "attribution", "provenance", "details"))
@pytest.mark.parametrize("ref", (AUTHORED, CANONICAL, "web"))
def test_every_history_channel_rejects_hidden_declaration_aliases(channel, ref):
    assert _violations(channel, _boundary("hidden"), ref)


@pytest.mark.parametrize("channel", ("result", "attribution", "provenance", "details"))
@pytest.mark.parametrize("ref", (AUTHORED, CANONICAL, "web"))
def test_every_history_channel_accepts_visible_declaration_aliases(channel, ref):
    assert _violations(channel, _boundary("observable"), ref) == []


@pytest.mark.parametrize("channel", ("result", "attribution", "provenance", "details"))
def test_ambiguous_history_aliases_fail_closed(channel):
    assert _violations(channel, _boundary("observable", ambiguous=True), "web")


@pytest.mark.parametrize("channel", ("result", "attribution", "provenance", "details"))
def test_a_concealment_blocks_a_previously_visible_alias(channel):
    boundary = _boundary("observable")
    boundary = replace(
        boundary, view_relation_timeline=({"effective_order": -1, "view_relation": {CANONICAL: "concealed"}},)
    )
    assert _violations(channel, boundary, AUTHORED)


@pytest.mark.parametrize("ref", ("content.receipt", "receipt", "provision.content.receipt"))
def test_declared_evidence_aliases_remain_authorized(ref):
    document = yaml.safe_load(action_scenario())
    document["content"] = {"receipt": {"type": "file", "target": "web", "path": "/receipt"}}
    boundary = document["observation_boundaries"]["red-view"]
    boundary["evidence_refs"].append("content.receipt")
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(document)))
    boundary = model.observation_boundaries[OBSERVATION_ADDRESS]
    assert (
        _participant_behavior_evidence_ref_violations(
            locator="history",
            refs=(ref,),
            boundary=boundary,
            relation=_participant_behavior_initial_view_relation(boundary),
            effective_order=-1,
        )
        == []
    )


def test_hidden_authored_effect_targets_and_support_refs_fail_full_history_validation():
    source = _scenario_with_hidden_action_result_ref().replace("content.private-answer-key", "nodes.web.services.http")
    model = compile_runtime_model(parse_sdl(source))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=_declared_effects(),
    )
    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads_for_action_result(result),
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
        )
    )
    messages = [message for _, message in violations]
    assert any("support_ref 'nodes.web.services.http' is not participant-visible" in message for message in messages)
    assert any("target_ref 'nodes.web.services.http' is not participant-visible" in message for message in messages)


def test_hidden_authored_provenance_fails_full_history_validation():
    source = (
        outcome_scenario()
        .replace("content.private-answer-key", AUTHORED)
        .replace("provenance_refs: [provenance.scaffold.standard]", "provenance_refs: [nodes.web]", 1)
    )
    model = compile_runtime_model(parse_sdl(source))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"][2]["provenance_refs"] = [AUTHORED]
    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )
    assert any("provenance_ref 'nodes.web' exposes a hidden" in message for _, message in violations)
