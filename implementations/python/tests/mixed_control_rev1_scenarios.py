"""Shared #1363 SDL scenarios that author the rev1 mixed-control form.

They reuse the ACT-617 and DSL-142 fixtures' participants, scope and evidence so
the rev1 cases differ from the incumbent ones only in the authored policy form.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml
from raes.parser import parse_sdl
from test_act_617_mixed_control import _scenario_yaml as act_617_yaml
from test_dsl_142_participant_inject_delivery import _external_direction_yaml

SEMANTICS = "mixed-control-policy-occurrence/rev1"
DISPOSITIONS = {
    "duplicate": "idempotent-if-equivalent",
    "stale": "reject-no-state-change",
    "revoked": "reject-no-state-change",
    "late": "reject-no-state-change",
    "concurrent": "order-then-revalidate",
    "conflict": "reject-no-state-change",
}


def controller_state(controller: str, team: str, *, window: tuple[int, int] = (0, 1000), **changes: Any) -> dict:
    return {
        "controller_ref": controller,
        "authority_basis_refs": [f"entities.{team}"],
        "scope_refs": ["nodes.web"],
        "policy_revision": "1.0.0",
        "valid_from_order": window[0],
        "valid_until_order": window[1],
        "authority_status": "active",
        "evidence_refs": [f"entities.{team}"],
        **changes,
    }


def edge(kind: str, source: str, destination: str, team: str, **changes: Any) -> dict:
    payload: dict[str, Any] = {
        "transition_kind": kind,
        "from_state_ref": source,
        "to_state_ref": destination,
        "valid_from_order": 0,
        "valid_until_order": 1000,
        "evidence_refs": [f"entities.{team}"],
    }
    if kind == "handoff":
        payload["completion_evidence_refs"] = [f"entities.{'blue-team' if team == 'red-team' else 'red-team'}"]
    if kind == "external-direction":
        payload["target_kinds"] = ["proposal", "action", "control"]
    payload.update(changes)
    return payload


def rev1_policy(*, form: str = "reusable-policy", steps: list[dict] | None = None) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "semantics": SEMANTICS,
        "form": form,
        "participant_ref": "red-agent",
        "policy_revision": "1.0.0",
        "order_strategy": "total-effective-order",
        "initial_state_ref": "autonomous",
        "dispositions": dict(DISPOSITIONS),
        "controller_states": {
            "autonomous": controller_state("self", "red-team"),
            "supervised": controller_state("supervisor-agent", "blue-team"),
        },
        "permitted_transitions": {
            "take": edge("handoff", "autonomous", "supervised", "red-team"),
            "return": edge("handoff", "supervised", "autonomous", "blue-team"),
            "propose": edge("proposal", "autonomous", "autonomous", "red-team"),
            "approve": edge("approval", "supervised", "supervised", "blue-team"),
            "direct": edge("external-direction", "supervised", "supervised", "blue-team"),
        },
    }
    if form == "finite-script":
        policy["script_steps"] = steps or [
            {"step_id": "h1", "permitted_transition_ref": "take"},
            {"step_id": "h2", "permitted_transition_ref": "return"},
        ]
    return policy


def rev1_scenario(*, form: str = "reusable-policy", steps: list[dict] | None = None) -> dict[str, Any]:
    payload = yaml.safe_load(act_617_yaml(include_declaration=False))
    payload["behavior_specifications"]["controlled-red"]["mixed_control"] = rev1_policy(form=form, steps=steps)
    return payload


def legacy_scenario() -> dict[str, Any]:
    return yaml.safe_load(act_617_yaml())


def rev1_policy_of(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["behavior_specifications"]["controlled-red"]["mixed_control"]


def parse(payload: dict[str, Any]):
    return parse_sdl(yaml.safe_dump(copy.deepcopy(payload), sort_keys=False))


def rev1_delivery_scenario() -> dict[str, Any]:
    """The DSL-142 external-direction scenario with a rev1 policy and nested control block."""

    payload = yaml.safe_load(_external_direction_yaml())
    spec = payload["behavior_specifications"]["red-briefing"]
    spec["mixed_control"] = {
        **{key: value for key, value in rev1_policy().items() if key != "permitted_transitions"},
        "controller_states": {
            "autonomous": controller_state("self", "red-team", window=(0, 99)),
            "directed": controller_state("supervisor-agent", "blue-team", window=(0, 99)),
        },
        "permitted_transitions": {
            "take": edge("handoff", "autonomous", "directed", "red-team"),
            "direct-briefing": edge("external-direction", "directed", "directed", "blue-team"),
        },
    }
    binding = spec["participant_inject_deliveries"]["briefing"]
    for field in [name for name in binding if name.startswith("control") or name == "controller_ref"]:
        del binding[field]
    binding["control"] = {
        "semantics": SEMANTICS,
        "policy_revision": "1.0.0",
        "permitted_transition_ref": "direct-briefing",
        "controller_ref": "supervisor-agent",
        "authority_scope_refs": ["nodes.web"],
        "evidence_refs": ["entities.blue-team"],
    }
    return payload


def delivery_binding(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["behavior_specifications"]["red-briefing"]["participant_inject_deliveries"]["briefing"]
