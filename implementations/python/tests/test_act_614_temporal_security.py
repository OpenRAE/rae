"""Temporal evidence authorization and backend trust-boundary regressions."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from implementations.python.tests._act_614_temporal_fixtures import (
    _activity_temporal_payload,
    _bound_deadline_payload,
    _bound_dwell_payload,
    _temporal_target,
    _TemporalEvidenceRuntime,
)
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _activity_control,
    _activity_policy_yaml,
)
from implementations.python.tests.test_issue_899_participant_resource_budgets import _budget_policy_yaml
from raes._errors import SDLValidationError
from raes.parser import parse_sdl
from raes_runtime.manager import RuntimeManager


@pytest.mark.parametrize("mutation", ["undeclared", "withheld", "foreign", "duplicate", "boundary"])
def test_native_temporal_proofs_are_authorized_before_history_commit(mutation: str) -> None:
    class MaliciousRuntime(_TemporalEvidenceRuntime):
        def bind_autonomous_action(self, *args):
            request = super().bind_autonomous_action(*args)
            if mutation == "withheld":
                request.implementation_selection.exposure_policy.withheld_refs.append("content.participant-observation")
            return request

        def admit_action(self, request, snapshot):
            native = super().admit_action(request, snapshot)
            if mutation == "withheld":
                return native
            proof = native.action_result.temporal_evidence[0].model_copy(deep=True)
            proofs = [proof]
            if mutation == "undeclared":
                proof.evidence_refs = ("evidence.undeclared",)
            elif mutation == "foreign":
                proof.context.participant_address = "participant.behavior.someone-else"
                proofs = [*native.action_result.temporal_evidence, proof]
            elif mutation == "duplicate":
                proofs.append(proof.model_copy(deep=True))
            else:
                proof.observation_boundary_address = "participant.observation-boundary.other"
            action_result = native.action_result.model_copy(update={"temporal_evidence": proofs})
            histories = deepcopy(native.snapshot.participant_behavior_history)
            histories[request.participant_address][-1]["action_result"] = action_result.model_dump(mode="json")
            return replace(
                native,
                action_result=action_result,
                snapshot=native.snapshot.with_entries(
                    dict(native.snapshot.entries),
                    participant_behavior_history=histories,
                ),
            )

    scenario, target = _temporal_target(_bound_deadline_payload(), MaliciousRuntime())
    manager = RuntimeManager(target)
    result = manager.apply(manager.plan(scenario))
    assert not result.success
    assert not result.snapshot.participant_behavior_history


@pytest.mark.parametrize("phase", ["binding", "dispatch"])
@pytest.mark.parametrize("mutation", ["strip", "bound"])
@pytest.mark.parametrize("profile", ["v1", "v2", "v3", "concurrent"])
def test_backend_cannot_mutate_authoritative_temporal_request(phase: str, mutation: str, profile: str) -> None:
    class MutatingRuntime(_TemporalEvidenceRuntime):
        def mutate(self, contexts):
            for context in contexts:
                if mutation == "strip":
                    context.shared_time = None
                else:
                    context.shared_time.binding.end.tick = 1000
                    context.shared_time.bound_end.tick = 1000

        def bind_autonomous_action(self, *args):
            request = super().bind_autonomous_action(*args)
            if phase == "binding":
                self.mutate(request.temporal_contexts)
            return request

        def admit_action(self, request, snapshot):
            if phase == "dispatch":
                self.mutate(request.temporal_contexts)
            return super().admit_action(request, snapshot)

    activity = profile in {"v2", "v3"}
    source = _budget_policy_yaml if profile == "v3" else _activity_policy_yaml
    payload = _activity_temporal_payload(source) if activity else _bound_deadline_payload()
    deadline = 15 if activity else 5
    payload["temporal_constraints"]["finish-by-five"]["end"]["tick"] = deadline
    if profile == "concurrent":
        payload["entities"]["second"] = deepcopy(payload["entities"]["enterprise-participant"])
        payload["agents"]["second"] = {**deepcopy(payload["agents"]["participant-agent"]), "entity": "second"}
        spec = payload["behavior_specifications"]["participant-behavior"]
        spec["participant_refs"].append("second")
        spec["autonomous_execution"]["max_in_flight"] = 2
    scenario, target = _temporal_target(payload, MutatingRuntime())
    manager = RuntimeManager(target, stochastic_controls=(_activity_control(),) if activity else ())
    plan = manager.plan(scenario)
    result = manager.apply(plan)
    if activity:
        result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    policy = next(iter(plan.model.behavior_specifications.values())).autonomous_execution
    assert policy.temporal_bindings[0].end.tick == deadline
    if phase == "dispatch":
        assert not result.success
        assert not result.snapshot.participant_behavior_history
    else:
        # Binding cannot remove or change the runtime-owned requirement.
        histories = result.snapshot.participant_behavior_history.values()
        assert histories
        assert all(
            history[-1]["temporal_assessments"][0]["context"]["bound_end"]["tick"] == deadline for history in histories
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign-boundary",
        "participant-boundary",
        "spec-boundary",
        "policy-boundary",
        "unobservable-condition",
        "hidden-condition",
        "undeclared-evidence",
    ],
)
def test_dwell_requires_authorized_observation_of_its_condition(mutation: str) -> None:
    payload = _bound_dwell_payload()
    action = payload["action_contracts"]["probe-customer-portal-login"]
    binding = action["temporal_contracts"][0]["shared_time_binding"]
    condition = next(item for item in action["preconditions"] if item["precondition_id"] == "portal-present")
    if mutation.endswith("boundary"):
        payload["observation_boundaries"]["other-view"] = deepcopy(
            payload["observation_boundaries"]["participant-view"]
        )
        binding["observation_boundary_ref"] = "other-view"
        if mutation in {"spec-boundary", "policy-boundary"}:
            payload["agents"]["participant-agent"]["observation_boundaries"].append("other-view")
        if mutation in {"participant-boundary", "policy-boundary"}:
            payload["behavior_specifications"]["participant-behavior"]["observation_boundary_refs"].append("other-view")
    elif mutation == "hidden-condition":
        payload["observation_boundaries"]["participant-view"]["view_rules"] = [
            {
                "information_ref": condition["support_refs"][0],
                "boundary_class": "observable_resource",
                "disposition": "hidden",
                "visibility_basis": "Unavailable to this participant.",
            }
        ]
    elif mutation == "unobservable-condition":
        condition["support_refs"] = ["content.evaluator-notes"]
    else:
        condition["evidence_refs"] = ["content.evaluator-notes"]
    with pytest.raises(SDLValidationError, match="temporal binding"):
        parse_sdl(yaml.safe_dump(payload))
