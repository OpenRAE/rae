"""ACT-617 authored and compiled mixed-control participant semantics."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from raes._errors import SDLParseError, SDLValidationError
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl, parse_sdl_file
from raes.participant_behavior_specification import MixedControlTransitionKind
from raes_processor.compiler import compile_runtime_model

REPO_ROOT = Path(__file__).resolve().parents[3]


def _scenario_yaml(*, mode: str = "mixed-control", include_declaration: bool = True) -> str:
    declaration = ""
    if include_declaration:
        declaration = textwrap.indent(
            textwrap.dedent(
                """
                mixed_control:
                  participant_ref: red-agent
                  policy_revision: 1.0.0
                  order_strategy: total-effective-order
                  initial_state_ref: autonomous
                  dispositions:
                    duplicate: idempotent-if-equivalent
                    stale: reject-no-state-change
                    revoked: reject-no-state-change
                    late: reject-no-state-change
                    concurrent: order-then-revalidate
                    conflict: reject-no-state-change
                  controller_states:
                    autonomous:
                      controller_ref: self
                      authority_basis_refs: [entities.red-team]
                      scope_refs: [nodes.web]
                      policy_revision: 1.0.0
                      valid_from_order: 0
                      valid_until_order: 10
                      authority_status: active
                      evidence_refs: [entities.red-team]
                    pending:
                      controller_ref: self
                      authority_basis_refs: [entities.red-team]
                      scope_refs: [nodes.web]
                      policy_revision: 1.0.0
                      valid_from_order: 10
                      valid_until_order: 11
                      authority_status: active
                      evidence_refs: [entities.red-team]
                    supervised:
                      controller_ref: supervisor-agent
                      authority_basis_refs: [entities.blue-team]
                      scope_refs: [nodes.web]
                      policy_revision: 1.0.0
                      valid_from_order: 10
                      valid_until_order: 99
                      authority_status: active
                      evidence_refs: [entities.blue-team]
                  transitions:
                    propose_supervision:
                      transition_kind: proposal
                      from_state_ref: autonomous
                      to_state_ref: pending
                      policy_revision: 1.0.0
                      expected_state_revision: 0
                      resulting_state_revision: 1
                      effective_order: 10
                      valid_from_order: 0
                      valid_until_order: 10
                      evidence_refs: [entities.red-team]
                    approve_supervision:
                      transition_kind: approval
                      from_state_ref: pending
                      to_state_ref: supervised
                      policy_revision: 1.0.0
                      expected_state_revision: 1
                      resulting_state_revision: 2
                      effective_order: 11
                      valid_from_order: 0
                      valid_until_order: 11
                      proposal_ref: propose_supervision
                      proposal_revision: 1
                      evidence_refs: [entities.blue-team]
            """
            ).strip(),
            "    ",
        )
        declaration += "\n"
    return (
        textwrap.dedent(
            f"""
        name: act-617
        nodes:
          web:
            type: compute
            resources: {{ram: 1 GiB, cpu: 1}}
          internal:
            type: compute
            resources: {{ram: 1 GiB, cpu: 1}}
        entities:
          red-team:
            role: red
          blue-team:
            role: blue
        agents:
          red-agent:
            affiliations: [red-team]
            authority_anchors: [entities.red-team]
            operating_scope: [nodes.web]
          supervisor-agent:
            affiliations: [blue-team]
            authority_anchors: [entities.blue-team]
            operating_scope: [nodes.web]
        behavior_specifications:
          controlled-red:
            semantic_version: 1.0.0
            participant_refs: [red-agent]
            authority_scope_refs: [nodes.web]
            behavior_mode: {mode}
            extension_policy: closed
        """
        )
        + declaration
    )


def test_mixed_control_declaration_parses_as_closed_typed_state_and_transitions() -> None:
    scenario = parse_sdl(_scenario_yaml())

    declaration = scenario.behavior_specifications["controlled-red"].mixed_control
    assert declaration is not None
    assert declaration.participant_ref == "red-agent"
    assert declaration.initial_state_ref == "autonomous"
    assert declaration.controller_states["supervised"].controller_ref == "supervisor-agent"
    assert declaration.transitions["propose_supervision"].transition_kind.value == "proposal"
    assert declaration.transitions["approve_supervision"].proposal_ref == "propose_supervision"


def test_mixed_control_mapping_keys_accept_portable_hyphenated_identifiers() -> None:
    scenario = parse_sdl(
        _scenario_yaml()
        .replace("autonomous", "autonomous-mode")
        .replace("propose_supervision", "propose-supervision")
        .replace("approve_supervision", "approve-supervision")
    )

    declaration = scenario.behavior_specifications["controlled-red"].mixed_control
    assert declaration is not None
    assert declaration.initial_state_ref == "autonomous-mode"
    assert "propose-supervision" in declaration.transitions


def test_mixed_control_mode_requires_explicit_declaration() -> None:
    scenario = _scenario_yaml(include_declaration=False)
    with pytest.raises(SDLValidationError, match="mixed-control mode requires mixed_control"):
        parse_sdl(scenario)


def test_mixed_control_declaration_requires_matching_mode() -> None:
    scenario = _scenario_yaml(mode="autonomous")
    with pytest.raises(SDLValidationError, match="mixed_control requires behavior_mode mixed-control"):
        parse_sdl(scenario)


def test_mixed_control_is_not_hidden_in_raw_compiler_metadata() -> None:
    scenario = parse_sdl(_scenario_yaml())

    compiled = compile_runtime_model(scenario).behavior_specifications[
        "participant.behavior-specification.controlled-red"
    ]
    assert compiled.controller_states
    assert compiled.control_transitions


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "participant_ref: red-agent",
            "participant_ref: supervisor-agent",
            "must bind exactly one participant_ref owned by the behavior specification",
        ),
        (
            "controller_ref: supervisor-agent",
            "controller_ref: blue",
            "controller_ref 'blue' must reference a declared agent or self",
        ),
        (
            "authority_basis_refs: [entities.blue-team]",
            "authority_basis_refs: [entities.red-team]",
            "authority basis 'entities.red-team' is not declared by controller 'supervisor-agent'",
        ),
        (
            "scope_refs: [nodes.web]\n          policy_revision: 1.0.0\n          valid_from_order: 10",
            "scope_refs: [nodes.internal]\n          policy_revision: 1.0.0\n          valid_from_order: 10",
            "scope_ref 'nodes.internal' widens the behavior specification authority scope",
        ),
        (
            "evidence_refs: [entities.blue-team]",
            "evidence_refs: [entities.missing]",
            "evidence_ref 'entities.missing' does not reference any defined element",
        ),
    ],
)
def test_mixed_control_controller_authority_and_scope_fail_closed(old: str, new: str, message: str) -> None:
    scenario = _scenario_yaml().replace(old, new, 1)
    with pytest.raises(SDLValidationError, match=message):
        parse_sdl(scenario)


def test_mixed_control_rejects_transitions_from_revoked_authority() -> None:
    scenario = _scenario_yaml()
    marker = "authority_status: active"
    pending_marker = scenario.index(marker, scenario.index(marker) + len(marker))
    scenario = scenario[:pending_marker] + scenario[pending_marker:].replace(marker, "authority_status: revoked", 1)

    with pytest.raises(SDLValidationError, match="transition 'approve_supervision' starts from revoked authority"):
        parse_sdl(scenario)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("proposal_revision: 1", "proposal_revision: 9", "stale proposal revision"),
        (
            "expected_state_revision: 1\n          resulting_state_revision: 2",
            "expected_state_revision: 0\n          resulting_state_revision: 1",
            "revision 0 is not established for controller state 'pending'",
        ),
        ("effective_order: 11", "effective_order: 10", "unique effective_order"),
    ],
)
def test_mixed_control_stale_and_ambiguous_decisions_fail_closed(old: str, new: str, message: str) -> None:
    scenario = _scenario_yaml().replace(old, new, 1)
    with pytest.raises(SDLParseError, match=message):
        parse_sdl(scenario)


def test_mixed_control_handoff_requires_controller_change_and_completion_evidence() -> None:
    scenario = _scenario_yaml().replace("transition_kind: approval", "transition_kind: handoff", 1)

    with pytest.raises(SDLParseError, match="handoff transitions require completion_evidence_refs"):
        parse_sdl(scenario)


def test_mixed_control_handoff_records_controller_change_and_completion_evidence() -> None:
    scenario = (
        _scenario_yaml()
        .replace("transition_kind: approval", "transition_kind: handoff", 1)
        .replace(
            "proposal_revision: 1\n          evidence_refs: [entities.blue-team]\n",
            "proposal_revision: 1\n          evidence_refs: [entities.blue-team]\n"
            "          completion_evidence_refs: [entities.blue-team]\n",
            1,
        )
    )

    declaration = parse_sdl(scenario).behavior_specifications["controlled-red"].mixed_control
    assert declaration is not None
    handoff = declaration.transitions["approve_supervision"]
    assert handoff.transition_kind.value == "handoff"
    assert handoff.completion_evidence_refs == ["entities.blue-team"]


def test_mixed_control_dispositions_are_explicit_and_fail_closed() -> None:
    declaration = parse_sdl(_scenario_yaml()).behavior_specifications["controlled-red"].mixed_control
    assert declaration is not None
    assert declaration.dispositions.duplicate.value == "idempotent-if-equivalent"
    assert declaration.dispositions.stale.value == "reject-no-state-change"
    assert declaration.dispositions.revoked.value == "reject-no-state-change"
    assert declaration.dispositions.late.value == "reject-no-state-change"
    assert declaration.dispositions.concurrent.value == "order-then-revalidate"
    assert declaration.dispositions.conflict.value == "reject-no-state-change"


def test_control_fact_kinds_remain_distinct_from_admission_execution_and_observation() -> None:
    assert {kind.value for kind in MixedControlTransitionKind} == {
        "proposal",
        "approval",
        "denial",
        "external-direction",
        "intervention",
        "handoff",
        "override",
        "cancellation",
    }


@pytest.mark.parametrize(("expected", "resulting"), [(1, 1), (3, 2), (3, 3)])
def test_control_transitions_always_advance_state_revision(expected: int, resulting: int) -> None:
    scenario = _scenario_yaml().replace(
        "expected_state_revision: 0\n          resulting_state_revision: 1",
        f"expected_state_revision: {expected}\n          resulting_state_revision: {resulting}",
        1,
    )

    with pytest.raises(SDLParseError, match="must advance state revision"):
        parse_sdl(scenario)


def test_mixed_control_initial_state_revision_starts_at_zero() -> None:
    scenario = _scenario_yaml().replace(
        "expected_state_revision: 0\n          resulting_state_revision: 1",
        "expected_state_revision: 4\n          resulting_state_revision: 5",
        1,
    )

    with pytest.raises(SDLParseError, match="revision 4 is not established for controller state 'autonomous'"):
        parse_sdl(scenario)


def test_mixed_control_state_revision_advances_exactly_once_per_transition() -> None:
    scenario = _scenario_yaml().replace(
        "expected_state_revision: 0\n          resulting_state_revision: 1",
        "expected_state_revision: 0\n          resulting_state_revision: 2",
        1,
    )

    with pytest.raises(SDLParseError, match="advance state revision by exactly one"):
        parse_sdl(scenario)


def test_mixed_control_non_proposal_transition_requires_established_state_revision() -> None:
    scenario = (
        _scenario_yaml()
        .replace("transition_kind: approval", "transition_kind: intervention", 1)
        .replace(
            "expected_state_revision: 1\n          resulting_state_revision: 2",
            "expected_state_revision: 9\n          resulting_state_revision: 10",
            1,
        )
        .replace("          proposal_ref: propose_supervision\n          proposal_revision: 1\n", "", 1)
    )

    with pytest.raises(SDLParseError, match="revision 9 is not established for controller state 'pending'"):
        parse_sdl(scenario)


def test_compiler_preserves_typed_control_addresses_order_dependencies_and_provenance() -> None:
    compiled = compile_runtime_model(parse_sdl(_scenario_yaml())).behavior_specifications[
        "participant.behavior-specification.controlled-red"
    ]

    assert compiled.mixed_control_participant_address == "participant.behavior.red-agent"
    assert compiled.mixed_control_policy_revision == "1.0.0"
    assert compiled.mixed_control_order_strategy == "total-effective-order"
    assert compiled.mixed_control_initial_state_address.endswith(".controller-state.autonomous")
    assert [state.state_id for state in compiled.controller_states] == ["autonomous", "pending", "supervised"]
    assert [transition.transition_id for transition in compiled.control_transitions] == [
        "propose_supervision",
        "approve_supervision",
    ]
    approval = compiled.control_transitions[1]
    assert approval.proposal_address.endswith(".control-transition.propose_supervision")
    assert approval.from_state_address.endswith(".controller-state.pending")
    assert approval.to_state_address.endswith(".controller-state.supervised")
    assert "provision.node.web" in compiled.refresh_dependencies
    assert compiled.spec["mixed_control"]["policy_revision"] == "1.0.0"


def test_instantiation_preserves_mixed_control_meaning_before_compilation() -> None:
    instantiated = instantiate_scenario(parse_sdl(_scenario_yaml()))
    declaration = instantiated.behavior_specifications["controlled-red"].mixed_control

    assert declaration is not None
    assert declaration.participant_ref == "red-agent"
    assert declaration.transitions["approve_supervision"].expected_state_revision == 1
    compiled = compile_runtime_model(instantiated).behavior_specifications[
        "participant.behavior-specification.controlled-red"
    ]
    assert compiled.control_transitions[1].resulting_state_revision == 2


def test_module_composition_rewrites_external_control_refs_but_keeps_local_state_ids(tmp_path: Path) -> None:
    imported = tmp_path / "mixed.yaml"
    imported.write_text(
        _scenario_yaml().replace(
            "name: act-617",
            textwrap.dedent(
                """
                name: act-617
                module:
                  id: acme/mixed-control
                  version: 1.0.0
                  exports:
                    nodes: [web, internal]
                    entities: [red-team, blue-team]
                    agents: [red-agent, supervisor-agent]
                    behavior_specifications: [controlled-red]
                """
            ).strip(),
            1,
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - source: local:mixed.yaml\n    namespace: shared\n",
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    declaration = scenario.behavior_specifications["shared.controlled-red"].mixed_control
    assert declaration is not None
    assert declaration.participant_ref == "shared.red-agent"
    assert declaration.controller_states["autonomous"].authority_basis_refs == ["entities.shared.red-team"]
    assert declaration.controller_states["supervised"].controller_ref == "shared.supervisor-agent"
    assert declaration.controller_states["supervised"].scope_refs == ["nodes.shared.web"]
    assert declaration.initial_state_ref == "autonomous"
    assert declaration.transitions["approve_supervision"].proposal_ref == "propose_supervision"


def test_published_valid_and_invalid_sdl_fixtures_exercise_mixed_control_boundary() -> None:
    valid = REPO_ROOT / "contracts/fixtures/sdl/mixed-control-v1/valid/mixed-control-participant.yaml"
    invalid = REPO_ROOT / "contracts/fixtures/sdl/mixed-control-v1/invalid/mixed-control-operator-impersonation.yaml"

    scenario = parse_sdl_file(valid)
    assert scenario.behavior_specifications["controlled-red"].mixed_control is not None
    with pytest.raises(SDLValidationError, match="controller_ref 'blue' must reference a declared agent or self"):
        parse_sdl_file(invalid)


@pytest.mark.parametrize(
    "schema_path",
    [
        "contracts/schemas/sdl/sdl-authoring-input-v1.json",
        "contracts/schemas/sdl/instantiated-scenario-v1.json",
        "contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json",
    ],
)
def test_published_sdl_schemas_are_closed_and_include_mixed_control(schema_path: str) -> None:
    schema = json.loads((REPO_ROOT / schema_path).read_text(encoding="utf-8"))
    behavior = schema["$defs"]["ParticipantBehaviorSpecification"]
    mixed_control = schema["$defs"]["MixedControlParticipantOperation"]

    assert behavior["additionalProperties"] is False
    assert behavior["properties"]["mixed_control"]["anyOf"][0]["$ref"].endswith("/MixedControlParticipantOperation")
    assert mixed_control["additionalProperties"] is False
    assert set(mixed_control["required"]) == {
        "participant_ref",
        "policy_revision",
        "order_strategy",
        "initial_state_ref",
        "dispositions",
        "controller_states",
        "transitions",
    }
