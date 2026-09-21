"""ACT-614 temporal profiles."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from implementations.python.tests._act_614_temporal_fixtures import (
    _bound_deadline_payload,
    _bound_dwell_payload,
)
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    IMPLEMENTATION_REF,
    _activity_policy_yaml,
    _autonomous_manifest,
    _scenario_yaml,
)
from implementations.python.tests.test_issue_899_participant_resource_budgets import _budget_policy_yaml
from pydantic import ValidationError
from raes._errors import SDLInstantiationError, SDLParseError, SDLValidationError
from raes._module_symbols import HASHMAP_SECTIONS
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl, parse_sdl_file
from raes.participant_execution import ParticipantActivityTiming
from raes_backend_protocols.capability_admission import participant_autonomous_execution_capability_gaps
from raes_processor.compiler import compile_runtime_model


def test_bound_dwell_requires_its_selected_event_to_be_declared() -> None:
    payload = _bound_dwell_payload()
    temporal = payload["action_contracts"]["probe-customer-portal-login"]["temporal_contracts"][0]
    temporal["event_points"] = ["window_open", "window_close"]
    with pytest.raises(SDLParseError, match="declared event_point"):
        parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize("source", [_scenario_yaml, _activity_policy_yaml, _budget_policy_yaml])
@pytest.mark.parametrize("export_private", [False, True])
def test_repeated_profile_imports_resolve_nested_references(tmp_path: Path, source, export_private: bool) -> None:
    payload = yaml.safe_load(source())
    # Role selectors intentionally select every matching participant in the
    # composed scenario. These module instances select their explicit owner.
    payload["behavior_specifications"]["participant-behavior"]["participant_role_refs"] = []
    exports = {"behavior_specifications": ["participant-behavior"]}
    if export_private:
        exports = {section: list(payload[section]) for section in HASHMAP_SECTIONS if payload.get(section)}
    payload["module"] = {"id": "examples/temporal-profile", "version": "1.0.0", "exports": exports}
    (tmp_path / "profile.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    root = tmp_path / "scenario.yaml"
    root.write_text(
        yaml.safe_dump(
            {
                "name": "repeated-profile-imports",
                "imports": [{"path": "profile.yaml", "namespace": namespace} for namespace in ("office", "lab")],
            }
        ),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    runtime = compile_runtime_model(scenario)
    assert len(runtime.behavior_specifications) == 2
    for namespace in ("office", "lab"):
        prefix = namespace if export_private else f"{namespace}.__private"
        policy = scenario.behavior_specifications[f"{namespace}.participant-behavior"].autonomous_execution
        assert policy.clock_ref == f"{prefix}.scenario-clock"
        assert policy.progression_policy_ref == f"{prefix}.scenario-progression"
        assert policy.observation_boundary_ref == f"{prefix}.participant-view"
        assert policy.participant_implementation_ref == IMPLEMENTATION_REF
        if policy.profile == "participant-autonomous-execution/v1":
            assert policy.action_order == [f"{prefix}.probe-customer-portal-login"]
            assert policy.temporal_constraint_refs == [f"{prefix}.green-cadence"]
        else:
            assert policy.work_window_refs == [f"{prefix}.work-window"]
            assert policy.pause_window_refs == [f"{prefix}.pause-window"]
            assert policy.stochastic_control_ref == "green-activity-policy"
            assert set(policy.action_candidates) == {"portal_login"}
            assert policy.action_candidates["portal_login"].action_ref == f"{prefix}.probe-customer-portal-login"
        action = scenario.action_contracts[f"{prefix}.probe-customer-portal-login"]
        target = f"nodes.{prefix}.customer-portal.services.http"
        assert target in action.preconditions[0].support_refs
        assert action.effects[0].target_refs == [target]
        boundary = scenario.observation_boundaries[f"{prefix}.participant-view"]
        assert all(set(rule.evidence_refs) <= set(boundary.evidence_refs) for rule in boundary.view_rules)


def test_activity_timing_accepts_typed_whole_field_parameters() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["variables"] = {"interval": {"type": "integer", "required": True}}
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["timing"] = {
        "minimum_ticks": "${interval}",
        "maximum_ticks": "${interval}",
    }
    scenario = parse_sdl(yaml.safe_dump(payload))
    assert (
        scenario.behavior_specifications["participant-behavior"].autonomous_execution.timing.minimum_ticks
        == "${interval}"
    )
    bound = instantiate_scenario(scenario, {"interval": 20})
    assert bound.behavior_specifications["participant-behavior"].autonomous_execution.timing.minimum_ticks == 20
    compile_runtime_model(bound)


@pytest.mark.parametrize(
    ("source", "path", "value"),
    [
        (_scenario_yaml, ("max_action_attempts",), 4),
        (_scenario_yaml, ("max_in_flight",), 2),
        (_activity_policy_yaml, ("max_occurrences",), 4),
        (_activity_policy_yaml, ("max_action_attempts",), 24),
        (_activity_policy_yaml, ("max_burst_size",), 3),
        (_activity_policy_yaml, ("max_in_flight",), 2),
        (_activity_policy_yaml, ("action_candidates", "portal_login", "weight"), 7),
        (_activity_policy_yaml, ("action_candidates", "portal_login", "max_retries"), 1),
        (_activity_policy_yaml, ("action_candidates", "portal_login", "cooldown_ticks"), 0),
        (_budget_policy_yaml, ("max_in_flight",), 1),
    ],
)
def test_policy_numeric_parameters_bind_before_dependent_validation(source, path: tuple[str, ...], value: int) -> None:
    payload = yaml.safe_load(source())
    payload["variables"] = {"bound": {"type": "integer", "required": True}}
    field = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    for key in path[:-1]:
        field = field[key]
    field[path[-1]] = "${bound}"
    scenario = parse_sdl(yaml.safe_dump(payload))
    bound = instantiate_scenario(scenario, {"bound": value})
    compiled = compile_runtime_model(bound)
    assert len(compiled.behavior_specifications) == 1
    field = bound.behavior_specifications["participant-behavior"].autonomous_execution.model_dump()
    for key in path:
        field = field[key]
    assert field == value
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(scenario, {"bound": True})
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(scenario)


@pytest.mark.parametrize("value", [True, 1.0, 1.5, float("inf"), 0, -1, 1_000_000_001, "${interval}ticks"])
def test_activity_numeric_fields_reject_non_integer_or_out_of_bounds_values(value: object) -> None:
    with pytest.raises(ValidationError):
        ParticipantActivityTiming(minimum_ticks=value, maximum_ticks=30)


def test_bound_interval_rechecks_order_and_stepped_reachability() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["variables"] = {"minimum": {"type": "integer", "required": True}}
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["timing"]["minimum_ticks"] = (
        "${minimum}"
    )
    scenario = parse_sdl(yaml.safe_dump(payload))
    for value in (40, 11):
        with pytest.raises(SDLInstantiationError):
            instantiate_scenario(scenario, {"minimum": value})


@pytest.mark.parametrize(
    ("source", "path", "invalid"),
    [
        (_activity_policy_yaml, ("max_occurrences",), 999),
        (_activity_policy_yaml, ("max_burst_size",), 999),
        (_activity_policy_yaml, ("action_candidates", "portal_login", "max_retries"), 0),
        (_budget_policy_yaml, ("max_in_flight",), 2),
    ],
)
def test_numeric_binding_rechecks_cross_field_constraints(source, path, invalid) -> None:
    payload = yaml.safe_load(source())
    payload["variables"] = {"bound": {"type": "integer", "required": True}}
    field = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    for part in path[:-1]:
        field = field[part]
    field[path[-1]] = "${bound}"
    scenario = parse_sdl(yaml.safe_dump(payload))
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(scenario, {"bound": invalid})


def test_numeric_parameter_must_be_declared() -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["max_occurrences"] = "${missing}"
    with pytest.raises(SDLValidationError):
        parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize("event", ["start", "end", "observed", "effective"])
def test_explicit_deadline_binding_compiles_action_event_and_shared_coordinate(event: str) -> None:
    scenario = parse_sdl(yaml.safe_dump(_bound_deadline_payload(event)))
    model = compile_runtime_model(scenario)
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    binding = policy.temporal_bindings[0]
    assert binding.temporal_id == "finish"
    assert binding.action_contract_address == "participant.action-contract.probe-customer-portal-login"
    assert binding.clock_address == "time.clock.scenario-clock"
    assert binding.constraint_address == "time.constraint.finish-by-five"
    assert binding.event_point == event
    assert binding.end.tick == 5
    assert binding.contract_digest.startswith("sha256:")

    manifest = _autonomous_manifest(model)
    gaps = participant_autonomous_execution_capability_gaps(manifest, [policy], model.time_model)
    assert any("temporal" in gap for gap in gaps)


def test_shared_constraint_keeps_existing_clock_reference_syntax() -> None:
    payload = _bound_deadline_payload()
    payload["temporal_constraints"]["finish-by-five"]["clock_ref"] = "clocks.scenario-clock"
    with pytest.raises(SDLValidationError, match="does not reference a declared clock"):
        parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize("kind", ["user-deadline", "automation-dwell"])
def test_portable_temporal_examples_compile_and_parameterize(kind: str) -> None:
    path = Path(__file__).resolve().parents[3] / "examples/scenarios/temporal-profiles" / f"{kind}.sdl.yaml"
    source = parse_sdl_file(path)
    scenario = instantiate_scenario(source, {"attempts": 1})
    model = compile_runtime_model(scenario)
    policy = next(iter(model.behavior_specifications.values())).autonomous_execution
    assert len(policy.temporal_bindings) == 1
    assert policy.max_action_attempts == 1
    assert policy.temporal_bindings[0].temporal_kind == ("deadline" if kind == "user-deadline" else "dwell")


def test_imported_numeric_parameters_bind_independently(tmp_path: Path) -> None:
    payload = yaml.safe_load(_activity_policy_yaml())
    payload["variables"] = {"interval": {"type": "integer", "required": True}}
    specification = payload["behavior_specifications"]["participant-behavior"]
    specification["participant_role_refs"] = []
    specification["autonomous_execution"]["timing"] = {"minimum_ticks": "${interval}", "maximum_ticks": "${interval}"}
    payload["module"] = {
        "id": "examples/activity",
        "version": "1.0.0",
        "parameters": ["interval"],
        "exports": {"behavior_specifications": ["participant-behavior"]},
    }
    (tmp_path / "profile.yaml").write_text(yaml.safe_dump(payload))
    (tmp_path / "root.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "independent-profile-parameters",
                "imports": [
                    {"path": "profile.yaml", "namespace": name, "parameters": {"interval": ticks}}
                    for name, ticks in (("office", 10), ("lab", 20))
                ],
            }
        )
    )
    scenario = parse_sdl_file(tmp_path / "root.yaml")
    bound = instantiate_scenario(scenario)
    model = compile_runtime_model(bound)
    assert {spec.autonomous_execution.timing_minimum_ticks for spec in model.behavior_specifications.values()} == {
        10,
        20,
    }


@pytest.mark.parametrize("kind", ["deadline", "dwell"])
def test_explicit_temporal_bindings_follow_private_module_imports(tmp_path: Path, kind: str) -> None:
    payload = _bound_deadline_payload() if kind == "deadline" else _bound_dwell_payload()
    payload["behavior_specifications"]["participant-behavior"]["participant_role_refs"] = []
    payload["module"] = {
        "id": "examples/temporal-profile",
        "version": "1.0.0",
        "exports": {"behavior_specifications": ["participant-behavior"]},
    }
    (tmp_path / "profile.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        yaml.safe_dump({"name": "bound-import", "imports": [{"path": "profile.yaml", "namespace": "office"}]}),
        encoding="utf-8",
    )
    model = compile_runtime_model(parse_sdl_file(root))
    binding = next(iter(model.behavior_specifications.values())).autonomous_execution.temporal_bindings[0]
    assert binding.clock_address == "time.clock.office.__private.scenario-clock"
    if kind == "dwell":
        assert (
            binding.observation_boundary_address == "participant.observation-boundary.office.__private.participant-view"
        )
        assert binding.condition_precondition_id == "portal-present"


def test_bound_temporal_domain_cannot_contradict_the_selected_shared_clock() -> None:
    payload = _bound_deadline_payload()
    payload["action_contracts"]["probe-customer-portal-login"]["temporal_contracts"][0]["time_domain"] = "episode_step"
    with pytest.raises(SDLValidationError, match="time domain"):
        parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize("mutation", ["start", "condition", "mode"])
def test_resolved_dwell_contract_rejects_missing_or_conflicting_semantics(mutation: str) -> None:
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalBindingModel

    model = compile_runtime_model(parse_sdl(yaml.safe_dump(_bound_dwell_payload())))
    binding = (
        next(iter(model.behavior_specifications.values()))
        .autonomous_execution.temporal_bindings[0]
        .model_dump(mode="json")
    )
    if mutation == "mode":
        binding["evidence_mode"] = "event"
    else:
        binding.pop("start" if mutation == "start" else "condition_precondition_id")
    with pytest.raises(ValueError, match="dwell"):
        ParticipantTemporalBindingModel.model_validate(binding)


@pytest.mark.parametrize("kind", ["deadline", "dwell"])
def test_published_authoring_schema_accepts_explicit_shared_time_binding(kind: str) -> None:
    import json

    from jsonschema import Draft202012Validator

    schema_path = Path(__file__).resolve().parents[3] / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
    schema = json.loads(schema_path.read_text())
    payload = _bound_deadline_payload() if kind == "deadline" else _bound_dwell_payload()
    Draft202012Validator(schema).validate(payload)


@pytest.mark.parametrize("mutation", ["subject", "clock", "constraint", "kind", "policy_clock"])
def test_temporal_bindings_reject_invalid_references_before_backend_selection(mutation: str) -> None:
    payload = _bound_deadline_payload()
    constraint = payload["temporal_constraints"]["finish-by-five"]
    binding = payload["action_contracts"]["probe-customer-portal-login"]["temporal_contracts"][0]["shared_time_binding"]
    if mutation == "subject":
        constraint["subject_refs"] = ["nodes.customer-db"]
    elif mutation in {"clock", "constraint"}:
        binding[f"{mutation}_ref"] = "missing"
    elif mutation == "kind":
        constraint.update(constraint_kind="window", start={"tick": 0})
    else:
        payload["clocks"]["other-clock"] = dict(payload["clocks"]["scenario-clock"])
        constraint["clock_ref"] = "other-clock"
        binding["clock_ref"] = "other-clock"
    with pytest.raises(SDLValidationError, match="temporal binding"):
        parse_sdl(yaml.safe_dump(payload))
