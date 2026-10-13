"""#1363: rev1 reusable mixed-control authoring, validation, composition and compilation (ACT-617)."""

from __future__ import annotations

import copy
import textwrap
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml
from mixed_control_rev1_scenarios import edge, legacy_scenario, parse, rev1_policy_of, rev1_scenario
from raes._errors import SDLParseError, SDLValidationError
from raes.parser import parse_sdl_file
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler._mixed_control import _compile_mixed_control
from raes_processor.compiler._mixed_control_policy import (
    _compile_mixed_control_declaration,
    occurrence_policy_projection,
)
from raes_processor.compiler.alias_index import _runtime_addressable_ref_index

SPEC_ADDRESS = "participant.behavior-specification.controlled-red"


def _compiled(payload: dict):
    return compile_runtime_model(parse(payload))


def test_one_compiled_child_per_permission_and_per_script_step() -> None:
    model = _compiled(rev1_scenario())
    spec = model.behavior_specifications[SPEC_ADDRESS]
    policy = spec.mixed_control_policy
    assert spec.mixed_control_semantics == "mixed-control-policy-occurrence/rev1"
    assert spec.control_transitions == ()
    assert [item.transition_id for item in policy.permitted_transitions] == [
        "approve",
        "direct",
        "propose",
        "return",
        "take",
    ]
    take = next(item for item in policy.permitted_transitions if item.transition_id == "take")
    assert (take.transition_kind, take.from_state_address, take.to_state_address) == (
        "handoff",
        f"{SPEC_ADDRESS}.controller-state.autonomous",
        f"{SPEC_ADDRESS}.controller-state.supervised",
    )
    script = _compiled(rev1_scenario(form="finite-script")).behavior_specifications[SPEC_ADDRESS].mixed_control_policy
    assert [(step.step_id, step.position, step.permitted_transition_address) for step in script.script_steps] == [
        ("h1", 1, f"{SPEC_ADDRESS}.permitted-transition.take"),
        ("h2", 2, f"{SPEC_ADDRESS}.permitted-transition.return"),
    ]
    projection = occurrence_policy_projection(spec, episode_id="episode-1")
    assert projection.pin.policy_ref == policy.address
    assert {item.transition_ref for item in projection.transitions} == {
        item.address for item in policy.permitted_transitions
    }


def test_the_legacy_form_compiles_through_the_unchanged_path_with_an_explicit_discriminant() -> None:
    scenario = parse(legacy_scenario())
    spec = compile_runtime_model(scenario).behavior_specifications[SPEC_ADDRESS]
    legacy = _compile_mixed_control(
        spec_name="controlled-red",
        behavior_spec=scenario.behavior_specifications["controlled-red"],
        addressable_ref_index=_runtime_addressable_ref_index(scenario),
    )
    compiled = asdict(spec)
    assert (spec.mixed_control_semantics, spec.mixed_control_policy) == ("fixed-coordinate-v1", None)
    assert tuple(asdict(item) for item in legacy[6]) == tuple(compiled["control_transitions"])
    assert tuple(asdict(item) for item in legacy[5]) == tuple(compiled["controller_states"])
    assert compiled["spec"]["mixed_control"] == scenario.behavior_specifications[
        "controlled-red"
    ].mixed_control.model_dump(mode="json", by_alias=True)


def _set(payload: dict, path: tuple, value) -> dict:
    target = rev1_policy_of(payload)
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return payload


@pytest.mark.parametrize(
    ("path", "limit_is_valid"),
    [
        (("permitted_transitions", "take", "valid_until_order"), True),
        (("controller_states", "supervised", "valid_until_order"), True),
        (("script_steps", 0, "expected_state_revision"), True),
        (("script_steps", 0, "valid_until_order"), False),
    ],
)
def test_authored_coordinates_above_the_mc_08_range_are_refused(path: tuple, limit_is_valid: bool) -> None:
    payload = rev1_scenario(form="finite-script")
    rev1_policy_of(payload)["script_steps"][0].update({"valid_from_order": 0, "valid_until_order": 10})
    with pytest.raises(SDLParseError, match="less than or equal to 1000000"):
        parse(_set(copy.deepcopy(payload), path, 1_000_001))
    if limit_is_valid:
        parse(_set(payload, path, 1_000_000))


@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        (lambda p: p.pop("semantics"), SDLParseError, "Extra inputs|permitted_transitions|form"),
        (lambda p: p.update(semantics="mixed-control-policy-occurrence/rev2"), SDLParseError, "semantics"),
        (lambda p: p.pop("form"), SDLParseError, "form"),
        (lambda p: p.update(form="infinite-script"), SDLParseError, "form"),
        (lambda p: p.update(script_steps=[{"step_id": "h1", "permitted_transition_ref": "take"}]), SDLParseError, ""),
        (lambda p: p["permitted_transitions"]["approve"].update(target_kinds=["proposal"]), SDLParseError, ""),
        (lambda p: p["permitted_transitions"]["direct"].update(target_kinds=["decision"]), SDLParseError, ""),
        (lambda p: p["permitted_transitions"]["take"].pop("completion_evidence_refs"), SDLParseError, ""),
        (lambda p: p["permitted_transitions"]["take"].update(expected_state_revision=0), SDLParseError, ""),
        (lambda p: p["permitted_transitions"]["take"].update(to_state_ref="missing"), SDLParseError, "unknown"),
    ],
)
def test_the_rev1_shape_is_closed(mutation, error, message: str) -> None:
    payload = rev1_scenario()
    mutation(rev1_policy_of(payload))
    with pytest.raises(error, match=message):
        parse(payload)


@pytest.mark.parametrize(("namespace_length", "refused"), [(63, True), (8, False)])
def test_a_namespaced_address_beyond_the_control_ref_range_is_a_compile_diagnostic(
    namespace_length: int, refused: bool
) -> None:
    payload = rev1_scenario()
    policy = rev1_policy_of(payload)
    policy["permitted_transitions"]["e" * 63] = policy["permitted_transitions"].pop("propose")
    scenario = parse(payload)
    namespaced = ".".join(["n" * namespace_length, "m" * namespace_length, "controlled-red"])
    diagnostics: list = []
    _compile_mixed_control_declaration(
        spec_name=namespaced,
        behavior_spec=scenario.behavior_specifications["controlled-red"],
        addressable_ref_index=_runtime_addressable_ref_index(scenario),
        diagnostics=diagnostics,
    )
    codes = [diagnostic.code for diagnostic in diagnostics]
    assert (codes == ["participant.mixed-control-ref-out-of-range"]) is refused
    assert refused or not codes


def test_a_self_to_own_agent_handoff_is_refused_in_rev1_but_kept_in_legacy() -> None:
    payload = rev1_scenario()
    rev1_policy_of(payload)["controller_states"]["supervised"]["controller_ref"] = "red-agent"
    rev1_policy_of(payload)["controller_states"]["supervised"]["authority_basis_refs"] = ["entities.red-team"]
    rev1_policy_of(payload)["controller_states"]["supervised"]["evidence_refs"] = ["entities.red-team"]
    rev1_policy_of(payload)["permitted_transitions"].pop("approve")
    rev1_policy_of(payload)["permitted_transitions"].pop("direct")
    with pytest.raises(SDLValidationError, match="handoff must change controller"):
        parse(payload)
    legacy = legacy_scenario()
    states = legacy["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]
    states["supervised"].update(controller_ref="red-agent", authority_basis_refs=["entities.red-team"])
    states["supervised"]["evidence_refs"] = ["entities.red-team"]
    transition = legacy["behavior_specifications"]["controlled-red"]["mixed_control"]["transitions"][
        "approve_supervision"
    ]
    transition.update(
        transition_kind="handoff", completion_evidence_refs=["entities.red-team"], evidence_refs=["entities.red-team"]
    )
    transition.pop("proposal_ref")
    transition.pop("proposal_revision")
    parse(legacy)


def test_only_a_handoff_may_change_controller_identity() -> None:
    payload = rev1_scenario()
    rev1_policy_of(payload)["permitted_transitions"]["escalate"] = edge(
        "approval", "autonomous", "supervised", "red-team"
    )
    with pytest.raises(SDLValidationError, match="only a handoff changes controller identity"):
        parse(payload)


@pytest.mark.parametrize("kind", ["handoff", "proposal", "intervention", "override", "cancellation"])
def test_an_edge_into_revoked_authority_is_refused_while_legacy_is_unchanged(kind: str) -> None:
    payload = rev1_scenario()
    policy = rev1_policy_of(payload)
    policy["controller_states"]["revoked"] = {
        **policy["controller_states"]["supervised" if kind == "handoff" else "autonomous"],
        "authority_status": "revoked",
    }
    source = "autonomous"
    team = "red-team"
    policy["permitted_transitions"]["into-revoked"] = edge(kind, source, "revoked", team)
    with pytest.raises(SDLValidationError, match="enters revoked authority"):
        parse(payload)
    legacy = legacy_scenario()
    states = legacy["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]
    states["supervised"]["authority_status"] = "revoked"
    parse(legacy)


def test_an_edge_window_must_intersect_the_destination_window() -> None:
    payload = rev1_scenario()
    rev1_policy_of(payload)["controller_states"]["supervised"].update(valid_from_order=500, valid_until_order=1000)
    rev1_policy_of(payload)["permitted_transitions"]["take"].update(valid_from_order=0, valid_until_order=100)
    with pytest.raises(SDLValidationError, match="take' window does not intersect its to-state validity"):
        parse(payload)


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ({"step_id": "h2", "permitted_transition_ref": "return", "valid_from_order": 0, "valid_until_order": 2000}, ""),
        ({"step_id": "h2", "permitted_transition_ref": "return", "target_kind": "proposal"}, "widens"),
        ({"step_id": "h2", "permitted_transition_ref": "approve", "target_step_ref": "missing"}, "earlier step"),
        ({"step_id": "h2", "permitted_transition_ref": "approve", "target_step_ref": "h1"}, "exactly one eligible"),
    ],
)
def test_a_script_step_only_narrows_its_permission(step: dict, message: str) -> None:
    payload = rev1_scenario(form="finite-script", steps=[{"step_id": "h1", "permitted_transition_ref": "take"}, step])
    with pytest.raises((SDLParseError, SDLValidationError), match=message):
        parse(payload)
    ok = rev1_scenario(
        form="finite-script",
        steps=[
            {"step_id": "p1", "permitted_transition_ref": "propose"},
            {"step_id": "h1", "permitted_transition_ref": "take"},
            {"step_id": "a1", "permitted_transition_ref": "approve", "target_step_ref": "p1"},
        ],
    )
    parse(ok)


def test_module_composition_namespaces_rev1_refs_and_keeps_local_ids(tmp_path: Path) -> None:
    module = rev1_scenario()
    module["name"] = "act-617"
    module["module"] = {
        "id": "acme/mixed-control",
        "version": "1.0.0",
        "exports": {
            "nodes": ["web", "internal"],
            "entities": ["red-team", "blue-team"],
            "agents": ["red-agent", "supervisor-agent"],
            "behavior_specifications": ["controlled-red"],
        },
    }
    (tmp_path / "mixed.yaml").write_text(yaml.safe_dump(module, sort_keys=False), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - source: local:mixed.yaml
                namespace: first
              - source: local:mixed.yaml
                namespace: second
            """
        ),
        encoding="utf-8",
    )
    scenario = parse_sdl_file(root)
    for namespace in ("first", "second"):
        declaration = scenario.behavior_specifications[f"{namespace}.controlled-red"].mixed_control
        assert declaration.participant_ref == f"{namespace}.red-agent"
        assert declaration.controller_states["supervised"].controller_ref == f"{namespace}.supervisor-agent"
        take = declaration.permitted_transitions["take"]
        assert take.evidence_refs == [f"entities.{namespace}.red-team"]
        assert take.completion_evidence_refs == [f"entities.{namespace}.blue-team"]
        assert (take.from_state_ref, take.to_state_ref) == ("autonomous", "supervised")


@pytest.mark.parametrize("form", ["legacy", "rev1"])
def test_relationship_control_bindings_read_either_form(form: str) -> None:
    payload = legacy_scenario() if form == "legacy" else rev1_scenario()
    payload["relationships"] = {
        "control": {
            "type": "participant",
            "source": "supervisor-agent",
            "target": "red-agent",
            "participant": {
                "kind": "supervision",
                "scope_refs": ["nodes.web"],
                "control_specification_ref": "behavior_specifications.controlled-red",
            },
        }
    }
    parse(payload)
    reversed_payload = copy.deepcopy(payload)
    edge_payload = reversed_payload["relationships"]["control"]
    edge_payload["source"], edge_payload["target"] = "red-agent", "supervisor-agent"
    with pytest.raises(SDLValidationError, match="control_specification_ref.*direction"):
        parse(reversed_payload)
    for agent in payload["agents"].values():
        agent["operating_scope"].append("nodes.internal")
    payload["relationships"]["control"]["participant"]["scope_refs"] = ["nodes.internal"]
    with pytest.raises(SDLValidationError, match="control_specification_ref.*scope"):
        parse(payload)
