"""Finite positive and counterexample cases for the portable obligation catalog."""

from dataclasses import replace

import pytest
from participant_control_contract_fixtures import ref
from participant_control_v2_fixtures import Resolver
from participant_crossing_fixtures import PARTICIPANT, evidence, identity
from raes_conformance.conformance.modular_control_types import ModularControlOperation, ModularControlStep
from raes_contracts.contracts.participant_control_applicability import (
    ParticipantControlSelectionV2Model,
    control_digest,
)
from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
from sem233_flow_sink_fixtures import FlowSinkToggles, deny_resolver
from test_issue_1071_modular_conformance import action_step, case_for, run


@pytest.mark.parametrize(
    "relation,disposition,calls", [("bounded-compatible", "eligible", 1), ("insufficient", "weakened", 0)]
)
def test_admitted_bounded_strength_is_not_a_blanket_downgrade(relation, disposition, calls):
    owner = Resolver()
    selection = owner.selection.model_dump(mode="json")
    for item in [*selection["slots"], *selection["obligations"]]:
        item.update(required_strength="bounded", constraints=[ref("bounded-constraint", "constraint")])
    owner.selection = ParticipantControlSelectionV2Model.model_validate(selection)
    owner.effective_level, owner.support_relation = "bounded", relation
    report = run(
        case_for("support-strength", owner=owner, disposition=disposition, calls=calls), required=("support-strength",)
    )
    assert report.passed
    assert report.cases[0].modular_control.support[0]["relation"] == relation


def test_permissive_influence_records_facts_and_runs_the_parent():
    assert run(case_for("permissive-influence"), required=("permissive-influence",)).passed


def decision_owner(*, conflict=False):
    owner = Resolver()
    selection = owner.selection.model_dump(mode="json")
    selection["slots"] = [{**selection["slots"][-1], "dependencies": []}]
    if conflict:
        selection["slots"].append({**selection["slots"][0], "slot_id": "other-rule"})
    owner.selection = ParticipantControlSelectionV2Model.model_validate(selection)

    def decide(invocation):
        slot = invocation.requested_slot_ids[0]
        owner.calls.append(slot)
        return (
            ControlMechanismResultV2Model(
                result_id="result-" + slot,
                slot_id=slot,
                instance_id=invocation.instance_id,
                binding_digest=invocation.binding_digest,
                context_digest=invocation.context_digest,
                invocation_digest=control_digest(invocation),
                status="resolved",
                payload=dict(
                    kind="decision",
                    disposition="deny" if slot == "other-rule" else "permit",
                    rule=ref("decision-rule", "rule"),
                ),
                evidence=(ref("non-ifc-observation"),),
                next_provider_state=None,
            ),
        )

    owner.providers["influence"].resolve_stage = decide
    return owner


def test_non_ifc_mechanism_needs_no_fabricated_ifc_fact():
    owner = decision_owner()
    report = run(case_for("non-ifc", owner=owner), required=("non-ifc",))
    assert report.passed
    assert owner.calls == ["rule"]


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_decisions_cannot_gain_permission_from_order(reverse):
    owner = decision_owner(conflict=True)
    if reverse:
        owner.selection = owner.selection.model_copy(update={"slots": tuple(reversed(owner.selection.slots))})
    report = run(case_for("conflict", owner=owner, disposition="deny", calls=0), required=("conflict",))
    assert report.passed, report.cases[0].diagnostics


def test_wrong_drain_actor_is_refused_before_dispatch():
    selected = case_for(
        "authority",
        disposition=None,
        calls=0,
        steps=(
            ModularControlStep(
                ModularControlOperation.DISPATCH,
                dict(participant_address=PARTICIPANT, identity=identity(bound=False)),
                expect_refusal=True,
            ),
        ),
    )
    assert run(selected, required=("authority",)).passed


def test_public_final_projection_refusal_has_no_releasable_value():
    from raes_conformance.conformance import run_modular_control_conformance
    from raes_contracts.contracts import ParticipantFlowFinalDisposition
    from test_issue_1069_participant_control_effects import _target
    from test_issue_1071_modular_conformance import Harness

    selected = case_for(
        "final-sink",
        disposition=None,
        calls=0,
        steps=(
            ModularControlStep(
                ModularControlOperation.PROJECTION,
                dict(
                    participant_address=PARTICIPANT,
                    identity=identity(audience_bound=True),
                    crossing_evidence=evidence(),
                    idempotency_key="projection",
                ),
                expect_refusal=True,
            ),
        ),
    )
    selected = replace(
        selected,
        options={
            **selected.options,
            "crossing_policy_resolver": deny_resolver(
                FlowSinkToggles(capability_disposition=ParticipantFlowFinalDisposition.DENY)
            ),
        },
    )
    report = run_modular_control_conformance(_target(), harness=Harness(selected), obligations=("final-sink",))
    assert report.passed, report.cases[0].diagnostics


def test_duplicate_admission_uses_the_exact_receipt_once():
    selected = case_for("duplicate", steps=(action_step(), action_step()))
    assert run(selected, required=("duplicate",)).passed


def test_no_case_can_disable_the_last_release_gate():
    selected = case_for()
    selected = replace(selected, options={**selected.options, "enforce_final_sink_flow_control": False})
    assert not run(selected).passed


def test_out_of_world_malformed_provider_output_cannot_become_an_attack_success():
    owner = Resolver()
    owner.providers["influence"].failure = "malformed"
    report = run(case_for("integrity", owner=owner, disposition="failed", calls=0), required=("integrity",))
    assert report.passed
    assert report.cases[0].modular_control.actual_calls == {}
    assert report.native_conformance is False


@pytest.mark.parametrize("decision,phase", [("deny", "independent"), ("permit", "required-predecessor")])
def test_phase_decisions_do_not_release_the_parent(decision, phase):
    from raes_conformance.conformance import run_modular_control_conformance
    from test_issue_1069_participant_control_effects import _target
    from test_issue_1071_effect_conformance import handoff_case
    from test_issue_1071_modular_conformance import Harness

    selected = replace(handoff_case(phase=phase, decision=decision), obligation="phase-decision")
    report = run_modular_control_conformance(_target(), harness=Harness(selected), obligations=("phase-decision",))
    assert report.passed, report.cases[0].diagnostics


def test_exhausted_trigger_budget_cannot_repeat_the_owner():
    from raes_conformance.conformance import run_modular_control_conformance
    from test_issue_1069_participant_control_effects import _target
    from test_issue_1071_effect_conformance import handoff_case
    from test_issue_1071_modular_conformance import Harness

    selected = handoff_case()
    owner = selected.options["participant_control"].resolver
    # One effect reservation exhausts this root's admitted effect budget.
    owner.selection = owner.selection.model_copy(
        update={"bounds": owner.selection.bounds.model_copy(update={"max_effects": 1})}
    )
    from participant_control_v2_fixtures import binding

    def next_attempt(plane, outputs):
        owner.effect_id = "effect-over-budget"
        return action_step(key="over-budget").arguments

    selected = replace(
        selected,
        obligation="trigger-bound",
        options={**selected.options, "participant_control": binding(owner)},
        steps=(*selected.steps, ModularControlStep(ModularControlOperation.ACTION, next_attempt)),
    )
    report = run_modular_control_conformance(_target(), harness=Harness(selected), obligations=("trigger-bound",))
    assert report.passed, report.cases[0].diagnostics
