"""Issue #310 (ACT-624): participant interaction budgets and quotas as first-class support.

The tests follow the ACT-624 rows of the issue #122 source-to-contract-to-test
matrix in ``specs/formal/participant-episode-model/README.md``:

- an interaction budget is a member of the behavior-specification aggregate for
  every participant kind, not an option of the autonomous profile alone, and an
  attempt has one governing budget (EBM-04);
- a participant-local budget never counts another participant's use, including
  participants a role selects (EBM-03);
- step, turn, time, token, and tool-use stay distinct governed dimensions that
  planner capability admission checks against the backend declaration (EBM-05);
  and
- backend enforcement is realization evidence that conformance checks, not
  proof (EBM-09).
"""

from __future__ import annotations

import ast
import copy
import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from implementations.python.tests.test_dsl_437_benign_participant_execution import _NativeParticipantRuntime
from implementations.python.tests.test_issue_306_participant_budget_exhaustion import _advance_to_next_action
from implementations.python.tests.test_issue_308_participant_interaction_budgets import (
    ACTION,
    SPEC,
    TOOL_BUDGET,
    _interaction_capabilities,
    _interaction_manifest,
    _manager,
    _payload,
    _source,
    _table_rows,
    _validation_messages,
)
from pydantic import ValidationError
from raes import instantiate_scenario, parse_sdl, parse_sdl_file
from raes._errors import SDLInstantiationError
from raes.participant_behavior_specification import ParticipantBehaviorSpecification
from raes.participant_resource_budgets import ParticipantInteractionBudget, ParticipantResourceBudgetPolicy
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_backend_protocols.participant_capabilities import ParticipantFeatureSupport
from raes_backend_protocols.participant_resource_admission import participant_interaction_budget_gaps
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance.participant_interaction_budgets import (
    PARTICIPANT_INTERACTION_BUDGET_INVALID_DIAGNOSTIC_CODE,
    participant_interaction_budget_conformance_diagnostics,
)
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.participant_manifests import BackendManifestV2Model
from raes_contracts.contracts.participant_resource_budgets import participant_resource_budget_state_ref
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.participant_resource_accounting import commit_participant_resource_reservation
from raes_runtime.participant_resource_budgets import initialize_participant_resource_budgets
from raes_runtime.participant_resource_reservation import reserve_participant_resources

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN = REPO_ROOT / "specs/formal/participant-episode-model/README.md"
SEMANTICS = REPO_ROOT / "specs/formal/participant-semantics/autonomous-execution.md"
MIXED_CONTROL_FIXTURE = REPO_ROOT / "contracts/fixtures/sdl/mixed-control-v1/valid/mixed-control-participant.yaml"
PARTICIPANT = "participant.behavior.participant-agent"
BUDGET_ADDRESS = f"participant.interaction-budget.{SPEC}"
# Action, turn, logical time, token, and tool-use bounds (the ACT-624 statement).
AGGREGATE_DIMENSIONS = (
    "participant-actions",
    "range-actions",
    "fleet-actions",
    "turns",
    "scenario-time",
    "tokens",
    TOOL_BUDGET,
)
TURNS_ONLY = {
    "policy_id": "turn-budget",
    "owners": {"self": {"kind": "participant", "ref": "red-agent"}},
    "fairness": {
        "policy": "weighted_fair",
        "priority_class": "background",
        "weight": 1,
        "protected": False,
        "borrowing": "lendable_only",
        "reclaim": "yield",
        "max_queue_ticks": 20,
        "starvation_bound_ticks": 100,
    },
    "dimensions": {
        "turns": {
            "owner_ref": "self",
            "pool_ref": "participant-pool",
            "resource_kind": "interaction_turns",
            "unit": "turns",
            "accounting_mode": "cumulative_counter",
            "meter_profile_ref": "raes.participant-turn/v1",
            "limit": 20,
            "reservation": 1,
            "reset": "episode",
        }
    },
}
INTERACTION_BUDGET_SUPPORT = ParticipantFeatureSupport(
    feature="interaction_budgets",
    support_level="exact",
    evidence_refs=("evidence:interaction-budget-conformance",),
)


def _aggregate_payload(*, behavior_mode: str | None = "human-supervised") -> dict:
    """Move the v3 fixture's budget onto the aggregate of a non-autonomous participant."""

    payload = _payload()
    spec = payload["behavior_specifications"][SPEC]
    policy = spec.pop("autonomous_execution")
    budget = policy["resource_budget"]
    budget["dimensions"] = {key: budget["dimensions"][key] for key in AGGREGATE_DIMENSIONS}
    budget["clock_ref"] = policy["clock_ref"]
    spec["resource_budget"] = budget
    if behavior_mode is None:
        spec.pop("behavior_mode")
    else:
        spec["behavior_mode"] = behavior_mode
    return payload


def _aggregate_budget(payload: dict | None = None):
    model = compile_runtime_model(parse_sdl(_source(payload or _aggregate_payload())))
    return model.behavior_specifications[f"participant.behavior-specification.{SPEC}"].interaction_budget


def _mixed_control_source() -> str:
    payload = yaml.safe_load(MIXED_CONTROL_FIXTURE.read_text(encoding="utf-8"))
    payload["behavior_specifications"]["controlled-red"]["resource_budget"] = copy.deepcopy(TURNS_ONLY)
    return yaml.safe_dump(payload, sort_keys=False)


@pytest.mark.parametrize(
    ("source", "spec_name", "participant"),
    [
        *(
            (_source(_aggregate_payload(behavior_mode=mode)), SPEC, PARTICIPANT)
            for mode in (
                "autonomous",
                "human-control-proxy",
                "human-supervised",
                "policy-directed",
                "replayed",
                "scripted",
            )
        ),
        (_mixed_control_source(), "controlled-red", "participant.behavior.red-agent"),
        (_source(_aggregate_payload(behavior_mode=None)), SPEC, PARTICIPANT),
    ],
    ids=[
        "autonomous",
        "human-control-proxy",
        "human-supervised",
        "policy-directed",
        "replayed",
        "scripted",
        "mixed-control",
        "no-behavior-mode",
    ],
)
def test_interaction_budget_is_a_member_of_every_participant_kind_aggregate(
    source: str,
    spec_name: str,
    participant: str,
) -> None:
    model = compile_runtime_model(parse_sdl(source))
    aggregate = model.behavior_specifications[f"participant.behavior-specification.{spec_name}"]

    assert aggregate.autonomous_execution is None
    assert aggregate.interaction_budget.address == f"participant.interaction-budget.{spec_name}"
    assert aggregate.interaction_budget.participant_addresses == (participant,)
    assert aggregate.interaction_budget.behavior_specification_address == aggregate.address


def test_interaction_budget_alone_satisfies_the_behavior_aggregate() -> None:
    bare = {"semantic_version": "1.0.0", "participant_refs": ["red-agent"]}

    specification = ParticipantBehaviorSpecification.model_validate(bare | {"resource_budget": TURNS_ONLY})

    assert specification.resource_budget.dimensions["turns"].limit == 20
    with pytest.raises(ValidationError, match="must aggregate at least one behavior surface reference"):
        ParticipantBehaviorSpecification.model_validate(bare)


def test_the_autonomous_profile_cannot_also_carry_an_aggregate_budget() -> None:
    spec = _payload()["behavior_specifications"][SPEC]
    spec["resource_budget"] = copy.deepcopy(TURNS_ONLY) | {"owners": {"self": {"kind": "participant", "ref": "x"}}}

    with pytest.raises(ValidationError, match="an autonomous execution profile carries its own budget"):
        ParticipantBehaviorSpecification.model_validate(spec)


def test_aggregate_budget_bounds_only_the_dimensions_it_declares() -> None:
    assert set(ParticipantInteractionBudget.model_validate(TURNS_ONLY).dimensions) == {"turns"}
    with pytest.raises(ValidationError, match="resource budget requires complete resource vector"):
        ParticipantResourceBudgetPolicy.model_validate(TURNS_ONLY)


def _clocked_dimension(kind: str, unit: str, meter: str, *, reset: str, window: int | None = None) -> dict:
    dimension = TURNS_ONLY["dimensions"]["turns"] | {
        "resource_kind": kind,
        "unit": unit,
        "meter_profile_ref": meter,
        "reset": reset,
    }
    if window is not None:
        dimension |= {"accounting_mode": "windowed_counter", "window_ticks": window}
    return dimension


@pytest.mark.parametrize(
    ("dimension", "clock_ref"),
    [
        (_clocked_dimension("scenario_time", "ticks", "raes.shared-time-ticks/v1", reset="run"), None),
        (_clocked_dimension("interaction_turns", "turns", "raes.participant-turn/v1", reset="time_segment"), None),
        (_clocked_dimension("interaction_turns", "turns", "raes.participant-turn/v1", reset="run", window=10), None),
        (TURNS_ONLY["dimensions"]["turns"], "scenario-clock"),
    ],
    ids=["scenario-time", "time-segment-reset", "window", "unused-clock"],
)
def test_aggregate_budget_counts_ticks_on_exactly_one_declared_clock(dimension: dict, clock_ref: str | None) -> None:
    budget = TURNS_ONLY | {"dimensions": {"bound": dimension}, "clock_ref": clock_ref}

    with pytest.raises(ValidationError, match="interaction budget clock_ref is required exactly when"):
        ParticipantInteractionBudget.model_validate(budget)


def _unknown_clock(payload: dict) -> None:
    payload["behavior_specifications"][SPEC]["resource_budget"]["clock_ref"] = "missing-clock"


def _unknown_affordance(payload: dict) -> None:
    payload["behavior_specifications"][SPEC]["resource_budget"]["dimensions"][TOOL_BUDGET]["tool_affordance_refs"] = [
        "missing-tool"
    ]


def _two_participants(payload: dict) -> None:
    payload["agents"]["second-agent"] = copy.deepcopy(payload["agents"]["participant-agent"])
    payload["behavior_specifications"][SPEC]["participant_refs"].append("second-agent")


def _role_selected_participant(payload: dict) -> None:
    # The copy keeps the green entity, so participant_role_refs ["green"] selects it.
    payload["agents"]["second-agent"] = copy.deepcopy(payload["agents"]["participant-agent"])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_unknown_clock, "resource_budget clock_ref 'missing-clock' does not name a declared clock"),
        (_unknown_affordance, "tool_affordance_ref 'missing-tool' does not name a tool affordance"),
        (_two_participants, "participant ref 'participant-agent' would count every governed participant's use"),
        (
            _role_selected_participant,
            "participant ref 'participant-agent' would count every governed participant's use",
        ),
    ],
    ids=["unknown-clock", "unknown-affordance", "participant-local-across-participants", "role-selected-participant"],
)
def test_aggregate_budget_refs_resolve_inside_its_specification(mutate, message: str) -> None:
    payload = _aggregate_payload()
    mutate(payload)

    assert any(message in line for line in _validation_messages(payload))


def _parameterized_participant() -> dict:
    """Name the governed participant, and its participant owner, through one variable."""

    payload = _aggregate_payload()
    payload["variables"] = {"governed_agent": {"type": "string", "default": "participant-agent"}}
    spec = payload["behavior_specifications"][SPEC]
    spec["participant_refs"] = ["${governed_agent}"]
    spec["resource_budget"]["owners"]["green"]["ref"] = "${governed_agent}"
    return payload


def test_parameterized_participants_are_checked_once_their_variables_resolve() -> None:
    crowded = _parameterized_participant()
    _role_selected_participant(crowded)

    resolved = instantiate_scenario(parse_sdl(_source(_parameterized_participant())))
    model = compile_runtime_model(resolved)
    unresolved = parse_sdl(_source(crowded))

    budget = model.behavior_specifications[f"participant.behavior-specification.{SPEC}"].interaction_budget
    assert budget.participant_addresses == (PARTICIPANT,)
    with pytest.raises(SDLInstantiationError, match="would count every governed participant's use"):
        instantiate_scenario(unresolved)


def _second_budget(payload: dict, selection: dict, participant: str = "participant-agent") -> dict:
    """Add a turns-only aggregate budget in a second specification that selects ``selection``."""

    owners = {"self": {"kind": "participant", "ref": participant}}
    payload["behavior_specifications"]["second-budget"] = {
        "semantic_version": "1.0.0",
        **selection,
        "resource_budget": copy.deepcopy(TURNS_ONLY) | {"owners": owners},
    }
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        _second_budget(_payload(), {"participant_refs": ["participant-agent"]}),
        _second_budget(_aggregate_payload(), {"participant_refs": ["participant-agent"]}),
        _second_budget(_aggregate_payload(), {"participant_role_refs": ["green"]}),
    ],
    ids=["autonomous-and-aggregate", "two-aggregates", "role-selected"],
)
def test_a_participant_is_governed_by_at_most_one_budget(payload: dict) -> None:
    message = (
        "Behavior specification 'second-budget' resource budget governs participant 'participant-agent', "
        "which behavior specification 'participant-behavior' already budgets"
    )

    assert any(message in line for line in _validation_messages(payload))


def test_specifications_of_different_participants_each_carry_a_budget() -> None:
    payload = yaml.safe_load(_mixed_control_source())
    _second_budget(payload, {"participant_refs": ["supervisor-agent"]}, participant="supervisor-agent")

    model = compile_runtime_model(parse_sdl(_source(payload)))

    assert sorted(
        specification.interaction_budget.participant_addresses
        for specification in model.behavior_specifications.values()
    ) == [("participant.behavior.red-agent",), ("participant.behavior.supervisor-agent",)]


def test_aggregate_budget_projects_into_the_canonical_demand() -> None:
    budget = _aggregate_budget()
    demands = {demand.budget_id: demand for demand in budget.resource_demands}

    assert {budget_id: demands[budget_id].resource_kind for budget_id in ("turns", "scenario-time", "tokens")} == {
        "turns": "interaction_turns",
        "scenario-time": "scenario_time",
        "tokens": "inference_tokens",
    }
    assert demands[TOOL_BUDGET].action_contract_addresses == (f"participant.action-contract.{ACTION}",)
    assert {demand.participant_disclosure_ref for demand in demands.values()} == {None}
    assert budget.clock_address == "time.clock.scenario-clock"
    assert {owner.kind for owner in budget.resource_owners} == {
        "participant",
        "deployment_tenant",
        "shared_service",
        "fleet",
    }


def test_imported_aggregate_budget_keeps_its_clock_and_owner_refs_bound(tmp_path: Path) -> None:
    payload = _aggregate_payload()
    payload["module"] = {
        "id": "example/interaction-budget-support",
        "version": "1.0.0",
        "exports": {
            "agents": ["participant-agent"],
            "behavior_specifications": [SPEC],
            "deployment_tenants": ["range-a", "range-b"],
            "infrastructure": ["customer-portal"],
            "nodes": ["customer-portal"],
            "observation_boundaries": ["participant-view"],
        },
    }
    (tmp_path / "module.yaml").write_text(_source(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        _source({"name": "imported", "imports": [{"path": "module.yaml", "namespace": "shared", "version": "1.0.0"}]}),
        encoding="utf-8",
    )

    model = compile_runtime_model(parse_sdl_file(root))
    budget = model.behavior_specifications[f"participant.behavior-specification.shared.{SPEC}"].interaction_budget

    assert budget.clock_address.startswith("time.clock.shared.")
    assert budget.participant_addresses == ("participant.behavior.shared.participant-agent",)
    assert {owner.address for owner in budget.resource_owners if owner.kind == "participant"} == {
        "participant.behavior.shared.participant-agent"
    }


def _declared(capability, **changes):
    """Declare interaction budgets in place of any unsupported declaration of the term."""

    return replace(
        capability,
        supported_behavior_features=capability.supported_behavior_features | {"interaction_budgets"},
        feature_support=(
            *(entry for entry in capability.feature_support if entry.feature != "interaction_budgets"),
            INTERACTION_BUDGET_SUPPORT,
        ),
        **changes,
    )


def _declared_stub_capabilities():
    return _declared(create_stub_target().manifest.participant_runtime, resource_budgets=_interaction_capabilities())


def test_backend_declares_interaction_budgets_with_budget_capabilities() -> None:
    capability = _declared_stub_capabilities()
    manifest = create_stub_target().manifest
    wire = backend_manifest_v2_model(
        replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    )

    assert not capability.supports_autonomous_execution
    assert BackendManifestV2Model.model_validate(wire.model_dump(mode="json")) == wire
    assert "interaction_budgets" in _evidence_required_features(schema_bundle()["backend-manifest-v2"])


def _evidence_required_features(schema: dict) -> list[str]:
    """Read the features whose participant_runtime feature_support entry must cite evidence."""

    entry = schema["$defs"]["ParticipantRuntimeCapabilitiesModel"]["properties"]["feature_support"]["items"]
    support = schema["$defs"][entry["$ref"].removeprefix("#/$defs/")]
    rule = next(rule for rule in support["allOf"] if rule["then"]["required"] == ["evidence_refs"])
    return rule["if"]["properties"]["feature"]["enum"]


def _without_evidence_declaration(capability) -> dict:
    return {
        "feature_support": tuple(item for item in capability.feature_support if item.feature != "interaction_budgets")
    }


def _without_budget_capabilities(_capability) -> dict:
    return {"resource_budgets": None}


def _without_the_feature(capability) -> dict:
    return {
        "supported_behavior_features": capability.supported_behavior_features - {"interaction_budgets"},
        "feature_support": _without_evidence_declaration(capability)["feature_support"],
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (_without_evidence_declaration, "require explicit feature_support declarations: interaction_budgets"),
        (_without_budget_capabilities, "interaction_budgets requires participant resource-budget capabilities"),
        (_without_the_feature, "autonomous execution limits require autonomous execution support"),
    ],
    ids=["no-evidence-declaration", "no-budget-capabilities", "budget-capabilities-without-the-feature"],
)
def test_interaction_budget_declaration_is_complete_and_evidence_bound(changes, message: str) -> None:
    capability = _declared_stub_capabilities()
    update = changes(capability)

    with pytest.raises(ValueError, match=message):
        replace(capability, **update)


def _interaction_budget_manifest(capabilities=None):
    manifest = _interaction_manifest(capabilities)
    runtime = _declared(manifest.participant_runtime)
    return replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=runtime))


def test_backend_with_autonomy_only_budget_support_refuses_the_aggregate_budget() -> None:
    budget = _aggregate_budget()
    autonomy_only = _interaction_manifest()
    declared = _interaction_budget_manifest()

    refused = participant_interaction_budget_gaps(autonomy_only, autonomy_only.participant_runtime, (budget,))
    admitted = participant_interaction_budget_gaps(declared, declared.participant_runtime, (budget,))

    assert refused == ["backend does not declare participant interaction budgets"]
    assert admitted == []


def test_backend_must_declare_each_interaction_kind_the_aggregate_budget_uses() -> None:
    capabilities = _interaction_capabilities()
    without_turns = replace(
        capabilities,
        supported_resource_kinds=capabilities.supported_resource_kinds - {"interaction_turns"},
        configured_pools=tuple(
            pool for pool in capabilities.configured_pools if pool.resource_kind != "interaction_turns"
        ),
    )
    manifest = _interaction_budget_manifest(without_turns)

    gaps = participant_interaction_budget_gaps(manifest, manifest.participant_runtime, (_aggregate_budget(),))

    assert gaps == ["participant resource budget turns unsupported: resource kind interaction_turns"]


def test_shared_pool_capacity_is_admitted_across_autonomous_and_aggregate_budgets() -> None:
    payload = _aggregate_payload()
    authored = payload["behavior_specifications"][SPEC]["resource_budget"]
    authored["dimensions"] = {"turns": authored["dimensions"]["turns"] | {"limit": 25}}
    authored.pop("clock_ref")
    budget = _aggregate_budget(payload)
    autonomous = compile_runtime_model(parse_sdl(_source(_payload()))).behavior_specifications[
        f"participant.behavior-specification.{SPEC}"
    ]
    manifest = _interaction_budget_manifest()

    alone = participant_interaction_budget_gaps(manifest, manifest.participant_runtime, (budget,))
    shared = participant_interaction_budget_gaps(
        manifest, manifest.participant_runtime, (budget,), (autonomous.autonomous_execution,)
    )

    # Each family fits the 40-turn pool alone; together they need 45.
    assert alone == []
    assert shared == [
        "participant resource pool participant-pool aggregate policy limits require 45; configured capacity is 40"
    ]


@pytest.mark.parametrize("declared", [False, True], ids=["stub-backend", "declaring-backend"])
def test_planner_admits_an_aggregate_budget_only_for_a_declaring_backend(declared: bool) -> None:
    model = compile_runtime_model(parse_sdl(_source(_aggregate_payload())))
    manifest = _interaction_budget_manifest() if declared else create_stub_target().manifest

    refusals = [
        diagnostic.message
        for diagnostic in plan(model, manifest).diagnostics
        if diagnostic.code == "participant.interaction-budget-unsupported"
    ]

    assert refusals == ([] if declared else ["backend does not declare participant interaction budgets"])


class _RecordingRuntime(_NativeParticipantRuntime):
    """Native runtime that keeps every admission request it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[object] = []

    def _model_action(self, request, snapshot, *, episode_id):
        self.requests.append(request)
        return super()._model_action(request, snapshot, episode_id=episode_id)


@pytest.mark.parametrize("declared", [False, True], ids=["undeclared-backend", "declared-backend"])
def test_reference_control_plane_refuses_a_manual_bypass_of_an_unrealized_budget(declared: bool) -> None:
    runtime = _RecordingRuntime()
    manager = _manager(_payload(), runtime)
    _advance_to_next_action(manager)
    request = replace(runtime.requests[-1], temporal_contexts=())
    model = compile_runtime_model(parse_sdl(_source(_aggregate_payload())))
    aggregate = model.behavior_specifications[f"participant.behavior-specification.{SPEC}"]
    manifest = _interaction_budget_manifest() if declared else _interaction_manifest()
    target = replace(create_stub_target(), manifest=manifest, participant_runtime=runtime)
    native_calls = len(runtime.native_actions)
    control = RuntimeControlPlane(
        target,
        initial_snapshot=manager.snapshot,
        behavior_specifications={aggregate.address: aggregate},
    )
    try:
        receipt = control.admit_participant_action(model.participant_behaviors[PARTICIPANT], request)
    finally:
        control.close()

    # A declaring backend realizes the budget itself; conformance then checks its evidence.
    assert receipt.accepted is declared
    assert len(runtime.native_actions) == native_calls + int(declared)


def _recorded_attempts():
    """Record two native attempts of the participant through the reference v3 scheduler."""

    manager = _manager(_payload(), _NativeParticipantRuntime())
    _advance_to_next_action(manager)
    return _advance_to_next_action(manager).snapshot


def _realized(snapshot, budget):
    """Run the budget's admission for every recorded attempt, as a realizing backend would.

    The budget admits the first attempt; shared-pool contention throttles the others.
    """

    working = initialize_participant_resource_budgets(
        snapshot, (budget,), _interaction_capabilities(), execution_generation=0
    ).snapshot
    attempts = sorted(
        {
            event["action_instance_id"]
            for event in snapshot.participant_behavior_history[PARTICIPANT]
            if event.get("event_type") == "observation_emitted"
        }
    )
    for attempt in attempts:
        working = reserve_participant_resources(working, budget, operation_id=attempt, execution_generation=0).snapshot
        working = commit_participant_resource_reservation(
            working,
            operation_id=attempt,
            execution_generation=0,
            measured_quantities={
                participant_resource_budget_state_ref(budget.address, demand.budget_id): demand.reservation
                for demand in budget.resource_demands
            },
            evidence_refs=(f"evidence:{attempt}:interaction-budget",),
        ).snapshot
    return working, attempts


def test_governed_attempts_must_carry_interaction_budget_admission() -> None:
    budget = _aggregate_budget()
    snapshot = _recorded_attempts()
    realized, attempts = _realized(snapshot, budget)

    bypassed = participant_interaction_budget_conformance_diagnostics({budget.address: budget}, snapshot)

    assert len(attempts) >= 2
    assert [diagnostic.code for diagnostic in bypassed] == [
        PARTICIPANT_INTERACTION_BUDGET_INVALID_DIAGNOSTIC_CODE
    ] * len(attempts)
    assert all("has no admission against interaction budget" in diagnostic.message for diagnostic in bypassed)
    assert participant_interaction_budget_conformance_diagnostics({budget.address: budget}, realized) == ()


def test_realized_evidence_cannot_contradict_the_compiled_budget() -> None:
    budget = _aggregate_budget()
    realized, _ = _realized(_recorded_attempts(), budget)
    states = dict(realized.participant_resource_budget_states)
    state_ref = participant_resource_budget_state_ref(budget.address, "turns")
    states[state_ref] = states[state_ref] | {"limit": 21}
    substituted = realized.with_entries(dict(realized.entries), participant_resource_budget_states=states)

    diagnostics = participant_interaction_budget_conformance_diagnostics({budget.address: budget}, substituted)

    assert [diagnostic.message for diagnostic in diagnostics] == [
        "realized budget state differs from compiled dimension 'turns' in: limit"
    ]


def _rejected(snapshot, budget, attempts):
    """Record the budget's rejection of every attempt, each asking for more turns than the limit."""

    working = initialize_participant_resource_budgets(
        snapshot, (budget,), _interaction_capabilities(), execution_generation=0
    ).snapshot
    for attempt in attempts:
        working = reserve_participant_resources(
            working, budget, operation_id=attempt, execution_generation=0, requested_quantities={"turns": 10_000}
        ).snapshot
    return working


def test_each_attempt_is_checked_against_every_governing_budget() -> None:
    budget = _aggregate_budget()
    other = replace(budget, address=f"{budget.address}-other")
    governing = {budget.address: budget, other.address: other}
    snapshot = _recorded_attempts()
    realized, attempts = _realized(snapshot, budget)

    unrecorded = participant_interaction_budget_conformance_diagnostics(governing, snapshot)
    admitted_by_one = participant_interaction_budget_conformance_diagnostics(governing, realized)
    refused_by_one = participant_interaction_budget_conformance_diagnostics(
        governing, _rejected(snapshot, budget, attempts)
    )

    # Without evidence, every attempt bypasses both budgets.
    assert len(unrecorded) == 2 * len(attempts)
    # The first budget admits only the first attempt (shared-pool contention throttles the others),
    # so that attempt alone bypasses the second budget.
    assert [diagnostic.message.split(";")[0] for diagnostic in admitted_by_one] == [
        f"attempt {attempts[0]!r} has no admission against interaction budget {other.address!r}"
    ]
    # A refusal by one governing budget stands for all of them.
    assert refused_by_one == ()


def test_traceability_table_covers_the_design_routed_invariants() -> None:
    routed = {
        invariant
        for row in _table_rows(DESIGN, "## Source-to-contract-to-test matrix")
        if "#310" in row[-1]
        for invariant in re.findall(r"EBM-\d{2}", row[0])
    }
    rows = _table_rows(SEMANTICS, "### ACT-624 Traceability")
    named = {name for row in rows for cell in row[3:] for name in re.findall(r"`(test_[a-z0-9_]+)`", cell)}
    defined = {
        node.name
        for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }

    assert routed
    assert routed <= {invariant for row in rows for invariant in re.findall(r"EBM-\d{2}", row[1])}
    assert named
    assert named <= defined
