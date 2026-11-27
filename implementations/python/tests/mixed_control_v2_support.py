"""Shared builders for #1363 rev1 policy projections and API-409 v2 occurrence histories.

The edge set mirrors the #1351 bounded model (``test_issue_1351_mixed_control_design.EDGES``),
so differential tests can drive both with the same attempt sequences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from raes_contracts.contracts import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    ParticipantControlOccurrencePolicyModel,
    ParticipantControlOccurrenceV2Model,
    participant_control_validity_bounds,
)

PARTICIPANT = "participant.behavior.red-agent"
SUPERVISOR = "participant.behavior.supervisor-agent"
EPISODE = "episode-1"
SPEC = "participant.behavior-specification.controlled-red"
POLICY_REF = f"{SPEC}.mixed-control-policy"
SCOPE = "provision.node.web"
STATES = {"A": f"{SPEC}.controller-state.autonomous", "B": f"{SPEC}.controller-state.supervised"}
CONTROLLERS = {"A": PARTICIPANT, "B": SUPERVISOR}
BASES = {"A": "entities.red-team", "B": "entities.blue-team"}
EDGES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "take": ("handoff", "A", "B", ()),
    "return": ("handoff", "B", "A", ()),
    "propose": ("proposal", "A", "A", ()),
    "approve": ("approval", "B", "B", ("proposal",)),
    "deny": ("denial", "B", "B", ("proposal",)),
    "direct": ("external-direction", "B", "B", ("proposal", "action", "control")),
    "intervene": ("intervention", "B", "B", ("action", "control", "attempt")),
    "override": ("override", "B", "B", ("control", "decision")),
    "cancel": ("cancellation", "B", "B", ("proposal", "decision", "admitted-action", "attempt")),
}


def edge_ref(name: str) -> str:
    return f"{SPEC}.permitted-transition.{name}"


def step_ref(name: str) -> str:
    return f"{SPEC}.script-step.{name}"


def state_payload(name: str, *, status: str = "active", window: tuple[int, int] = (0, 1000)) -> dict[str, Any]:
    return {
        "state_ref": STATES[name],
        "controller_ref": CONTROLLERS[name],
        "authority_basis_refs": [BASES[name]],
        "scope_refs": [SCOPE],
        "authority_status": status,
        "valid_from_order": window[0],
        "valid_until_order": window[1],
    }


def transition_payload(name: str, *, window: tuple[int, int] = (0, 1000)) -> dict[str, Any]:
    kind, source, destination, targets = EDGES[name]
    return {
        "transition_ref": edge_ref(name),
        "kind": kind,
        "from_state_ref": STATES[source],
        "to_state_ref": STATES[destination],
        "valid_from_order": window[0],
        "valid_until_order": window[1],
        "target_kinds": list(targets),
    }


def policy(
    *,
    form: str = "reusable-policy",
    steps: list[dict[str, Any]] | None = None,
    states: list[dict[str, Any]] | None = None,
    transitions: list[dict[str, Any]] | None = None,
    episode: str = EPISODE,
    **changes: Any,
) -> ParticipantControlOccurrencePolicyModel:
    payload = {
        "semantics": "mixed-control-policy-occurrence/rev1",
        "participant_address": PARTICIPANT,
        "episode_id": episode,
        "pin": {"behavior_specification_ref": SPEC, "policy_ref": POLICY_REF, "policy_revision": "1.0.0", "form": form},
        "order_strategy": "total-effective-order",
        "initial_state_ref": STATES["A"],
        "behavior_scope_refs": [SCOPE],
        "states": states or [state_payload("A"), state_payload("B")],
        "transitions": transitions or [transition_payload(name) for name in EDGES],
        "script_steps": steps or [],
        **changes,
    }
    return ParticipantControlOccurrencePolicyModel.model_validate(payload)


def script_step(name: str, edge: str, **narrowing: Any) -> dict[str, Any]:
    return {"step_ref": step_ref(name), "transition_ref": edge_ref(edge), **narrowing}


def _kind_fields(kind: str, position: int) -> dict[str, Any]:
    defaults: dict[str, dict[str, Any]] = {
        "proposal": {
            "proposal_id": f"proposal-{position}",
            "proposal_revision": 1,
            "admission_status": "not-admitted",
            "action_contract_ref": "participant.action-contract.contain",
            "payload_digest": "sha256:" + "a" * 64,
        },
        "approval": {"proposal_revision": 1, "decision_ref": f"decision-{position}", "decision_revision": 1},
        "denial": {"proposal_revision": 1, "decision_ref": f"decision-{position}", "decision_revision": 1},
        "intervention": {"intervention_ref": f"intervention-{position}"},
        "handoff": {"completion_evidence_ref": f"evidence.completion-{position}"},
        "override": {"replacement_ref": f"replacement-{position}"},
    }
    return dict(defaults.get(kind, {}))


def envelope(position: int, controller: str, occurrence: dict[str, Any], *, episode: str, **changes: Any) -> dict:
    payload = {
        "event_id": f"participant-control.{episode}.{position}",
        "schema_name": "participant-control-occurrence",
        "schema_version": "2.0.0",
        "event_type": "participant-control-occurrence",
        "extension_policy": "closed",
        "participant_address": PARTICIPANT,
        "episode_id": episode,
        "occurred_at": "2026-10-13T00:00:00Z",
        "recorded_at": "2026-10-13T00:00:01Z",
        "ingested_at": "2026-10-13T00:00:02Z",
        "clock_authority": "runtime.control-plane.clock",
        "ordering_basis": "logical_clock",
        "actor_ref": controller,
        "producer_ref": "runtime.control-plane.test",
        "provenance_refs": ["provenance:test"],
        "evidence_refs": ["evidence:test"],
        "object_marking_refs": ["marking:participant-control"],
        "authorization_scope": SCOPE,
        "semantics": "mixed-control-policy-occurrence/rev1",
        "policy": {
            "behavior_specification_ref": SPEC,
            "policy_ref": POLICY_REF,
            "policy_revision": "1.0.0",
            "form": "reusable-policy",
        },
        "occurrence": occurrence,
    }
    payload.update(changes)
    return payload


@dataclass
class History:
    """Build exact v2 histories at the trusted cut; ``candidate`` builds without appending."""

    projection: ParticipantControlOccurrencePolicyModel = field(default_factory=policy)
    episode: str = EPISODE
    start: int = 0
    records: list[ParticipantControlOccurrenceV2Model] = field(default_factory=list)
    state: str = "A"
    revision: int = 0
    last_order: int | None = None
    cursor: int = 0

    @property
    def position(self) -> int:
        return self.start + len(self.records) + 1

    def accepted_payload(self, edge: str, *, step: str | None = None, **fields: Any) -> dict[str, Any]:
        kind, source, destination, _ = EDGES[edge]
        position = self.position
        order = fields.pop("effective_order", (self.last_order or 0) + 10)
        bounds = participant_control_validity_bounds(self.projection, edge_ref(edge), step_ref(step) if step else None)
        occurrence = {
            "disposition": "accepted",
            "permitted_transition_ref": edge_ref(edge),
            "kind": kind,
            "prior_state_ref": STATES[self.state],
            "expected_state_revision": self.revision,
            "resulting_state_ref": STATES[destination],
            "resulting_state_revision": self.revision + 1,
            "expected_history_head": position - 1,
            "occurrence_revision": position,
            "controller_ref": CONTROLLERS[source],
            "authority_basis_refs": [BASES[source]],
            "controlled_scope_refs": [SCOPE],
            "effective_order": order,
            "valid_from_order": bounds[0] if bounds else 0,
            "valid_until_order": bounds[1] if bounds else 0,
            "limitation_refs": ["limitation.not-admitted"],
            **({"script_step_ref": step_ref(step)} if step else {}),
            **_kind_fields(kind, position),
        }
        envelope_changes = fields.pop("envelope", {})
        occurrence.update(fields)
        return envelope(
            position,
            occurrence["controller_ref"],
            occurrence,
            episode=self.episode,
            policy={**_pin(self.projection)},
            **envelope_changes,
        )

    def candidate(self, edge: str, **fields: Any) -> ParticipantControlOccurrenceV2Model:
        return ParticipantControlOccurrenceV2Model.model_validate(self.accepted_payload(edge, **fields))

    def accept(self, edge: str, **fields: Any) -> ParticipantControlOccurrenceV2Model:
        record = self.candidate(edge, **fields)
        self.records.append(record)
        occurrence = record.occurrence
        self.state = EDGES[edge][2]
        self.revision += 1
        self.last_order = occurrence.effective_order
        self.cursor += int(self.projection.pin.form == "finite-script")
        return record

    def rejected_payload(self, edge: str, reason: str, **attempt: Any) -> dict[str, Any]:
        kind, source, _, _ = EDGES.get(edge, ("handoff", self.state, self.state, ()))
        position = self.position
        observed = attempt.pop("observed", {})
        occurrence = {
            "disposition": "rejected",
            "occurrence_revision": position,
            "reason_code": reason,
            "attempted": {
                "permitted_transition_ref": edge_ref(edge),
                "kind": kind,
                "state_ref": STATES[self.state],
                "expected_state_revision": self.revision,
                "effective_order": (self.last_order or 0) + 10,
                "expected_history_head": position - 1,
                "controller_ref": CONTROLLERS[source],
                "authority_basis_refs": [BASES[source]],
                "controlled_scope_refs": [SCOPE],
                **attempt,
            },
            "observed": {
                "state_ref": STATES[self.state],
                "state_revision": self.revision,
                "last_accepted_order": self.last_order,
                "history_head": position - 1,
                **observed,
            },
            "state_change": "none",
            "limitation_refs": ["limitation.not-admitted"],
        }
        controller = occurrence["attempted"]["controller_ref"]
        return envelope(position, controller, occurrence, episode=self.episode, policy={**_pin(self.projection)})

    def reject(self, edge: str, reason: str, **attempt: Any) -> ParticipantControlOccurrenceV2Model:
        record = ParticipantControlOccurrenceV2Model.model_validate(self.rejected_payload(edge, reason, **attempt))
        self.records.append(record)
        return record


def _pin(projection: ParticipantControlOccurrencePolicyModel) -> dict[str, Any]:
    return projection.pin.model_dump(mode="json")


V1_DECLARATION_REF = "participant.behavior-specification.legacy-red.control-transition.propose"


def v1_record(position: int, *, episode: str = "episode-0") -> ParticipantControlOccurrenceModel:
    """One accepted v1 proposal of the same participant, under its fixed-coordinate declaration."""

    return ParticipantControlOccurrenceModel.model_validate(
        {
            **{
                key: value
                for key, value in envelope(position, PARTICIPANT, {}, episode=episode).items()
                if key not in {"semantics", "policy", "occurrence"}
            },
            "schema_version": "1.0.0",
            "occurrence": {
                "declaration_ref": V1_DECLARATION_REF,
                "kind": "proposal",
                "controller_ref": PARTICIPANT,
                "controller_state_ref": STATES["A"],
                "authority_basis_refs": [BASES["A"]],
                "controlled_scope_refs": [SCOPE],
                "behavior_specification_ref": "participant.behavior-specification.legacy-red",
                "mixed_control_policy_ref": "participant.behavior-specification.legacy-red",
                "policy_revision": "1.0.0",
                "expected_state_revision": 0,
                "effective_order": 10,
                "valid_from_order": 0,
                "valid_until_order": 10,
                "occurrence_revision": position,
                "disposition": "accepted",
                "limitation_refs": ["limitation.not-admitted"],
                "proposal_id": f"legacy-proposal-{position}",
                "proposal_revision": 1,
                "admission_status": "not-admitted",
                "action_contract_ref": "participant.action-contract.contain",
                "payload_digest": "sha256:" + "a" * 64,
            },
        }
    )


def v1_declaration(*, episode: str = "episode-0") -> ParticipantControlDeclarationModel:
    return ParticipantControlDeclarationModel.model_validate(
        {
            "declaration_ref": V1_DECLARATION_REF,
            "kind": "proposal",
            "participant_address": PARTICIPANT,
            "episode_id": episode,
            "controller_ref": PARTICIPANT,
            "controller_state_ref": STATES["A"],
            "authority_basis_refs": [BASES["A"]],
            "controlled_scope_refs": [SCOPE],
            "behavior_specification_ref": "participant.behavior-specification.legacy-red",
            "mixed_control_policy_ref": "participant.behavior-specification.legacy-red",
            "policy_revision": "1.0.0",
            "expected_state_revision": 0,
            "effective_order": 10,
            "valid_from_order": 0,
            "valid_until_order": 10,
        }
    )
