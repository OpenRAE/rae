"""#1363: legacy fixed-coordinate mixed control converts to a rev1 finite script, or refuses explicitly."""

from __future__ import annotations

import copy
from functools import cache
from itertools import product
from typing import Any

import pytest
import yaml
from mixed_control_rev1_scenarios import legacy_scenario, rev1_scenario
from mixed_control_v2_support import envelope
from raes.canonical import canonical_sdl_digest
from raes.mixed_control_migration import migrate_mixed_control_to_finite_script
from raes.parser import parse_sdl
from raes_contracts.contracts import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    ParticipantControlOccurrenceV2Model,
    fold_participant_control_episode_v2,
    participant_control_validity_bounds,
    validate_participant_control_occurrence_context,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler._mixed_control_policy import occurrence_policy_projection
from test_dsl_142_participant_inject_delivery import _external_direction_yaml

SPEC = "participant.behavior-specification.controlled-red"
POINTER = "/behavior_specifications/controlled-red/mixed_control/transitions/"
CONTROLLERS = {"self": "red-team", "supervisor-agent": "blue-team"}


def _state(controller: str, **changes: Any) -> dict[str, Any]:
    team = CONTROLLERS[controller]
    return {
        "controller_ref": controller,
        "authority_basis_refs": [f"entities.{team}"],
        "scope_refs": ["nodes.web"],
        "policy_revision": "1.0.0",
        "valid_from_order": 0,
        "valid_until_order": 1000,
        "authority_status": "active",
        "evidence_refs": [f"entities.{team}"],
        **changes,
    }


def _legacy(states: dict[str, dict], transitions: list[tuple]) -> dict[str, Any]:
    """Transitions are (id, kind, from, to, expected revision, order, proposal ref or None)."""

    payload = legacy_scenario()
    declaration = payload["behavior_specifications"]["controlled-red"]["mixed_control"]
    declaration["controller_states"] = states
    declaration["initial_state_ref"] = next(iter(states))
    resulting = {item[0]: item[4] + 1 for item in transitions}
    declaration["transitions"] = {}
    for transition_id, kind, source, destination, expected, order, proposal in transitions:
        team = CONTROLLERS[states[source]["controller_ref"]]
        entry = {
            "transition_kind": kind,
            "from_state_ref": source,
            "to_state_ref": destination,
            "policy_revision": "1.0.0",
            "expected_state_revision": expected,
            "resulting_state_revision": expected + 1,
            "effective_order": order,
            "valid_from_order": 0,
            "valid_until_order": 1000,
            "evidence_refs": [f"entities.{team}"],
        }
        if kind == "handoff":
            entry["completion_evidence_refs"] = [f"entities.{CONTROLLERS[states[destination]['controller_ref']]}"]
        if proposal is not None:
            entry.update(proposal_ref=proposal, proposal_revision=resulting[proposal])
        declaration["transitions"][transition_id] = entry
    return payload


def _source(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, sort_keys=False)


HANDOFF_CHAIN = _legacy(
    {"autonomous": _state("self"), "supervised": _state("supervisor-agent")},
    [
        ("take", "handoff", "autonomous", "supervised", 0, 10, None),
        ("return", "handoff", "supervised", "autonomous", 1, 20, None),
    ],
)
DECISION_CHAIN = _legacy(
    {"autonomous": _state("self"), "pending": _state("self")},
    [
        ("propose-one", "proposal", "autonomous", "pending", 0, 10, None),
        ("approve-one", "approval", "pending", "autonomous", 1, 20, "propose-one"),
        ("propose-two", "proposal", "autonomous", "pending", 2, 30, None),
        ("direct-two", "external-direction", "pending", "autonomous", 3, 40, "propose-two"),
    ],
)
CANCEL_CHAIN = _legacy(
    {"autonomous": _state("self"), "pending": _state("self")},
    [
        ("propose", "proposal", "autonomous", "pending", 0, 10, None),
        ("cancel", "cancellation", "pending", "autonomous", 1, 20, "propose"),
    ],
)


def _transitions(payload: dict[str, Any]) -> dict[str, dict]:
    return payload["behavior_specifications"]["controlled-red"]["mixed_control"]["transitions"]


@cache
def _legacy_spec(source: str):
    return compile_runtime_model(parse_sdl(source)).behavior_specifications[SPEC]


def _legacy_accepts(payload: dict[str, Any], attempts: tuple[str, ...]) -> bool:
    """v1 oracle: RUN-310's replay rule plus the v1 contextual owner over the accepted records."""

    spec = _legacy_spec(_source(payload))
    compiled = {item.transition_id: item for item in spec.control_transitions}
    states = {item.address: item for item in spec.controller_states}
    current, revision = spec.mixed_control_initial_state_address, 0
    records: list[ParticipantControlOccurrenceModel] = []
    declarations = []
    for position, edge in enumerate(attempts, start=1):
        transition = compiled[edge]
        if (transition.from_state_address, transition.expected_state_revision) != (current, revision):
            return False
        state = states[transition.from_state_address]
        record, declaration = _v1_record(spec, transition, state, position, records)
        records.append(record)
        declarations.append(declaration)
        validate_participant_control_occurrence_context(records, declarations=declarations)
        current, revision = transition.to_state_address, transition.resulting_state_revision
    return True


def _v1_record(spec, transition, state, position: int, earlier: list) -> tuple:
    common = {
        "declaration_ref": transition.address,
        "kind": transition.transition_kind,
        "controller_ref": state.controller_address,
        "controller_state_ref": state.address,
        "authority_basis_refs": list(state.authority_basis_addresses or state.authority_basis_refs),
        "controlled_scope_refs": list(state.scope_addresses or state.scope_refs),
        "behavior_specification_ref": spec.address,
        "mixed_control_policy_ref": spec.address,
        "policy_revision": transition.policy_revision,
        "expected_state_revision": transition.expected_state_revision,
        "effective_order": transition.effective_order,
        "valid_from_order": transition.valid_from_order,
        "valid_until_order": transition.valid_until_order,
    }
    proposals = {item.occurrence.declaration_ref: item for item in earlier if item.occurrence.kind == "proposal"}
    linked = proposals.get(transition.proposal_address)
    detail: dict[str, Any] = {}
    if transition.transition_kind == "proposal":
        detail = {
            "proposal_id": f"proposal-{position}",
            "proposal_revision": transition.resulting_state_revision,
            "admission_status": "not-admitted",
            "action_contract_ref": "action",
            "payload_digest": "sha256:" + "a" * 64,
        }
    elif transition.transition_kind in {"approval", "denial"}:
        detail = {
            "proposal_ref": linked.occurrence.proposal_id,
            "proposal_revision": transition.proposal_revision,
            "decision_ref": f"decision-{position}",
            "decision_revision": 1,
        }
    elif transition.transition_kind in {"external-direction", "cancellation"}:
        detail = {
            "target_kind": "proposal",
            "target_ref": linked.occurrence.proposal_id,
            "target_revision": transition.proposal_revision,
            **({"cancellation_effect": "prevented"} if transition.transition_kind == "cancellation" else {}),
        }
    elif transition.transition_kind == "handoff":
        detail = {
            "prior_controller_state_ref": state.address,
            "resulting_controller_state_ref": transition.to_state_address,
            "resulting_state_revision": transition.resulting_state_revision,
            "completion_evidence_ref": f"completion-{position}",
        }
    base = envelope(
        position,
        state.controller_address,
        {},
        episode="episode-1",
        event_id=f"legacy-control.{position}",
        participant_address=spec.mixed_control_participant_address,
        predecessor_event_refs=[linked.event_id] if linked is not None else [],
    )
    record = {
        **{key: value for key, value in base.items() if key not in {"semantics", "policy", "occurrence"}},
        "schema_version": "1.0.0",
        "occurrence": {
            **common,
            "occurrence_revision": position,
            "disposition": "accepted",
            "limitation_refs": ["limitation"],
            **detail,
        },
    }
    declaration = ParticipantControlDeclarationModel.model_validate(
        {**common, "participant_address": spec.mixed_control_participant_address, "episode_id": "episode-1"}
    )
    return ParticipantControlOccurrenceModel.model_validate(record), declaration


def _v2_accepts(projection, attempts: tuple[str, ...], *, stop_code: list | None = None) -> bool:
    """v2 entry point over the converted finite script, with coordinates the current state implies."""

    edges = {item.transition_ref.rsplit(".", 1)[-1]: item for item in projection.transitions}
    states = {item.state_ref: item for item in projection.states}
    current, revision, last_order, cursor = projection.initial_state_ref, 0, None, 0
    records: list[ParticipantControlOccurrenceV2Model] = []
    produced: dict[str, str] = {}
    for position, edge in enumerate(attempts, start=1):
        transition = edges[edge]
        step = next(item for item in projection.script_steps if item.transition_ref == transition.transition_ref)
        payload = _v2_payload(projection, transition, step, states[current], position, revision, produced)
        try:
            record = ParticipantControlOccurrenceV2Model.model_validate(payload)
        except ValueError:
            return False
        result = fold_participant_control_episode_v2([*records, record], policy=projection)
        if result.violation is not None:
            if stop_code is not None:
                stop_code.append(result.violation)
            return False
        records.append(record)
        produced[step.step_ref] = getattr(record.occurrence, "proposal_id", "")
        current, revision, last_order, cursor = transition.to_state_ref, revision + 1, step.valid_from_order, cursor + 1
    return True


def _v2_payload(projection, transition, step, source, position: int, revision: int, produced: dict) -> dict:
    kind = transition.kind.value
    bounds = participant_control_validity_bounds(projection, transition.transition_ref, step.step_ref) or (0, 0)
    detail: dict[str, Any] = {}
    proposal = produced.get(step.target_step_ref or "", "missing-proposal")
    if kind == "proposal":
        detail = {
            "proposal_id": f"proposal-{position}",
            "proposal_revision": 1,
            "admission_status": "not-admitted",
            "action_contract_ref": "action",
            "payload_digest": "sha256:" + "a" * 64,
        }
    elif kind in {"approval", "denial"}:
        detail = {
            "proposal_ref": proposal,
            "proposal_revision": 1,
            "decision_ref": f"decision-{position}",
            "decision_revision": 1,
        }
    elif kind in {"external-direction", "cancellation"}:
        detail = {"target_kind": "proposal", "target_ref": proposal, "target_revision": 1}
    elif kind == "handoff":
        detail = {"completion_evidence_ref": f"completion-{position}"}
    occurrence = {
        "disposition": "accepted",
        "permitted_transition_ref": transition.transition_ref,
        "kind": kind,
        "prior_state_ref": source.state_ref,
        "expected_state_revision": revision,
        "resulting_state_ref": transition.to_state_ref,
        "resulting_state_revision": revision + 1,
        "expected_history_head": position - 1,
        "occurrence_revision": position,
        "controller_ref": source.controller_ref,
        "authority_basis_refs": source.authority_basis_refs,
        "controlled_scope_refs": source.scope_refs,
        "effective_order": step.valid_from_order,
        "valid_from_order": bounds[0],
        "valid_until_order": bounds[1],
        "script_step_ref": step.step_ref,
        "limitation_refs": ["limitation"],
        **detail,
    }
    return envelope(
        position,
        source.controller_ref,
        occurrence,
        episode=projection.episode_id,
        event_id=f"control.{position}",
        participant_address=projection.participant_address,
        policy=projection.pin.model_dump(mode="json"),
    )


def _converted_projection(payload: dict[str, Any]):
    result = migrate_mixed_control_to_finite_script(_source(payload))
    assert result.succeeded, [(item.code, item.address) for item in result.report.diagnostics]
    spec = compile_runtime_model(result.output).behavior_specifications[SPEC]
    return occurrence_policy_projection(spec, episode_id="episode-1"), result


@pytest.mark.parametrize("chain", [HANDOFF_CHAIN, DECISION_CHAIN, CANCEL_CHAIN], ids=["handoff", "decisions", "cancel"])
def test_bounded_differential_between_the_legacy_oracle_and_the_converted_script(chain: dict) -> None:
    projection, _ = _converted_projection(chain)
    edges = list(_transitions(chain))
    accepted = set()
    for length in range(1, len(edges) + 2):
        for attempts in product(edges, repeat=length):
            legacy = _legacy_accepts(chain, attempts)
            assert legacy == _v2_accepts(projection, attempts), attempts
            if legacy:
                accepted.add(attempts)
    assert accepted == {tuple(edges[:length]) for length in range(1, len(edges) + 1)}


def test_the_1351_witness_survives_conversion() -> None:
    projection, _ = _converted_projection(HANDOFF_CHAIN)
    assert _legacy_accepts(HANDOFF_CHAIN, ("take", "return"))
    assert _v2_accepts(projection, ("take", "return"))
    violations: list[str] = []
    assert not _v2_accepts(projection, ("take", "return", "take"), stop_code=violations)
    assert violations == ["accepted participant control occurrence fails script-exhausted"]
    assert not _legacy_accepts(HANDOFF_CHAIN, ("take", "return", "take"))


def test_conversion_reports_proposal_revisions_as_affected_identities() -> None:
    _, result = _converted_projection(DECISION_CHAIN)
    assert result.report.affected_identities == (
        f"{POINTER}approve-one/proposal_revision",
        f"{POINTER}direct-two/proposal_revision",
    )
    policy = result.output.behavior_specifications["controlled-red"].mixed_control
    assert policy.form == "finite-script"
    assert policy.permitted_transitions["direct-two"].target_kinds == ["proposal"]
    assert [(step.step_id, step.target_step_ref) for step in policy.script_steps] == [
        ("propose-one", None),
        ("approve-one", "propose-one"),
        ("propose-two", None),
        ("direct-two", "propose-two"),
    ]


def test_rev1_input_comes_back_unchanged() -> None:
    source = _source(rev1_scenario())
    result = migrate_mixed_control_to_finite_script(source)
    assert result.succeeded
    assert result.report.target_digest == canonical_sdl_digest(parse_sdl(source)).value
    assert result.output == parse_sdl(source)


def _revoked_target() -> dict:
    payload = copy.deepcopy(HANDOFF_CHAIN)
    states = payload["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]
    states["supervised"]["authority_status"] = "revoked"
    _transitions(payload).pop("return")
    return payload


def _link_case(second_kind: str, *, siblings: bool) -> dict:
    expected = 1 if siblings else 2
    return _legacy(
        {"autonomous": _state("self"), "pending": _state("self"), "decided": _state("self")},
        [
            ("propose", "proposal", "autonomous", "pending", 0, 10, None),
            ("approve", "approval", "pending", "decided", 1, 20, "propose"),
            ("second", second_kind, "pending" if siblings else "decided", "autonomous", expected, 30, "propose"),
        ],
    )


def _same_controller_handoff() -> dict:
    payload = copy.deepcopy(HANDOFF_CHAIN)
    states = payload["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]
    states["supervised"] = _state("self", controller_ref="red-agent")
    _transitions(payload)["take"]["completion_evidence_refs"] = ["entities.red-team"]
    _transitions(payload).pop("return")
    return payload


def _branching() -> dict:
    payload = copy.deepcopy(HANDOFF_CHAIN)
    _transitions(payload)["take-again"] = {**_transitions(payload)["take"], "effective_order": 30}
    return payload


def _intervention_with_proposal() -> dict:
    return _legacy(
        {"autonomous": _state("self"), "pending": _state("self")},
        [
            ("propose", "proposal", "autonomous", "pending", 0, 10, None),
            ("intervene", "intervention", "pending", "autonomous", 1, 20, "propose"),
        ],
    )


def _directed_delivery() -> dict:
    return yaml.safe_load(_external_direction_yaml())


DELIVERY = "/behavior_specifications/red-briefing/participant_inject_deliveries/briefing"
REFUSALS = [
    ("canonical", legacy_scenario, {("controller-change-requires-handoff", f"{POINTER}approve_supervision")}),
    ("same-controller-handoff", _same_controller_handoff, {("handoff-without-controller-change", f"{POINTER}take")}),
    ("branching", _branching, {("branching-sequence", f"{POINTER}take-again")}),
    ("outside-kind-set", _intervention_with_proposal, {("proposal-target-outside-kind-set", f"{POINTER}intervene")}),
    (
        "directed-delivery",
        _directed_delivery,
        {
            (
                "controller-change-requires-handoff",
                "/behavior_specifications/red-briefing/mixed_control/transitions/direct-briefing",
            ),
            ("order-time-mapping-required", DELIVERY),
            ("policy-revision-conflated", DELIVERY),
            ("source-destination-authority-disagreement", DELIVERY),
        },
    ),
    ("revoked-target", _revoked_target, {("source-or-target-invalid", f"{POINTER}take")}),
    *(
        (
            f"decided-then-{kind}",
            lambda kind=kind: _link_case(kind, siblings=False),
            {("source-or-target-invalid", f"{POINTER}second")},
        )
        for kind in ("external-direction", "denial", "cancellation")
    ),
    *(
        (
            f"sibling-{kind}",
            lambda kind=kind: _link_case(kind, siblings=True),
            {("branching-sequence", f"{POINTER}second")},
        )
        for kind in ("external-direction", "denial", "cancellation")
    ),
]


@pytest.mark.parametrize(("case", "build", "expected"), REFUSALS, ids=[item[0] for item in REFUSALS])
def test_every_applicable_refusal_is_reported_with_its_pointer(case: str, build, expected: set) -> None:
    result = migrate_mixed_control_to_finite_script(_source(build()))
    assert not result.succeeded, case
    assert result.output is None
    assert result.report.target_digest is None
    reported = {
        (item.code.removeprefix("mixed-control-migration."), item.address) for item in result.report.diagnostics
    }
    assert expected <= reported, reported
    assert all(code in {item[0] for item in expected} for code, _ in reported), reported


def test_source_that_fails_legacy_validation_is_refused_without_partial_output() -> None:
    payload = copy.deepcopy(HANDOFF_CHAIN)
    _transitions(payload)["return"]["expected_state_revision"] = 7
    _transitions(payload)["return"]["resulting_state_revision"] = 8
    result = migrate_mixed_control_to_finite_script(_source(payload))
    assert not result.succeeded
    assert result.output is None
    assert {item.code for item in result.report.diagnostics} == {"mixed-control-migration.source-or-target-invalid"}
