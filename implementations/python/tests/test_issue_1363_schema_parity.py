"""#1363: Python models and every published schema give the same verdict for the rev1 shapes."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from mixed_control_rev1_scenarios import delivery_binding, legacy_scenario, rev1_delivery_scenario, rev1_policy
from mixed_control_v2_support import History
from pydantic import TypeAdapter, ValidationError
from raes.participant_behavior_specification import MixedControlDeclaration
from raes.participant_inject_delivery import ParticipantInjectDelivery
from raes_contracts.contracts import ParticipantControlOccurrenceV2Model

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = (
    "contracts/schemas/sdl/sdl-authoring-input-v1.json",
    "contracts/schemas/sdl/instantiated-scenario-v1.json",
    "contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json",
    "contracts/schemas/sdl/materialized-scenario-v1.json",
    "contracts/schemas/satisfiability/scenario-satisfiability-evidence-v1.json",
)
V2_SCHEMA = "contracts/schemas/participant-runtime/participant-control-occurrence-v2.json"


@cache
def _schema(path: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def _validator(path: str, definition: str, prop: str | None = None) -> Draft202012Validator:
    schema = _schema(path)
    root = schema["$defs"][definition]
    fragment = root["properties"][prop] if prop else {"$ref": f"#/$defs/{definition}"}
    return Draft202012Validator({"$defs": schema["$defs"], **fragment})


def _python_accepts(validate: Callable[[Any], object], value: Any) -> bool:
    try:
        validate(value)
    except ValidationError:
        return False
    return True


def _legacy() -> dict[str, Any]:
    return legacy_scenario()["behavior_specifications"]["controlled-red"]["mixed_control"]


def _edges(policy: dict[str, Any]) -> dict[str, Any]:
    return policy["permitted_transitions"]


def _add_edge(kind: str, **fields: Any) -> Callable[[dict], None]:
    def mutate(policy: dict) -> None:
        source = _edges(policy)["approve"]
        _edges(policy)["extra"] = {**source, "transition_kind": kind, **fields}

    return mutate


MIXED_CONTROL_CASES: list[tuple[str, Callable[[], dict], Callable[[dict], None] | None, bool]] = [
    ("legacy", _legacy, None, True),
    ("reusable", rev1_policy, None, True),
    ("finite", lambda: rev1_policy(form="finite-script"), None, True),
    ("absent-semantics", rev1_policy, lambda p: p.pop("semantics"), False),
    ("semantics-on-legacy", _legacy, lambda p: p.update(semantics="mixed-control-policy-occurrence/rev1"), False),
    ("unknown-semantics", rev1_policy, lambda p: p.update(semantics="mixed-control-policy-occurrence/rev9"), False),
    ("missing-form", rev1_policy, lambda p: p.pop("form"), False),
    ("unknown-form", rev1_policy, lambda p: p.update(form="open-script"), False),
    (
        "reusable-with-steps",
        rev1_policy,
        lambda p: p.update(script_steps=[{"step_id": "h1", "permitted_transition_ref": "take"}]),
        False,
    ),
    ("finite-without-steps", lambda: rev1_policy(form="finite-script"), lambda p: p.pop("script_steps"), False),
    ("finite-empty-steps", lambda: rev1_policy(form="finite-script"), lambda p: p.update(script_steps=[]), False),
    *(
        (
            f"finite-window-{field}-{other}",
            lambda: rev1_policy(form="finite-script"),
            lambda p, field=field, other=other: p["script_steps"][0].update({field: 3, **other}),
            False,
        )
        for field, other in (
            ("valid_from_order", {}),
            ("valid_until_order", {}),
            ("valid_from_order", {"valid_until_order": None}),
            ("valid_until_order", {"valid_from_order": None}),
        )
    ),
    (
        "finite-complete-window",
        lambda: rev1_policy(form="finite-script"),
        lambda p: p["script_steps"][0].update(valid_from_order=3, valid_until_order=8),
        True,
    ),
    *(
        (
            f"map-key-{form}-{field}-{key}",
            build,
            lambda p, field=field, key=key, value=value: p[field].update({key: value}),
            False,
        )
        for form, build, transition_field in (
            ("rev1", rev1_policy, "permitted_transitions"),
            ("legacy", _legacy, "transitions"),
        )
        for field in ("controller_states", transition_field)
        for key, value in (("_bad", None), ("-bad", 42))
    ),
    ("direction-no-kinds", rev1_policy, lambda p: _edges(p)["direct"].pop("target_kinds"), False),
    ("direction-empty-kinds", rev1_policy, lambda p: _edges(p)["direct"].update(target_kinds=[]), False),
    (
        "direction-duplicate-kinds",
        rev1_policy,
        lambda p: _edges(p)["direct"].update(target_kinds=["proposal", "proposal"]),
        False,
    ),
    ("direction-attempt-kind", rev1_policy, lambda p: _edges(p)["direct"].update(target_kinds=["attempt"]), False),
    *(
        (f"{kind}-with-kinds", rev1_policy, _add_edge(kind, target_kinds=["control"]), False)
        for kind in ("intervention", "override", "cancellation", "proposal", "approval", "denial")
    ),
    (
        "handoff-with-kinds",
        rev1_policy,
        lambda p: _edges(p)["take"].update(target_kinds=["control"]),
        False,
    ),
    ("handoff-without-completion", rev1_policy, lambda p: _edges(p)["take"].pop("completion_evidence_refs"), False),
    ("bound-overflow", rev1_policy, lambda p: _edges(p)["take"].update(valid_until_order=1_000_001), False),
]


@pytest.mark.parametrize("schema_path", SCHEMAS)
@pytest.mark.parametrize(
    ("case", "build", "mutate", "valid"), MIXED_CONTROL_CASES, ids=[case[0] for case in MIXED_CONTROL_CASES]
)
def test_mixed_control_python_and_published_schema_verdicts_agree(schema_path, case, build, mutate, valid) -> None:
    value = copy.deepcopy(build())
    if mutate is not None:
        mutate(value)
    validator = _validator(schema_path, "ParticipantBehaviorSpecification", "mixed_control")
    adapter = TypeAdapter(MixedControlDeclaration)
    assert _python_accepts(adapter.validate_python, value) is valid, case
    assert validator.is_valid(value) is valid, case


DELIVERY_CASES = [
    ("control-block", None, True),
    ("disclosure-with-control", lambda b: b.update(delivery_kind="disclosure"), False),
    ("direction-without-control", lambda b: b.pop("control"), False),
    ("direction-with-null-control", lambda b: b.update(control=None), False),
    ("control-block-blank-scope", lambda b: b["control"].update(authority_scope_refs=[" "]), False),
    ("control-block-blank-evidence", lambda b: b["control"].update(evidence_refs=[" "]), False),
    ("control-and-flat-ref", lambda b: b.update(control_transition_ref="direct-briefing"), False),
    ("control-and-flat-scope", lambda b: b.update(control_authority_scope_refs=["nodes.web"]), False),
    ("control-and-flat-order", lambda b: b.update(control_effective_order=11), False),
    ("control-and-empty-flat-list", lambda b: b.update(control_evidence_refs=[]), True),
    ("control-block-extra", lambda b: b["control"].update(expected_state_revision=1), False),
    ("control-block-empty-scope", lambda b: b["control"].update(authority_scope_refs=[]), False),
]


@pytest.mark.parametrize("schema_path", SCHEMAS)
@pytest.mark.parametrize(("case", "mutate", "valid"), DELIVERY_CASES, ids=[case[0] for case in DELIVERY_CASES])
def test_delivery_control_block_exclusivity_agrees_across_python_and_schema(schema_path, case, mutate, valid) -> None:
    binding = copy.deepcopy(delivery_binding(rev1_delivery_scenario()))
    if mutate is not None:
        mutate(binding)
    validator = _validator(schema_path, "ParticipantInjectDelivery")
    assert _python_accepts(ParticipantInjectDelivery.model_validate, binding) is valid, case
    assert validator.is_valid(binding) is valid, case


def _decision(edge: str) -> Callable[[], dict[str, Any]]:
    def build() -> dict[str, Any]:
        history = History()
        history.accept("propose")
        history.accept("take")
        return history.accepted_payload(edge, proposal_ref="proposal-1")

    return build


_approval = _decision("approve")
_denial = _decision("deny")


def _set(payload: dict, path: tuple, value: Any) -> dict:
    target = payload
    for key in path[:-1]:
        target = target[key]
    if value is _DROP:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return payload


_DROP = object()
V2_CASES = [
    ("accepted", lambda: History().accepted_payload("take"), (), None, True),
    ("rejected", lambda: History().rejected_payload("take", "stale-policy"), (), None, True),
    (
        "rejected-without-ref",
        lambda: History().rejected_payload("take", "stale-policy"),
        ("occurrence", "attempted", "permitted_transition_ref"),
        _DROP,
        False,
    ),
    (
        "position-zero",
        lambda: History().rejected_payload("take", "stale-policy"),
        ("occurrence", "occurrence_revision"),
        0,
        False,
    ),
    (
        "position-overflow",
        lambda: History().rejected_payload("take", "stale-policy"),
        ("occurrence", "occurrence_revision"),
        1_000_001,
        False,
    ),
    (
        "proposal-own-revision-2",
        lambda: History().accepted_payload("propose"),
        ("occurrence", "proposal_revision"),
        2,
        False,
    ),
    (
        "proposal-own-revision-true",
        lambda: History().accepted_payload("propose"),
        ("occurrence", "proposal_revision"),
        True,
        False,
    ),
    ("approval-own-revision-2", _approval, ("occurrence", "decision_revision"), 2, False),
    ("approval-own-revision-true", _approval, ("occurrence", "decision_revision"), True, False),
    ("denial", _denial, (), None, True),
    ("denial-own-revision-true", _denial, ("occurrence", "decision_revision"), True, False),
    ("approval-cites-revision-2", _approval, ("occurrence", "proposal_revision"), 2, True),
    ("accepted-no-from", lambda: History().accepted_payload("take"), ("occurrence", "valid_from_order"), _DROP, False),
    (
        "accepted-no-until",
        lambda: History().accepted_payload("take"),
        ("occurrence", "valid_until_order"),
        _DROP,
        False,
    ),
    (
        "bound-overflow",
        lambda: History().accepted_payload("take"),
        ("occurrence", "valid_until_order"),
        1_000_001,
        False,
    ),
    ("bound-boolean", lambda: History().accepted_payload("take"), ("occurrence", "valid_until_order"), True, False),
    ("bound-string", lambda: History().accepted_payload("take"), ("occurrence", "valid_until_order"), "1000", False),
    (
        "rejected-with-bound",
        lambda: History().rejected_payload("take", "stale-policy"),
        ("occurrence", "valid_from_order"),
        0,
        False,
    ),
]


@pytest.mark.parametrize(("case", "build", "path", "value", "valid"), V2_CASES, ids=[case[0] for case in V2_CASES])
def test_v2_carrier_python_and_published_schema_verdicts_agree(case, build, path, value, valid) -> None:
    payload = build()
    if path:
        _set(payload, path, value)
    validator = Draft202012Validator(_schema(V2_SCHEMA))
    assert _python_accepts(ParticipantControlOccurrenceV2Model.model_validate, payload) is valid, case
    assert validator.is_valid(payload) is valid, case
