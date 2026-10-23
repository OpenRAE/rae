"""#1363: rev1 DSL-142 control bindings, and the unconditional refusal of rev1 execution paths."""

from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from mixed_control_rev1_scenarios import (
    SEMANTICS,
    delivery_binding,
    legacy_scenario,
    parse,
    rev1_delivery_scenario,
    rev1_scenario,
)
from mixed_control_v2_support import History
from raes._errors import SDLParseError, SDLValidationError
from raes_backend_stubs.manifest import create_stub_manifest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts import manifest_authority
from raes_contracts.contracts.participant_control_composition import control_digest
from raes_contracts.contracts.participant_control_resolution import _validate_inject
from raes_contracts.participant_control_history import iter_participant_control_history_snapshot_violations
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import ParticipantInjectDeliveryControlRuntime
from raes_processor.planner import plan
from raes_runtime.control_plane_configuration import ControlPlaneConfiguration
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_control_mediation import _specification_for_participant, _validate_candidate_history
from raes_runtime.participant_control_targets import participant_control_targets

SPEC_ADDRESS = "participant.behavior-specification.controlled-red"
PLANNER_CODE = "participant.mixed-control-semantics-unsupported"
RUNTIME_CODE = "runtime.mixed-control-semantics-unsupported"


def _with_db_scope(payload: dict) -> dict:
    payload["nodes"]["db"] = {"type": "compute", "resources": {"ram": "1 gib", "cpu": 1}}
    for agent in ("red-agent", "supervisor-agent"):
        payload["agents"][agent]["operating_scope"] = ["nodes.web", "nodes.db"]
    spec = payload["behavior_specifications"]["red-briefing"]
    spec["authority_scope_refs"] = ["nodes.web", "nodes.db"]
    for state in spec["mixed_control"]["controller_states"].values():
        state["scope_refs"] = ["nodes.web", "nodes.db"]
    return payload


def test_a_rev1_binding_joins_the_source_controller_and_compiles_to_a_typed_control_child() -> None:
    model = compile_runtime_model(parse(rev1_delivery_scenario()))
    delivery = model.participant_inject_deliveries[
        "participant.behavior-specification.red-briefing.inject-delivery.briefing"
    ]
    assert isinstance(delivery.control, ParticipantInjectDeliveryControlRuntime)
    assert delivery.control.semantics == SEMANTICS
    assert delivery.control.permitted_transition_address.endswith(".permitted-transition.direct-briefing")
    assert delivery.control.controller_address == "participant.behavior.supervisor-agent"
    assert delivery.control_transition_address == ""
    assert delivery.control.permitted_transition_address in delivery.refresh_dependencies


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda b, s: b["control"].update(controller_ref="red-agent"), "source-state controller"),
        (lambda b, s: b["control"].update(policy_revision="2.0.0"), "control policy pin disagrees"),
        (lambda b, s: b["control"].update(permitted_transition_ref="take"), "does not match delivery_kind"),
        (lambda b, s: b["control"].update(permitted_transition_ref="missing"), "does not resolve"),
        (lambda b, s: b["control"].update(authority_scope_refs=["nodes.web", "entities.blue-team"]), "widens"),
        (lambda b, s: b["control"].update(evidence_refs=["entities.red-team"]), "outside the permitted transition"),
    ],
)
def test_rev1_bindings_fail_closed(mutate, message: str) -> None:
    payload = rev1_delivery_scenario()
    mutate(delivery_binding(payload), payload)
    with pytest.raises(SDLValidationError, match=message):
        parse(payload)


def test_a_rev1_binding_may_narrow_but_not_widen_the_source_scope() -> None:
    payload = _with_db_scope(rev1_delivery_scenario())
    parse(payload)
    states = payload["behavior_specifications"]["red-briefing"]["mixed_control"]["controller_states"]
    states["directed"]["scope_refs"] = ["nodes.web"]
    delivery_binding(payload)["control"]["authority_scope_refs"] = ["nodes.web", "nodes.db"]
    with pytest.raises(SDLValidationError, match="widens the source-state scope"):
        parse(payload)


def test_the_delivery_and_control_policies_are_pinned_independently() -> None:
    payload = rev1_delivery_scenario()
    delivery_binding(payload)["delivery_policy"]["policy_revision"] = "9.9.9"
    parse(payload)


def test_cross_form_bindings_are_refused() -> None:
    legacy_owner = rev1_delivery_scenario()
    spec = legacy_owner["behavior_specifications"]["red-briefing"]
    legacy = legacy_scenario()["behavior_specifications"]["controlled-red"]["mixed_control"]
    spec["mixed_control"] = copy.deepcopy(legacy)
    with pytest.raises(SDLValidationError, match="requires a mixed-control-policy-occurrence/rev1"):
        parse(legacy_owner)
    flat = rev1_delivery_scenario()
    binding = delivery_binding(flat)
    binding.pop("control")
    binding.update(
        control_transition_ref="direct-briefing",
        controller_ref="supervisor-agent",
        control_authority_scope_refs=["nodes.web"],
        control_effective_order=11,
        control_valid_from_order=0,
        control_valid_until_order=11,
        control_evidence_refs=["entities.blue-team"],
    )
    with pytest.raises(SDLValidationError, match="flat control fields cannot bind"):
        parse(flat)


def test_a_disclosure_carries_no_control_block() -> None:
    payload = rev1_delivery_scenario()
    delivery_binding(payload)["delivery_kind"] = "disclosure"
    with pytest.raises(SDLParseError, match="disclosure delivery cannot carry a control block"):
        parse(payload)


@pytest.mark.parametrize(
    "manifest",
    [
        create_stub_manifest,
        lambda: create_stub_manifest(with_time=True, with_realization_envelope=True),
        lambda: create_stub_manifest(with_participant_runtime=False),
    ],
    ids=["default", "time-and-envelope", "no-participant-runtime"],
)
def test_planning_refuses_every_rev1_path_for_every_backend(manifest) -> None:
    for payload, address in (
        (rev1_scenario(), SPEC_ADDRESS),
        (rev1_delivery_scenario(), "participant.behavior-specification.red-briefing.inject-delivery.briefing"),
    ):
        execution_plan = plan(compile_runtime_model(parse(payload)), manifest())
        assert not execution_plan.is_valid
        assert (PLANNER_CODE, address) in {(item.code, item.address) for item in execution_plan.diagnostics}
    legacy_plan = plan(compile_runtime_model(parse(legacy_scenario())), manifest())
    assert PLANNER_CODE not in {item.code for item in legacy_plan.diagnostics}


def test_the_runtime_refuses_rev1_admission_before_any_episode() -> None:
    target = create_stub_target()
    manager = RuntimeManager(target)
    execution_plan = manager.plan(parse(rev1_scenario()))
    assert {PLANNER_CODE, RUNTIME_CODE} <= {item.code for item in execution_plan.diagnostics}
    result = manager.apply(execution_plan)
    assert not result.success
    assert result.snapshot.participant_episode_history == {}
    assert result.snapshot.participant_control_history == {}
    stripped = replace(execution_plan, diagnostics=[])
    retry = manager.apply(stripped)
    assert not retry.success
    assert RUNTIME_CODE in {item.code for item in retry.diagnostics}


def test_control_plane_construction_refuses_rev1_specifications() -> None:
    spec = compile_runtime_model(parse(rev1_scenario())).behavior_specifications[SPEC_ADDRESS]
    with pytest.raises(ValueError, match="cannot install mixed-control-policy-occurrence/rev1"):
        ControlPlaneConfiguration(behavior_specifications={SPEC_ADDRESS: spec})
    legacy = compile_runtime_model(parse(legacy_scenario())).behavior_specifications[SPEC_ADDRESS]
    ControlPlaneConfiguration(behavior_specifications={SPEC_ADDRESS: legacy})


def test_defense_in_depth_guards_hold() -> None:
    spec = compile_runtime_model(parse(rev1_scenario())).behavior_specifications[SPEC_ADDRESS]
    control_plane = SimpleNamespace(_behavior_specifications={SPEC_ADDRESS: spec})
    subject = SimpleNamespace(
        participant_address=spec.mixed_control_participant_address,
        controller_ref=spec.controller_states[0].controller_address,
    )
    identity = SimpleNamespace(participant_control_subjects=(subject,))
    with pytest.raises(ValueError, match="cannot execute a mixed-control-policy-occurrence/rev1"):
        _specification_for_participant(control_plane, spec.mixed_control_participant_address, identity)
    delivery = (
        parse(rev1_delivery_scenario())
        .behavior_specifications["red-briefing"]
        .participant_inject_deliveries["briefing"]
    )
    target = SimpleNamespace(delivery_ref=SimpleNamespace(ref="briefing", digest=control_digest(delivery)))
    context = SimpleNamespace(inject_deliveries={"briefing": delivery})
    with pytest.raises(ValueError, match="cannot join a mixed-control-policy-occurrence/rev1"):
        _validate_inject(target, None, context)


def test_lineage_readers_preserve_v2_but_legacy_context_cannot_validate_it() -> None:
    history = History()
    payload = history.accepted_payload("take")
    participant = payload["participant_address"]
    violations = iter_participant_control_history_snapshot_violations({participant: [payload]})
    assert violations == []
    snapshot = RuntimeSnapshot(participant_control_history={participant: [payload]})
    assert participant_control_targets(snapshot)[0].predecessor_ref == payload["event_id"]
    legacy = compile_runtime_model(parse(legacy_scenario())).behavior_specifications[SPEC_ADDRESS]
    with pytest.raises(ValueError):
        _validate_candidate_history(legacy, [payload], known_targets=())


def test_v2_is_on_no_supported_contract_or_capability_list() -> None:
    contract = "participant-control-occurrence-v2"
    for listed in (
        manifest_authority.PROCESSOR_SUPPORTED_CONTRACT_IDS,
        manifest_authority.BACKEND_SUPPORTED_CONTRACT_IDS,
        manifest_authority.PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
        *manifest_authority.PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS.values(),
    ):
        assert contract not in listed
