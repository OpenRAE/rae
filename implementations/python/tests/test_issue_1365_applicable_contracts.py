"""API-424 applicability amendment contract witnesses; no runtime adoption claim."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import (
    context_payload,
    effect_payload,
    evaluation_payload,
    ref,
    selection_payload,
)


def _selection_v2():
    source = selection_payload()
    source["schema_version"] = "participant-control-selection/v2"
    source["interpretation"] = "participant-control-applicability/rev1"
    source["bindings"][0]["protocol_revision"] = "participant-control-provider/v2"
    source["bindings"][0]["state_scope"] = {
        "scope_id": "state-influence",
        "sharing": "participant",
        "authority": source["bindings"][0]["authority"],
        "configuration_digest": source["bindings"][0]["configuration_digest"],
    }
    source["slots"] = source["slots"][:1]
    other = deepcopy(source["bindings"][0])
    other["instance_id"] = "other"
    other["applicability"][0]["sink_ref"] = "other-sink"
    other["state_scope"]["scope_id"] = "state-other"
    source["bindings"].append(other)
    source["slots"].append({**source["slots"][0], "slot_id": "other-fact", "instance_id": "other"})
    source["obligations"] = [
        {
            "obligation_id": "teaching-here",
            "profile": source["bindings"][0]["profiles"][0],
            "required_kind": "ifc-fact",
            "required_strength": "exact",
            "constraints": [],
        },
        {
            "obligation_id": "teaching-there",
            "profile": source["bindings"][0]["profiles"][0],
            "required_kind": "ifc-fact",
            "required_strength": "exact",
            "constraints": [],
        },
    ]
    return source


def _request_v2():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlSelectionV2Model,
        control_digest,
    )

    selection = ParticipantControlSelectionV2Model.model_validate(_selection_v2())
    context = context_payload()
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel

    cut = ParticipantControlContextModel.model_validate(context)
    request = {
        "selection": selection.model_dump(mode="json"),
        "context": context,
        "applicability": {
            "selection_digest": control_digest(selection),
            "context_digest": control_digest(cut),
            "applicable_slot_ids": ["fact"],
            "required_slot_ids": ["fact"],
            "coverage": [
                {
                    "obligation_id": "teaching-here",
                    "status": "applies",
                    "slot_ids": ["fact"],
                    "evidence": [ref("coverage-here")],
                },
                {
                    "obligation_id": "teaching-there",
                    "status": "proven-inapplicable",
                    "slot_ids": [],
                    "evidence": [ref("coverage-there")],
                },
            ],
            "derivation_evidence": [ref("subset-derivation")],
        },
    }
    return request


def test_disjoint_sinks_retain_full_apparatus_and_coverage():
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model

    request = ParticipantControlRequestV2Model.model_validate(_request_v2())
    assert len(request.selection.bindings) == 2
    assert request.applicability.applicable_slot_ids == ("fact",)


def test_missing_required_obligation_cannot_become_empty_success():
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model

    request = _request_v2()
    request["applicability"]["coverage"].pop()
    with pytest.raises(ValueError, match="coverage"):
        ParticipantControlRequestV2Model.model_validate(request)


def test_applicable_obligation_requires_admitted_slot():
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model

    request = _request_v2()
    request["applicability"]["coverage"][0]["slot_ids"] = []
    with pytest.raises(ValueError, match="coverage"):
        ParticipantControlRequestV2Model.model_validate(request)


def test_coverage_slot_must_belong_to_its_obligation_profile():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel
    from raes_contracts.contracts.participant_flow_control import PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST

    payload = _request_v2()
    other_profile = ref("participant-boundary-flow-policy-v1", "profile")
    other_profile["digest"] = PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST
    payload["selection"]["bindings"][1]["profiles"] = [other_profile]
    payload["selection"]["bindings"][1]["applicability"][0]["sink_ref"] = "teaching-observation"
    payload["context"]["provider_states"].append(
        {"instance_id": "other", "state": ref("state-other", "provider-state")}
    )
    payload["applicability"]["applicable_slot_ids"] = ["fact", "other-fact"]
    payload["applicability"]["required_slot_ids"] = ["fact", "other-fact"]
    payload["applicability"]["coverage"][1].update(status="applies", slot_ids=["other-fact"])
    payload["applicability"]["selection_digest"] = control_digest(
        ParticipantControlSelectionV2Model.model_validate(payload["selection"])
    )
    payload["applicability"]["context_digest"] = control_digest(
        ParticipantControlContextModel.model_validate(payload["context"])
    )
    with pytest.raises(ValueError, match="profile"):
        ParticipantControlRequestV2Model.model_validate(payload)


def test_total_proven_inapplicability_can_have_empty_applicable_subset():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel

    request = _request_v2()
    request["context"]["provider_states"] = []
    request["applicability"]["context_digest"] = control_digest(
        ParticipantControlContextModel.model_validate(request["context"])
    )
    request["applicability"]["applicable_slot_ids"] = []
    request["applicability"]["required_slot_ids"] = []
    for coverage in request["applicability"]["coverage"]:
        coverage["status"] = "proven-inapplicable"
        coverage["slot_ids"] = []
    assert ParticipantControlRequestV2Model.model_validate(request).applicability.applicable_slot_ids == ()


def _dependency_chain():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel

    request = _request_v2()
    selection = request["selection"]
    selection["bindings"][1]["applicability"][0]["sink_ref"] = "teaching-observation"
    selection["slots"] = [
        selection["slots"][0],
        {
            "slot_id": "assessment",
            "instance_id": "other",
            "kind": "advisory",
            "role": "advisory",
            "dependencies": [{"slot_id": "fact", "kind": "ifc-fact"}],
        },
        {
            "slot_id": "rule",
            "instance_id": "influence",
            "kind": "decision",
            "role": "mandatory",
            "dependencies": [{"slot_id": "assessment", "kind": "advisory"}],
        },
    ]
    selection["obligations"][1]["required_kind"] = "decision"
    request["context"]["provider_states"].append(
        {"instance_id": "other", "state": ref("state-other", "provider-state")}
    )
    request["applicability"]["coverage"][1] = {
        "obligation_id": "teaching-there",
        "status": "applies",
        "slot_ids": ["rule"],
        "evidence": [ref("coverage-there")],
    }
    request["applicability"]["applicable_slot_ids"] = ["fact", "assessment", "rule"]
    request["applicability"]["required_slot_ids"] = ["fact", "assessment", "rule"]
    selected = ParticipantControlSelectionV2Model.model_validate(selection)
    request["applicability"]["selection_digest"] = control_digest(selected)
    request["applicability"]["context_digest"] = control_digest(
        ParticipantControlContextModel.model_validate(request["context"])
    )
    return request


def _chain_records(request):
    from raes_contracts.contracts.participant_control_applicability import control_digest

    selection = request.selection
    context = request.context
    binding = {item.instance_id: item for item in selection.bindings}
    cut_digest = control_digest(context)
    facts = {
        "fact": {
            "kind": "ifc-fact",
            "domain": "teaching-influence-domain/rev1",
            "tokens": ["coached-hint"],
            "source_refs": [ref("observation-1", "input")],
        },
        "assessment": {
            "kind": "advisory",
            "assessment": "negative",
            "score": 0.2,
            "sample": ref("assessment-sample"),
        },
        "rule": {"kind": "decision", "disposition": "permit", "rule": ref("decision-rule", "rule")},
    }
    instances = {"fact": "influence", "assessment": "other", "rule": "influence"}
    kinds = {"fact": "ifc-fact", "assessment": "advisory", "rule": "decision"}
    invocations, results = [], []
    for slot_id, predecessor in (("fact", None), ("assessment", "fact"), ("rule", "assessment")):
        instance = instances[slot_id]
        inputs = []
        if predecessor:
            inputs.append(
                {
                    "slot_id": predecessor,
                    "kind": kinds[predecessor],
                    "result_id": "result-" + predecessor,
                    "result_digest": control_digest(results[-1]),
                }
            )
        invocation = {
            "invocation_id": "invoke-" + slot_id,
            "instance_id": instance,
            "requested_slot_ids": [slot_id],
            "binding_digest": control_digest(binding[instance]),
            "context_digest": cut_digest,
            "predecessor_inputs": inputs,
            "state_input": {
                "scope": binding[instance].state_scope.model_dump(mode="json"),
                "state": next(
                    s.state.model_dump(mode="json") for s in context.provider_states if s.instance_id == instance
                ),
                "source": "committed",
                "predecessor_invocation_id": None,
            },
            "projection": ref("input-projection", "projection"),
        }
        invocations.append(invocation)
        from raes_contracts.contracts.participant_control_invocation import ControlInvocationV2Model

        result = {
            "result_id": "result-" + slot_id,
            "slot_id": slot_id,
            "instance_id": instance,
            "binding_digest": invocation["binding_digest"],
            "context_digest": cut_digest,
            "invocation_digest": control_digest(ControlInvocationV2Model.model_validate(invocation)),
            "status": "resolved",
            "payload": facts[slot_id],
            "evidence": [ref("result-evidence")],
            "next_provider_state": None,
        }
        from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model

        results.append(ControlMechanismResultV2Model.model_validate(result))
    return invocations, results


def test_a_to_b_to_a_uses_exact_predecessor_results_and_pinned_state():
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model
    from raes_contracts.contracts.participant_control_invocation import validate_control_invocations_v2

    request = ParticipantControlRequestV2Model.model_validate(_dependency_chain())
    invocations, results = _chain_records(request)
    validate_control_invocations_v2(request, invocations, results)
    broken = deepcopy(invocations)
    broken[2]["predecessor_inputs"][0]["result_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="predecessor"):
        validate_control_invocations_v2(request, broken, results)
    wrong_state = deepcopy(invocations)
    wrong_state[2]["state_input"]["state"] = ref("wrong-state", "provider-state")
    with pytest.raises(ValueError, match="state version"):
        validate_control_invocations_v2(request, wrong_state, results)


def test_dependency_cannot_be_satisfied_within_one_invocation():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_invocation import validate_control_invocations_v2

    source = _dependency_chain()
    source["selection"]["slots"][2]["dependencies"] = [{"slot_id": "fact", "kind": "ifc-fact"}]
    source["applicability"]["required_slot_ids"] = ["fact", "rule"]
    source["applicability"]["selection_digest"] = control_digest(
        ParticipantControlSelectionV2Model.model_validate(source["selection"])
    )
    request = ParticipantControlRequestV2Model.model_validate(source)
    invocations, results = _chain_records(request)
    combined = deepcopy(invocations)
    combined[0]["requested_slot_ids"] = ["fact", "rule"]
    combined[0]["predecessor_inputs"] = deepcopy(combined[1]["predecessor_inputs"])
    combined.pop()
    with pytest.raises(ValueError, match="same invocation"):
        validate_control_invocations_v2(request, combined, results)


@pytest.mark.parametrize("phase", ["required-predecessor", "success-dependent", "independent"])
def test_parent_denial_is_invariant_across_effect_phases(phase):
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2

    effect = effect_payload()
    effect.update(
        phase=phase,
        parent_outcome="applied" if phase == "success-dependent" else "none",
        allowed_parent_dispositions=["deny", "withhold", "permit"] if phase == "independent" else [],
        originating_principal_ref="teacher",
        trigger=ref("trigger-1", "trigger"),
    )
    result = derive_control_effect_plan_v2(
        parent_crossing=ref("crossing-1", "crossing"),
        decisions=[
            {
                "decision_id": "deny-rule",
                "disposition": "deny",
                "rule": ref("deny-rule", "rule"),
                "reasons": [ref("denial-reason")],
            }
        ],
        effects=[effect],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    assert result.parent_disposition == "deny"
    assert result.runnable_effect_ids == (("effect-1",) if phase == "independent" else ())


def test_independent_audit_can_follow_denial_without_releasing_parent():
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2

    effect = effect_payload(
        {
            "kind": "audit",
            "subject": context_payload()["subject"],
            "audit_record": ref("audit-1", "audit"),
            "audience_ref": "reviewers",
            "retention_policy": ref("retention", "policy"),
        }
    )
    effect.update(
        phase="independent",
        parent_outcome="none",
        allowed_parent_dispositions=["deny"],
        originating_principal_ref="teacher",
        trigger=ref("trigger-1", "trigger"),
    )
    plan = derive_control_effect_plan_v2(
        parent_crossing=ref("crossing-1", "crossing"),
        decisions=[
            {
                "decision_id": "deny-rule",
                "disposition": "deny",
                "rule": ref("deny-rule", "rule"),
                "reasons": [ref("denial-reason")],
            }
        ],
        effects=[effect],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    assert plan.parent_disposition == "deny"
    assert plan.runnable_effect_ids == ("effect-1",)


def test_required_predecessor_cannot_wait_for_own_parent_application():
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2

    effect = effect_payload()
    effect.update(
        phase="required-predecessor",
        parent_outcome="applied",
        allowed_parent_dispositions=[],
        originating_principal_ref="teacher",
        trigger=ref("trigger-1", "trigger"),
    )
    with pytest.raises(ValueError, match="cycle|predecessor"):
        derive_control_effect_plan_v2(
            parent_crossing=ref("crossing-1", "crossing"),
            decisions=[],
            effects=[effect],
            incumbent_gate_disposition="permit",
            realized_effect_ids=(),
            parent_applied=False,
        )


def test_later_effect_requires_exact_parent_owner_receipt():
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2

    effect = effect_payload()
    effect.update(
        phase="success-dependent",
        parent_outcome="applied",
        allowed_parent_dispositions=[],
        originating_principal_ref="teacher",
        trigger=ref("trigger-1", "trigger"),
    )
    with pytest.raises(ValueError, match="receipt"):
        derive_control_effect_plan_v2(
            parent_crossing=ref("crossing-1", "crossing"),
            decisions=[],
            effects=[effect],
            incumbent_gate_disposition="permit",
            realized_effect_ids=(),
            parent_applied=True,
        )


def test_conflicting_routes_cannot_be_admitted_by_array_order():
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2

    source = context_payload()["subject"]
    effects = []
    for index in (1, 2):
        result = deepcopy(source)
        result["subject_ref"] = "routed-" + str(index)
        effect = effect_payload(
            {
                "kind": "route",
                "transformation": ref("route-rule", "transformation"),
                "source": source,
                "result": result,
                "destination_ref": "destination-" + str(index),
                "admission_policy": ref("route-policy", "policy"),
            }
        )
        effect.update(
            effect_id="effect-" + str(index),
            phase="independent",
            parent_outcome="none",
            allowed_parent_dispositions=["permit"],
            originating_principal_ref="teacher",
            trigger=ref("trigger-1", "trigger"),
        )
        effect["key"]["slot"] = "route-" + str(index)
        effects.append(effect)
    with pytest.raises(ValueError, match="conflict"):
        derive_control_effect_plan_v2(
            parent_crossing=ref("crossing-1", "crossing"),
            decisions=[],
            effects=effects,
            incumbent_gate_disposition="permit",
            realized_effect_ids=(),
            parent_applied=False,
        )


def _optional_request():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlSelectionV2Model,
        control_digest,
    )

    request = _request_v2()
    request["selection"]["slots"].append(
        {"slot_id": "monitor", "instance_id": "influence", "kind": "advisory", "role": "advisory", "dependencies": []}
    )
    selected = ParticipantControlSelectionV2Model.model_validate(request["selection"])
    request["applicability"]["selection_digest"] = control_digest(selected)
    request["applicability"]["applicable_slot_ids"] = ["fact", "monitor"]
    return request


def test_optional_malformed_result_is_normalized_without_private_error_text():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        normalize_optional_result_failure_v2,
    )

    request = ParticipantControlRequestV2Model.model_validate(_optional_request())
    binding = request.selection.bindings[0]
    invocation = ControlInvocationV2Model(
        invocation_id="invoke-monitor",
        instance_id="influence",
        requested_slot_ids=("monitor",),
        binding_digest=control_digest(binding),
        context_digest=control_digest(request.context),
        predecessor_inputs=(),
        state_input={
            "scope": binding.state_scope,
            "state": request.context.provider_states[0].state,
            "source": "committed",
            "predecessor_invocation_id": None,
        },
        projection=ref("input-projection", "projection"),
    )
    raw = {"slot_id": "monitor", "payload": {"secret": "private-token-do-not-disclose"}}
    result, loss = normalize_optional_result_failure_v2(
        request, invocation, raw, result_id="result-monitor", evidence=ref("optional-loss")
    )
    assert result.status == "failed" and result.payload is None and result.next_provider_state is None
    assert loss.slot_id == "monitor"
    assert "private-token" not in repr(result) + repr(loss)
    with pytest.raises(ValueError, match="mandatory"):
        normalize_optional_result_failure_v2(
            request,
            invocation.model_copy(update={"requested_slot_ids": ("fact",)}),
            raw,
            result_id="result-fact",
            evidence=ref("mandatory-loss"),
        )


def test_required_support_is_compared_to_admitted_strength():
    from raes_contracts.contracts.participant_control_support_v2 import ControlSupportAssessmentV2Model

    observed = evaluation_payload()["support"][0]
    observed["declared_level"] = "bounded"
    observed["effective_level"] = "bounded"
    observed["constraints"] = [ref("one-unit", "constraint")]
    with pytest.raises(ValueError, match="exact"):
        ControlSupportAssessmentV2Model(
            obligation_id="teaching-here",
            instance_id="influence",
            required_strength="exact",
            required_constraints=(),
            effective_support=observed,
            relation="bounded-compatible",
            evidence=(ref("support-relation"),),
        )
    assessment = ControlSupportAssessmentV2Model(
        obligation_id="teaching-here",
        instance_id="influence",
        required_strength="bounded",
        required_constraints=(ref("two-units", "constraint"),),
        effective_support=observed,
        relation="bounded-compatible",
        evidence=(ref("support-relation"),),
    )
    assert assessment.satisfied


def test_required_input_support_cannot_downgrade_its_admitted_slot_pin():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectPlanV2Model
    from raes_contracts.contracts.participant_control_evaluation_v2 import derive_control_composition_v2

    record = _evaluation_v2()
    selection = record["request"]["selection"]
    selection["slots"][1]["required_strength"] = "bounded"
    selection["slots"][1]["constraints"] = [ref("two-units", "constraint")]
    record["request"]["applicability"]["selection_digest"] = control_digest(
        ParticipantControlSelectionV2Model.model_validate(selection)
    )
    request = ParticipantControlRequestV2Model.model_validate(record["request"])
    with pytest.raises(ValueError, match="support"):
        derive_control_composition_v2(
            request,
            record["results"],
            record["support"],
            [],
            ControlEffectPlanV2Model.model_validate(record["effect_plan"]),
        )


def test_false_trigger_is_distinct_from_missing_rule_result():
    from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model

    record = evaluation_payload()["results"][1]
    record["invocation_digest"] = "sha256:" + "b" * 64
    record["payload"] = None
    record["rule_outcome"] = "not-triggered"
    record["evaluated_basis"] = [ref("false-trigger-basis")]
    result = ControlMechanismResultV2Model.model_validate(record)
    assert result.status == "resolved" and result.rule_outcome == "not-triggered"
    record["status"] = "missing"
    with pytest.raises(ValueError, match="trigger|resolved"):
        ControlMechanismResultV2Model.model_validate(record)


def test_shared_state_conflict_and_declared_tentative_chain():
    from raes_contracts.contracts.participant_control_evaluation_v2 import validate_state_proposals_v2

    scope = _selection_v2()["bindings"][0]["state_scope"]
    first = {
        "invocation_id": "invoke-fact",
        "scope": scope,
        "before": ref("state-1", "provider-state"),
        "after": ref("state-2", "provider-state"),
        "commit_on": "evaluation",
        "predecessor_invocation_id": None,
    }
    second = {
        **first,
        "invocation_id": "invoke-rule",
        "after": ref("state-3", "provider-state"),
    }
    with pytest.raises(ValueError, match="state conflict"):
        validate_state_proposals_v2([first, second])
    second["before"] = first["after"]
    second["predecessor_invocation_id"] = "invoke-fact"
    validate_state_proposals_v2([second, first])


def test_rejected_commit_cannot_expose_dispatchable_effects():
    from raes_contracts.contracts.participant_control_evaluation_v2 import ControlCommitBoundaryV2Model

    record = {
        "expected_history_heads": [ref("history-head", "history")],
        "coverage_digest": "sha256:" + "a" * 64,
        "result_digests": ["sha256:" + "b" * 64],
        "decision_digest": "sha256:" + "c" * 64,
        "state_proposal_digests": [],
        "effect_intent_digests": ["sha256:" + "d" * 64],
        "effects_consumed": 1,
        "status": "rejected",
        "receipt": None,
        "dispatchable_effect_ids": ["effect-1"],
    }
    with pytest.raises(ValueError, match="dispatch"):
        ControlCommitBoundaryV2Model.model_validate(record)
    record["dispatchable_effect_ids"] = []
    ControlCommitBoundaryV2Model.model_validate(record)


def test_denied_parent_cannot_commit_release_conditioned_state():
    import json

    from raes_contracts.contracts.participant_control_applicability import control_digest
    from raes_contracts.contracts.participant_control_evaluation_v2 import (
        ControlStateProposalV2Model,
        ParticipantControlEvaluationV2Model,
    )
    from raes_contracts.corpus import corpus_family_root

    path = (
        corpus_family_root("fixtures")
        / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
    )
    record = json.loads(path.read_text())
    proposal = ControlStateProposalV2Model(
        invocation_id="invoke-fact",
        scope=record["request"]["selection"]["bindings"][0]["state_scope"],
        before=record["invocations"][0]["state_input"]["state"],
        after=ref("state-2", "provider-state"),
        commit_on="parent-release",
        predecessor_invocation_id=None,
    )
    record["results"][0]["next_provider_state"] = proposal.after.model_dump(mode="json")
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        ControlMechanismResultV2Model,
    )

    by_slot = {item["slot_id"]: item for item in record["results"]}
    for call in record["invocations"]:
        for predecessor in call["predecessor_inputs"]:
            predecessor["result_digest"] = control_digest(
                ControlMechanismResultV2Model.model_validate(by_slot[predecessor["slot_id"]])
            )
        by_slot[call["requested_slot_ids"][0]]["invocation_digest"] = control_digest(
            ControlInvocationV2Model.model_validate(call)
        )
    record["commit"]["result_digests"] = [
        control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in record["results"]
    ]
    record["state_proposals"] = [proposal.model_dump(mode="json")]
    record["commit"]["state_proposal_digests"] = [control_digest(proposal)]
    record["commit"]["status"] = "committed"
    record["commit"]["receipt"] = ref("commit-receipt", "receipt")
    with pytest.raises(ValueError, match="parent-release state cannot commit for a refused parent"):
        ParticipantControlEvaluationV2Model.model_validate(record)
    proposal = proposal.model_copy(update={"commit_on": "evaluation"})
    record["state_proposals"] = [proposal.model_dump(mode="json")]
    record["commit"]["state_proposal_digests"] = [control_digest(proposal)]
    accepted = ParticipantControlEvaluationV2Model.model_validate(record)
    from dataclasses import replace

    from participant_control_contract_fixtures import crossing_payload
    from raes_contracts.contracts.participant_control_resolution import (
        ParticipantControlValidationContextV2,
        control_references,
        validate_participant_control_resolved_context_v2,
    )
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel

    crossing = ParticipantCrossingOccurrenceModel.model_validate(
        crossing_payload(accepted.request.context.model_dump(mode="json"))
    )
    trusted = ParticipantControlValidationContextV2(
        admitted_request=accepted.request,
        admitted_crossing=accepted.request.context.crossing,
        installed_bindings={item.instance_id: item for item in accepted.request.selection.bindings},
        resolved_coverage={item.obligation_id: item for item in accepted.request.applicability.coverage},
        resolved_results={item.slot_id: item for item in accepted.results},
        resolved_support={(item.obligation_id, item.instance_id): item for item in accepted.support},
        authorized_effects={control_digest(item): accepted.request.context for item in accepted.effect_plan.effects},
        safe_references=frozenset(control_references(accepted)),
        support_resolver=lambda item: True,
        incumbent_gate_disposition=accepted.effect_plan.incumbent_gate_disposition,
        crossing_records=(crossing,),
        crossing_subjects=(crossing.occurrence.subject,),
        crossing_policies=(crossing.occurrence.policy,),
        commit_receipt=accepted.commit.receipt,
    )
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(accepted, lambda _: trusted)
    validate_participant_control_resolved_context_v2(
        accepted, lambda _: replace(trusted, authorized_state_proposals={proposal.invocation_id: proposal})
    )
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(
            accepted,
            lambda _: replace(
                trusted,
                authorized_state_proposals={
                    proposal.invocation_id: proposal.model_copy(update={"commit_on": "parent-release"})
                },
            ),
        )


def test_new_effect_cannot_exceed_retained_causal_budget():
    import json

    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectPlanV2Model
    from raes_contracts.contracts.participant_control_evaluation_v2 import validate_effect_budget_v2
    from raes_contracts.contracts.participant_control_selection import ControlCausalBoundsModel
    from raes_contracts.corpus import corpus_family_root

    record = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )
    context = ParticipantControlContextModel.model_validate(record["request"]["context"])
    bounds = ControlCausalBoundsModel.model_validate(record["request"]["selection"]["bounds"])
    plan = ControlEffectPlanV2Model.model_validate(record["effect_plan"])
    validate_effect_budget_v2(context, bounds, plan)
    limited = context.model_copy(update={"effects_consumed": bounds.max_effects})
    with pytest.raises(ValueError, match="budget"):
        validate_effect_budget_v2(limited, bounds, plan)


def test_v2_effect_admission_rejects_lifecycle_before_live_target_and_foreign_root():
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
    from raes_contracts.contracts.participant_control_evaluation_v2 import validate_effect_budget_v2
    from raes_contracts.contracts.participant_control_selection import ControlCausalBoundsModel

    context = ParticipantControlContextModel.model_validate(context_payload())
    bounds = ControlCausalBoundsModel.model_validate(selection_payload()["bounds"])
    lifecycle = effect_payload(
        {
            "kind": "shutdown",
            "target_kind": "participant",
            "target_ref": "participants.student",
            "operation": "terminate",
            "lifecycle_authority": ref("lifecycle", "authority"),
            "expected_revision": "rev1",
        }
    )
    inject = effect_payload()
    inject["effect_id"] = "effect-2"
    inject["key"]["slot"] = "second"
    inject["predecessor_effect_ids"] = ["effect-1"]
    for effect in (lifecycle, inject):
        effect.update(
            phase="independent",
            parent_outcome="none",
            allowed_parent_dispositions=["permit"],
            originating_principal_ref="teacher",
            trigger=ref("trigger-1", "trigger"),
        )
    plan = derive_control_effect_plan_v2(
        parent_crossing=context.crossing,
        decisions=[],
        effects=[lifecycle, inject],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    with pytest.raises(ValueError, match="lifecycle"):
        validate_effect_budget_v2(context, bounds, plan)
    inject["predecessor_effect_ids"] = []
    unordered_plan = derive_control_effect_plan_v2(
        parent_crossing=context.crossing,
        decisions=[],
        effects=[lifecycle, inject],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    with pytest.raises(ValueError, match="lifecycle"):
        validate_effect_budget_v2(context, bounds, unordered_plan)
    lifecycle["predecessor_effect_ids"] = ["effect-2"]
    safe_plan = derive_control_effect_plan_v2(
        parent_crossing=context.crossing,
        decisions=[],
        effects=[lifecycle, inject],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    validate_effect_budget_v2(context, bounds, safe_plan)
    foreign = deepcopy(inject)
    foreign["predecessor_effect_ids"] = []
    foreign["key"]["trigger_root"] = "different-root"
    foreign_plan = derive_control_effect_plan_v2(
        parent_crossing=context.crossing,
        decisions=[],
        effects=[foreign],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    with pytest.raises(ValueError, match="causal root"):
        validate_effect_budget_v2(context, bounds, foreign_plan)


def test_consumed_tentative_state_requires_transaction_proposal():
    from raes_contracts.contracts.participant_control_applicability import control_digest
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        ControlMechanismResultV2Model,
    )

    payload = _evaluation_v2()
    payload["results"][0]["next_provider_state"] = ref("state-next", "provider-state")
    payload["invocations"][2]["state_input"].update(
        source="tentative",
        state=ref("state-next", "provider-state"),
        predecessor_invocation_id="invoke-fact",
    )
    by_slot = {item["slot_id"]: item for item in payload["results"]}
    for call in payload["invocations"]:
        for predecessor in call["predecessor_inputs"]:
            predecessor["result_digest"] = control_digest(
                ControlMechanismResultV2Model.model_validate(by_slot[predecessor["slot_id"]])
            )
        invocation = ControlInvocationV2Model.model_validate(call)
        by_slot[call["requested_slot_ids"][0]]["invocation_digest"] = control_digest(invocation)
    payload["commit"]["result_digests"] = [
        control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in payload["results"]
    ]
    with pytest.raises(ValueError, match="tentative state.*transaction proposal"):
        ParticipantControlEvaluationV2Model.model_validate(payload)


def _evaluation_v2():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
    from raes_contracts.contracts.participant_control_evaluation_v2 import derive_control_composition_v2

    request = ParticipantControlRequestV2Model.model_validate(_dependency_chain())
    invocations, results = _chain_records(request)
    support = []
    for requirement_id, instance in (
        ("teaching-here", "influence"),
        ("teaching-there", "influence"),
        ("input:assessment", "other"),
    ):
        observed = evaluation_payload()["support"][0]
        observed["instance_id"] = instance
        observed["context_digest"] = control_digest(request.context)
        support.append(
            {
                "obligation_id": requirement_id,
                "instance_id": instance,
                "required_strength": "exact",
                "required_constraints": [],
                "effective_support": observed,
                "relation": "exact",
                "evidence": [ref("support-relation")],
            }
        )
    plan = derive_control_effect_plan_v2(
        parent_crossing=request.context.crossing,
        decisions=[
            {
                "decision_id": "result-rule",
                "disposition": "permit",
                "rule": ref("decision-rule", "rule"),
                "reasons": [ref("decision-basis")],
            }
        ],
        effects=[],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    composition = derive_control_composition_v2(request, results, support, [], plan)
    return {
        "schema_version": "participant-control-evaluation/v2",
        "evaluation_id": "evaluation-v2",
        "request": request.model_dump(mode="json"),
        "invocations": invocations,
        "results": [item.model_dump(mode="json") for item in results],
        "support": support,
        "lost_advice": [],
        "effect_plan": plan.model_dump(mode="json"),
        "state_proposals": [],
        "composition": composition.model_dump(mode="json"),
        "commit": {
            "expected_history_heads": [item.model_dump(mode="json") for item in request.context.expected_history_heads],
            "coverage_digest": control_digest(request.applicability),
            "result_digests": [control_digest(item) for item in results],
            "decision_digest": control_digest(plan),
            "state_proposal_digests": [],
            "effect_intent_digests": [],
            "effects_consumed": request.context.effects_consumed,
            "status": "prepared",
            "receipt": None,
            "dispatchable_effect_ids": [],
        },
    }


def test_evaluation_v2_requires_complete_support_and_atomic_record_bindings():
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model

    payload = _evaluation_v2()
    document = ParticipantControlEvaluationV2Model.model_validate(payload)
    assert document.composition.disposition == "eligible"
    payload["support"].pop()
    with pytest.raises(ValueError, match="support"):
        ParticipantControlEvaluationV2Model.model_validate(payload)


@pytest.mark.parametrize("status,expected", [("stale", "stale"), ("weakened", "weakened")])
def test_required_result_status_retains_its_composition_disposition(status, expected):
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model
    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectPlanV2Model
    from raes_contracts.contracts.participant_control_evaluation_v2 import derive_control_composition_v2

    payload = _evaluation_v2()
    payload["results"][-1]["status"] = status
    payload["results"][-1]["payload"] = None
    request = ParticipantControlRequestV2Model.model_validate(payload["request"])
    plan = ControlEffectPlanV2Model.model_validate(payload["effect_plan"])
    composition = derive_control_composition_v2(request, payload["results"], payload["support"], [], plan)
    assert composition.disposition == expected


def test_v1_history_cannot_be_parsed_as_amended_evaluation():
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model

    with pytest.raises(ValueError):
        ParticipantControlEvaluationV2Model.model_validate(evaluation_payload())


def test_v2_bounded_json_ingress_preserves_abstention_and_rejects_duplicate_members():
    import json

    from raes_contracts.contracts.participant_control_applicability import control_digest
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
    from raes_contracts.contracts.participant_control_evaluation_v2 import (
        derive_control_composition_v2,
        parse_participant_control_evaluation_v2,
    )
    from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model

    payload = _evaluation_v2()
    payload["results"][-1]["payload"]["disposition"] = "abstain"
    result = ControlMechanismResultV2Model.model_validate(payload["results"][-1])
    payload["commit"]["result_digests"][-1] = control_digest(result)
    plan = derive_control_effect_plan_v2(
        parent_crossing=payload["request"]["context"]["crossing"],
        decisions=[],
        effects=[],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    payload["effect_plan"] = plan.model_dump(mode="json")
    payload["commit"]["decision_digest"] = control_digest(plan)
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model

    request = ParticipantControlRequestV2Model.model_validate(payload["request"])
    payload["composition"] = derive_control_composition_v2(
        request, payload["results"], payload["support"], [], plan
    ).model_dump(mode="json")
    parsed = parse_participant_control_evaluation_v2(json.dumps(payload))
    assert parsed.results[-1].payload.disposition == "abstain"
    assert parsed.composition.disposition == "failed"
    with pytest.raises(ValueError, match="invalid participant control evaluation"):
        parse_participant_control_evaluation_v2('{"schema_version":"one","schema_version":"two"}')


def test_v2_effect_outcome_cannot_name_an_absent_effect():
    import json

    from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectPlanV2Model
    from raes_contracts.corpus import corpus_family_root

    payload = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )["effect_plan"]
    payload["effect_outcomes"] = [
        {
            "effect_id": "absent-effect",
            "disposition": "failed",
            "receipt": ref("absent-receipt", "receipt"),
            "evidence": [ref("outcome-evidence")],
        }
    ]
    with pytest.raises(ValueError, match="outcome"):
        ControlEffectPlanV2Model.model_validate(payload)


def test_v2_publication_has_exact_schema_and_separate_provider_protocol():
    import json

    from jsonschema import Draft202012Validator
    from raes_backend_protocols.protocols import ParticipantControlProviderV2
    from raes_conformance.conformance.validators import contract_validation_strength
    from raes_contracts.contracts import schema_bundle
    from raes_contracts.corpus import corpus_family_root

    bundle = schema_bundle()
    for contract_id, payload in (
        ("participant-control-selection-v2", _selection_v2()),
        ("participant-control-evaluation-v2", _evaluation_v2()),
    ):
        schema = bundle[contract_id]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        published = corpus_family_root("schemas") / "participant-runtime" / (contract_id + ".json")
        assert json.loads(published.read_text()) == schema
    assert contract_validation_strength("participant-control-evaluation-v2") == "structural-context-required"
    assert "resolve_stage" in ParticipantControlProviderV2.__dict__


def test_v2_trusted_context_rejects_unresolved_coverage_and_support():
    from participant_control_contract_fixtures import crossing_payload
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.contracts.participant_control_resolution import (
        ParticipantControlValidationContextV2,
        control_references,
        validate_participant_control_resolved_context_v2,
    )
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel

    record = ParticipantControlEvaluationV2Model.model_validate(_evaluation_v2())
    crossing = ParticipantCrossingOccurrenceModel.model_validate(
        crossing_payload(record.request.context.model_dump(mode="json"))
    )
    trusted = ParticipantControlValidationContextV2(
        admitted_request=record.request,
        admitted_crossing=record.request.context.crossing,
        installed_bindings={item.instance_id: item for item in record.request.selection.bindings},
        resolved_coverage={item.obligation_id: item for item in record.request.applicability.coverage},
        resolved_results={item.slot_id: item for item in record.results},
        resolved_support={(item.obligation_id, item.instance_id): item for item in record.support},
        authorized_effects={},
        safe_references=frozenset(control_references(record)),
        support_resolver=lambda item: True,
        incumbent_gate_disposition="permit",
        crossing_records=(crossing,),
        crossing_subjects=(crossing.occurrence.subject,),
        crossing_policies=(crossing.occurrence.policy,),
    )
    validate_participant_control_resolved_context_v2(record, lambda _: trusted)
    from raes_conformance.conformance.validators import validate_contract_payload

    assert (
        validate_contract_payload("participant-control-evaluation-v2", record.model_dump(mode="json"))[0].code
        == "conformance.semantic-context-required"
    )
    assert (
        validate_contract_payload(
            "participant-control-evaluation-v2",
            record.model_dump(mode="json"),
            control_context_resolver=lambda _: trusted,
        )
        == ()
    )
    from dataclasses import replace

    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(record, lambda _: replace(trusted, resolved_coverage={}))
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(
            record, lambda _: replace(trusted, support_resolver=lambda item: False)
        )
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(
            record, lambda _: replace(trusted, incumbent_gate_disposition="deny")
        )
    committed_payload = _evaluation_v2()
    committed_payload["commit"]["status"] = "committed"
    committed_payload["commit"]["receipt"] = ref("atomic-receipt", "receipt")
    committed = ParticipantControlEvaluationV2Model.model_validate(committed_payload)
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(committed, lambda _: trusted)
    validate_participant_control_resolved_context_v2(
        committed,
        lambda _: replace(
            trusted,
            commit_receipt=committed.commit.receipt,
            safe_references=frozenset(control_references(committed)),
        ),
    )


def test_v2_effect_authorization_binds_full_payload_and_cut():
    import json

    from participant_control_contract_fixtures import crossing_payload
    from raes_contracts.contracts.participant_control_applicability import control_digest
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.contracts.participant_control_resolution import (
        ParticipantControlValidationContextV2,
        control_references,
        validate_participant_control_resolved_context_v2,
    )
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel
    from raes_contracts.corpus import corpus_family_root

    payload = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )
    record = ParticipantControlEvaluationV2Model.model_validate(payload)
    crossing = ParticipantCrossingOccurrenceModel.model_validate(
        crossing_payload(record.request.context.model_dump(mode="json"))
    )
    assert record.effect_plan.runnable_effect_ids
    from dataclasses import replace

    trusted = ParticipantControlValidationContextV2(
        admitted_request=record.request,
        admitted_crossing=record.request.context.crossing,
        installed_bindings={item.instance_id: item for item in record.request.selection.bindings},
        resolved_coverage={item.obligation_id: item for item in record.request.applicability.coverage},
        resolved_results={item.slot_id: item for item in record.results},
        resolved_support={(item.obligation_id, item.instance_id): item for item in record.support},
        authorized_effects={control_digest(item): record.request.context for item in record.effect_plan.effects},
        safe_references=frozenset(control_references(record)),
        support_resolver=lambda item: True,
        incumbent_gate_disposition=record.effect_plan.incumbent_gate_disposition,
        crossing_records=(crossing,),
        crossing_subjects=(crossing.occurrence.subject,),
        crossing_policies=(crossing.occurrence.policy,),
    )
    validate_participant_control_resolved_context_v2(record, lambda _: trusted)
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(
            record,
            lambda _: replace(
                trusted,
                authorized_effects={item.effect_id: record.request.context for item in record.effect_plan.effects},
            ),
        )
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(
            record,
            lambda _: replace(
                trusted,
                authorized_effects={
                    control_digest(item): record.request.context.model_copy(update={"sink_ref": "different-sink"})
                    for item in record.effect_plan.effects
                },
            ),
        )


def test_realized_effect_requires_prior_committed_full_intent_and_owner_outcome():
    import json
    from dataclasses import replace

    from participant_control_contract_fixtures import crossing_payload
    from raes_contracts.contracts.participant_control_applicability import control_digest
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel
    from raes_contracts.contracts.participant_control_decisions_v2 import (
        ControlEffectRequestV2Model,
        derive_control_effect_plan_v2,
    )
    from raes_contracts.contracts.participant_control_evaluation_v2 import (
        ParticipantControlEvaluationV2Model,
        validate_effect_budget_v2,
    )
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        ControlMechanismResultV2Model,
    )
    from raes_contracts.contracts.participant_control_resolution import (
        ControlCommittedEffectIntentV2,
        ParticipantControlValidationContextV2,
        control_references,
        validate_participant_control_resolved_context_v2,
    )
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel
    from raes_contracts.corpus import corpus_family_root

    payload = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )
    effect = ControlEffectRequestV2Model.model_validate(payload["effect_plan"]["effects"][0])
    payload["commit"].update(
        status="committed",
        receipt=ref("origin-commit", "receipt"),
        dispatchable_effect_ids=[effect.effect_id],
    )
    origin = ParticipantControlEvaluationV2Model.model_validate(payload)
    current = deepcopy(payload)
    current["request"]["context"]["effects_consumed"] = 1
    current["request"]["context"]["prior_effect_claims"] = [
        {
            "effect_id": effect.effect_id,
            "key": effect.key.model_dump(mode="json"),
            "content_digest": control_digest(effect),
        }
    ]
    current["request"]["context"]["rule_firings"] = [
        {
            "rule_id": effect.key.rule_id,
            "rule_revision": effect.key.rule_revision,
            "firing_epochs": [effect.key.firing_epoch],
        }
    ]
    cut = ParticipantControlContextModel.model_validate(current["request"]["context"])
    old_digest, new_digest = control_digest(origin.request.context), control_digest(cut)
    current = json.loads(json.dumps(current).replace(old_digest, new_digest))
    current["commit"].update(
        coverage_digest=control_digest(origin.request.applicability),
        effects_consumed=1,
        status="prepared",
        receipt=None,
        dispatchable_effect_ids=[],
        effect_intent_digests=[],
    )
    current["request"]["applicability"]["context_digest"] = new_digest
    by_slot = {item["slot_id"]: item for item in current["results"]}
    for call in current["invocations"]:
        for predecessor in call["predecessor_inputs"]:
            predecessor["result_digest"] = control_digest(
                ControlMechanismResultV2Model.model_validate(by_slot[predecessor["slot_id"]])
            )
        for slot_id in call["requested_slot_ids"]:
            by_slot[slot_id]["invocation_digest"] = control_digest(ControlInvocationV2Model.model_validate(call))
    current["commit"]["result_digests"] = [
        control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in current["results"]
    ]
    outcome = {
        "effect_id": effect.effect_id,
        "disposition": "applied",
        "receipt": ref("effect-applied", "receipt"),
        "evidence": [ref("effect-owner-evidence")],
    }
    plan = derive_control_effect_plan_v2(
        parent_crossing=origin.effect_plan.parent_crossing,
        decisions=list(origin.effect_plan.decisions),
        effects=list(origin.effect_plan.effects),
        incumbent_gate_disposition=origin.effect_plan.incumbent_gate_disposition,
        realized_effect_ids=(effect.effect_id,),
        parent_applied=False,
        effect_outcomes=[outcome],
    )
    with pytest.raises(ValueError, match="retained committed intent claim"):
        validate_effect_budget_v2(origin.request.context, origin.request.selection.bounds, plan)
    current["effect_plan"] = plan.model_dump(mode="json")
    current["commit"]["decision_digest"] = control_digest(plan)
    current["commit"]["coverage_digest"] = control_digest(
        origin.request.applicability.model_copy(update={"context_digest": new_digest})
    )
    record = ParticipantControlEvaluationV2Model.model_validate(current)
    crossing = ParticipantCrossingOccurrenceModel.model_validate(crossing_payload(cut.model_dump(mode="json")))
    trusted = ParticipantControlValidationContextV2(
        admitted_request=record.request,
        admitted_crossing=cut.crossing,
        installed_bindings={item.instance_id: item for item in record.request.selection.bindings},
        resolved_coverage={item.obligation_id: item for item in record.request.applicability.coverage},
        resolved_results={item.slot_id: item for item in record.results},
        resolved_support={(item.obligation_id, item.instance_id): item for item in record.support},
        authorized_effects={control_digest(effect): origin.request.context},
        safe_references=frozenset(control_references(record)),
        support_resolver=lambda item: True,
        incumbent_gate_disposition=record.effect_plan.incumbent_gate_disposition,
        crossing_records=(crossing,),
        crossing_subjects=(crossing.occurrence.subject,),
        crossing_policies=(crossing.occurrence.policy,),
        realization_receipts={effect.effect_id: plan.effect_outcomes[0]},
    )
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(record, lambda _: trusted)
    committed = ControlCommittedEffectIntentV2(evaluation=origin, outcome=plan.effect_outcomes[0])
    validate_participant_control_resolved_context_v2(
        record, lambda _: replace(trusted, committed_effect_intents={effect.effect_id: committed})
    )
    with pytest.raises(ValueError, match="trusted-context"):
        validate_participant_control_resolved_context_v2(
            record,
            lambda _: replace(
                trusted,
                committed_effect_intents={
                    effect.effect_id: replace(
                        committed, evaluation=origin.model_copy(update={"request": record.request})
                    )
                },
            ),
        )


def test_v2_security_fact_requires_incumbent_crossing_and_flow_relation_owner():
    from dataclasses import replace

    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
    from raes_contracts.contracts.participant_control_evaluation_v2 import (
        ParticipantControlEvaluationV2Model,
        derive_control_composition_v2,
    )
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        ControlMechanismResultV2Model,
    )
    from raes_contracts.contracts.participant_control_resolution import (
        ParticipantControlValidationContextV2,
        control_references,
        validate_participant_control_resolved_context_v2,
    )
    from test_api_424_security_profile import security_record_and_context

    legacy, owner = security_record_and_context()
    selection_data = legacy.request.selection.model_dump(mode="json")
    selection_data["schema_version"] = "participant-control-selection/v2"
    selection_data["interpretation"] = "participant-control-applicability/rev1"
    binding_data = selection_data["bindings"][0]
    binding_data["protocol_revision"] = "participant-control-provider/v2"
    binding_data["state_scope"] = {
        "scope_id": "security-state",
        "sharing": "participant",
        "authority": binding_data["authority"],
        "configuration_digest": binding_data["configuration_digest"],
    }
    selection_data["obligations"] = [
        {
            "obligation_id": "security-fact",
            "profile": binding_data["profiles"][0],
            "required_kind": "ifc-fact",
            "required_strength": "exact",
            "constraints": [],
        }
    ]
    selection = ParticipantControlSelectionV2Model.model_validate(selection_data)
    cut = legacy.request.context
    request = ParticipantControlRequestV2Model.model_validate(
        {
            "selection": selection.model_dump(mode="json"),
            "context": cut.model_dump(mode="json"),
            "applicability": {
                "selection_digest": control_digest(selection),
                "context_digest": control_digest(cut),
                "applicable_slot_ids": ["fact"],
                "required_slot_ids": ["fact"],
                "coverage": [
                    {
                        "obligation_id": "security-fact",
                        "status": "applies",
                        "slot_ids": ["fact"],
                        "evidence": [ref("security-coverage")],
                    }
                ],
                "derivation_evidence": [ref("security-applicability")],
            },
        }
    )
    invocation = ControlInvocationV2Model.model_validate(
        {
            "invocation_id": "security-invocation",
            "instance_id": "influence",
            "requested_slot_ids": ["fact"],
            "binding_digest": control_digest(selection.bindings[0]),
            "context_digest": control_digest(cut),
            "predecessor_inputs": [],
            "state_input": {
                "scope": selection.bindings[0].state_scope.model_dump(mode="json"),
                "state": cut.provider_states[0].state.model_dump(mode="json"),
                "source": "committed",
                "predecessor_invocation_id": None,
            },
            "projection": ref("security-projection", "projection"),
        }
    )
    result_data = legacy.results[0].model_dump(mode="json")
    result_data.update(
        binding_digest=control_digest(selection.bindings[0]),
        context_digest=control_digest(cut),
        invocation_digest=control_digest(invocation),
    )
    result = ControlMechanismResultV2Model.model_validate(result_data)
    support = {
        "obligation_id": "security-fact",
        "instance_id": "influence",
        "required_strength": "exact",
        "required_constraints": [],
        "effective_support": legacy.support[0].model_dump(mode="json"),
        "relation": "exact",
        "evidence": [ref("security-support")],
    }
    plan = derive_control_effect_plan_v2(
        parent_crossing=cut.crossing,
        decisions=[],
        effects=[],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    composition = derive_control_composition_v2(request, [result], [support], [], plan)
    record = ParticipantControlEvaluationV2Model.model_validate(
        {
            "schema_version": "participant-control-evaluation/v2",
            "evaluation_id": "security-evaluation",
            "request": request.model_dump(mode="json"),
            "invocations": [invocation.model_dump(mode="json")],
            "results": [result.model_dump(mode="json")],
            "support": [support],
            "lost_advice": [],
            "effect_plan": plan.model_dump(mode="json"),
            "state_proposals": [],
            "composition": composition.model_dump(mode="json"),
            "commit": {
                "expected_history_heads": [item.model_dump(mode="json") for item in cut.expected_history_heads],
                "coverage_digest": control_digest(request.applicability),
                "result_digests": [control_digest(result)],
                "decision_digest": control_digest(plan),
                "state_proposal_digests": [],
                "effect_intent_digests": [],
                "effects_consumed": cut.effects_consumed,
                "status": "prepared",
                "receipt": None,
                "dispatchable_effect_ids": [],
            },
        }
    )
    trusted = ParticipantControlValidationContextV2(
        admitted_request=request,
        admitted_crossing=cut.crossing,
        installed_bindings={"influence": selection.bindings[0]},
        resolved_coverage={item.obligation_id: item for item in request.applicability.coverage},
        resolved_results={"fact": result},
        resolved_support={(item.obligation_id, item.instance_id): item for item in record.support},
        authorized_effects={},
        safe_references=frozenset(set(owner.safe_references) | set(control_references(record))),
        support_resolver=lambda item: True,
        incumbent_gate_disposition="permit",
        crossing_records=owner.crossing_records,
        crossing_subjects=owner.crossing_subjects,
        crossing_policies=owner.crossing_policies,
        flow_relations=owner.flow_relations,
        flow_contexts=owner.flow_contexts,
    )
    validate_participant_control_resolved_context_v2(record, lambda _: trusted)
    for wrong in (replace(trusted, crossing_records=()), replace(trusted, flow_contexts={})):
        with pytest.raises(ValueError, match="trusted-context"):
            validate_participant_control_resolved_context_v2(record, lambda _, wrong=wrong: wrong)


def test_failed_required_composition_cannot_commit_parent_release_state():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
    from raes_contracts.contracts.participant_control_evaluation_v2 import (
        ControlStateProposalV2Model,
        ParticipantControlEvaluationV2Model,
        derive_control_composition_v2,
    )
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        ControlMechanismResultV2Model,
    )

    payload = _evaluation_v2()
    request = ParticipantControlRequestV2Model.model_validate(payload["request"])
    payload["results"][-1].update(status="failed", payload=None)
    proposal = ControlStateProposalV2Model(
        invocation_id="invoke-fact",
        scope=request.selection.bindings[0].state_scope,
        before=request.context.provider_states[0].state,
        after=ref("failed-parent-next-state", "provider-state"),
        commit_on="parent-release",
        predecessor_invocation_id=None,
    )
    payload["results"][0]["next_provider_state"] = proposal.after.model_dump(mode="json")
    by_slot = {item["slot_id"]: item for item in payload["results"]}
    for call in payload["invocations"]:
        for predecessor in call["predecessor_inputs"]:
            predecessor["result_digest"] = control_digest(
                ControlMechanismResultV2Model.model_validate(by_slot[predecessor["slot_id"]])
            )
        by_slot[call["requested_slot_ids"][0]]["invocation_digest"] = control_digest(
            ControlInvocationV2Model.model_validate(call)
        )
    plan = derive_control_effect_plan_v2(
        parent_crossing=request.context.crossing,
        decisions=[],
        effects=[],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    payload["effect_plan"] = plan.model_dump(mode="json")
    payload["composition"] = derive_control_composition_v2(
        request, payload["results"], payload["support"], [], plan
    ).model_dump(mode="json")
    assert payload["composition"]["disposition"] == "failed"
    payload["state_proposals"] = [proposal.model_dump(mode="json")]
    payload["commit"].update(
        result_digests=[
            control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in payload["results"]
        ],
        decision_digest=control_digest(plan),
        state_proposal_digests=[control_digest(proposal)],
        status="committed",
        receipt=ref("failed-parent-commit", "receipt"),
    )
    with pytest.raises(ValueError, match="mandatory composition.*parent release"):
        ParticipantControlEvaluationV2Model.model_validate(payload)


def test_failed_required_composition_cannot_dispatch_independent_effect():
    import json

    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlRequestV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_decisions_v2 import derive_control_effect_plan_v2
    from raes_contracts.contracts.participant_control_evaluation_v2 import (
        ParticipantControlEvaluationV2Model,
        derive_control_composition_v2,
    )
    from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
    from raes_contracts.corpus import corpus_family_root

    payload = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )
    request = ParticipantControlRequestV2Model.model_validate(payload["request"])
    payload["results"][2].update(status="failed", payload=None)
    effect = payload["results"][3]["payload"]
    effect["allowed_parent_dispositions"] = ["permit"]
    plan = derive_control_effect_plan_v2(
        parent_crossing=request.context.crossing,
        decisions=[],
        effects=[effect],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    assert plan.parent_disposition == "permit" and plan.runnable_effect_ids == (effect["effect_id"],)
    payload["effect_plan"] = plan.model_dump(mode="json")
    payload["composition"] = derive_control_composition_v2(
        request, payload["results"], payload["support"], payload["lost_advice"], plan
    ).model_dump(mode="json")
    assert payload["composition"]["disposition"] == "failed"
    payload["commit"].update(
        result_digests=[
            control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in payload["results"]
        ],
        decision_digest=control_digest(plan),
        effect_intent_digests=[],
        status="committed",
        receipt=ref("failed-dispatch-commit", "receipt"),
        dispatchable_effect_ids=[effect["effect_id"]],
    )
    with pytest.raises(ValueError, match="mandatory composition.*dispatch"):
        ParticipantControlEvaluationV2Model.model_validate(payload)
    effect["allowed_parent_dispositions"] = ["deny"]
    denied_plan = derive_control_effect_plan_v2(
        parent_crossing=request.context.crossing,
        decisions=[],
        effects=[effect],
        incumbent_gate_disposition="deny",
        realized_effect_ids=(),
        parent_applied=False,
    )
    assert denied_plan.runnable_effect_ids == (effect["effect_id"],)
    payload["effect_plan"] = denied_plan.model_dump(mode="json")
    payload["composition"] = derive_control_composition_v2(
        request, payload["results"], payload["support"], payload["lost_advice"], denied_plan
    ).model_dump(mode="json")
    payload["commit"].update(
        result_digests=[
            control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in payload["results"]
        ],
        decision_digest=control_digest(denied_plan),
        effect_intent_digests=[],
    )
    with pytest.raises(ValueError, match="mandatory composition.*dispatch"):
        ParticipantControlEvaluationV2Model.model_validate(payload)
    effect["allowed_parent_dispositions"] = ["withhold"]
    withheld_plan = derive_control_effect_plan_v2(
        parent_crossing=request.context.crossing,
        decisions=[],
        effects=[effect],
        incumbent_gate_disposition="permit",
        realized_effect_ids=(),
        parent_applied=False,
    )
    assert withheld_plan.runnable_effect_ids == ()
    payload["effect_plan"] = withheld_plan.model_dump(mode="json")
    payload["composition"] = derive_control_composition_v2(
        request, payload["results"], payload["support"], payload["lost_advice"], withheld_plan
    ).model_dump(mode="json")
    payload["commit"].update(
        result_digests=[
            control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in payload["results"]
        ],
        decision_digest=control_digest(withheld_plan),
        effect_intent_digests=[],
    )
    with pytest.raises(ValueError, match="mandatory composition.*dispatch"):
        ParticipantControlEvaluationV2Model.model_validate(payload)


def test_duplicate_provider_effect_id_cannot_hide_an_earlier_request():
    import json

    from raes_contracts.contracts.participant_control_applicability import (
        ControlApplicabilityV2Model,
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.contracts.participant_control_invocation import (
        ControlInvocationV2Model,
        ControlMechanismResultV2Model,
    )
    from raes_contracts.corpus import corpus_family_root

    payload = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )
    selection = payload["request"]["selection"]
    assessment = next(item for item in selection["slots"] if item["slot_id"] == "assessment")
    assessment["kind"] = "effect-request"
    rule = next(item for item in selection["slots"] if item["slot_id"] == "rule")
    rule["dependencies"][0]["kind"] = "effect-request"
    rule_call = next(item for item in payload["invocations"] if item["requested_slot_ids"] == ["rule"])
    rule_call["predecessor_inputs"][0]["kind"] = "effect-request"
    payload["request"]["applicability"]["selection_digest"] = control_digest(
        ParticipantControlSelectionV2Model.model_validate(selection)
    )
    results = {item["slot_id"]: item for item in payload["results"]}
    collision = deepcopy(results["audit-slot"]["payload"])
    collision["key"]["slot"] = "earlier-provider"
    results["assessment"]["payload"] = collision
    for call in payload["invocations"]:
        for predecessor in call["predecessor_inputs"]:
            predecessor["result_digest"] = control_digest(
                ControlMechanismResultV2Model.model_validate(results[predecessor["slot_id"]])
            )
        for slot_id in call["requested_slot_ids"]:
            results[slot_id]["invocation_digest"] = control_digest(ControlInvocationV2Model.model_validate(call))
    payload["commit"].update(
        coverage_digest=control_digest(ControlApplicabilityV2Model.model_validate(payload["request"]["applicability"])),
        result_digests=[
            control_digest(ControlMechanismResultV2Model.model_validate(item)) for item in payload["results"]
        ],
    )
    with pytest.raises(ValueError, match="duplicate provider effect identity"):
        ParticipantControlEvaluationV2Model.model_validate(payload)


def test_independent_audit_remains_dispatchable_after_denial():
    import json

    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.corpus import corpus_family_root

    payload = json.loads(
        (
            corpus_family_root("fixtures")
            / "participant-runtime/participant-control-evaluation-v2/valid/later-phase-denial.json"
        ).read_text()
    )
    payload["commit"].update(
        status="committed",
        receipt=ref("denial-audit-commit", "receipt"),
        dispatchable_effect_ids=payload["effect_plan"]["runnable_effect_ids"],
    )
    record = ParticipantControlEvaluationV2Model.model_validate(payload)
    assert record.composition.disposition == "deny"
    assert record.commit.dispatchable_effect_ids


def test_published_v2_examples_cover_applicability_and_effect_boundaries():
    import json

    from jsonschema import Draft202012Validator
    from raes_contracts.contracts import schema_bundle
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.corpus import corpus_family_root

    examples = (
        ("participant-control-selection-v2", "valid", "disjoint-sinks", True, True),
        ("participant-control-evaluation-v2", "valid", "dependency-chain", True, True),
        ("participant-control-evaluation-v2", "valid", "optional-failure", True, True),
        ("participant-control-evaluation-v2", "valid", "later-phase-denial", True, True),
        ("participant-control-evaluation-v2", "invalid", "unknown-field", False, False),
        ("participant-control-evaluation-v2", "context-invalid", "missing-obligation", True, False),
    )
    for contract_id, category, name, schema_valid, model_valid in examples:
        path = corpus_family_root("fixtures") / "participant-runtime" / contract_id / category / (name + ".json")
        payload = json.loads(path.read_text())
        assert Draft202012Validator(schema_bundle()[contract_id]).is_valid(payload) is schema_valid
        model = (
            ParticipantControlSelectionV2Model if "selection" in contract_id else ParticipantControlEvaluationV2Model
        )
        try:
            model.model_validate(payload)
        except ValueError:
            assert not model_valid
        else:
            assert model_valid
