"""Exact security-fact joins shared by API-424's versioned context validators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .participant_control_composition import control_digest
from .participant_control_coordinates import ParticipantControlContextModel
from .participant_control_results import ControlOwnerSecurityFactModel, ControlSecurityFactModel
from .participant_flow_control import ParticipantFlowControlRelationModel, ParticipantFlowSinkDecisionModel
from .participant_flow_control_validation import validate_participant_flow_control_context

if TYPE_CHECKING:
    from .participant_control_resolution import ParticipantControlValidationContext


def _security_sink_matches(
    decision: ParticipantFlowSinkDecisionModel,
    decision_ids: set[str],
    fact: ControlSecurityFactModel,
    cut: ParticipantControlContextModel,
) -> bool:
    return (
        decision.decision_id in decision_ids
        and (
            not isinstance(fact, ControlOwnerSecurityFactModel)
            or (decision.decision_id == fact.sink_decision_ref and decision.final_disposition == fact.sink_disposition)
        )
        and decision.label_ref == fact.label_ref
        and (decision.sink.sink_ref, decision.sink.destination_ref, decision.sink.audience_scope_ref)
        == (cut.sink_ref, cut.destination_ref, cut.audience_ref)
        and set(decision.expected_history_head_refs) == {head.ref for head in cut.expected_history_heads}
    )


def _validate_security_sink(
    relation: ParticipantFlowControlRelationModel, fact: ControlSecurityFactModel, cut: ParticipantControlContextModel
) -> None:
    # The IFC subject may be a derived action argument, whereas the API-423
    # subject is its enclosing control occurrence. Follow the incumbent
    # typed carrier relation instead of conflating these identities.
    decision_ids = {
        binding.relation_target.target_ref
        for binding in relation.bindings
        if binding.kind == "participant-crossing"
        and binding.event_id == cut.crossing.ref
        and binding.relation_target.target_kind == "sink-decision"
    }
    if not any(_security_sink_matches(decision, decision_ids, fact, cut) for decision in relation.sink_decisions):
        raise ValueError("security fact has no exact crossing and sink binding")


def _validate_security_fact(
    fact: ControlSecurityFactModel, cut: ParticipantControlContextModel, context: ParticipantControlValidationContext
) -> None:
    relation = context.flow_relations.get(fact.relation.ref)
    flow_context = context.flow_contexts.get(fact.relation.ref)
    if relation is None or flow_context is None or control_digest(relation) != fact.relation.digest:
        raise ValueError("security fact requires its exact incumbent relation and context")
    if isinstance(fact, ControlOwnerSecurityFactModel):
        if (relation.profile.profile_id, relation.profile.profile_revision, relation.profile.profile_digest) != (
            fact.profile.ref,
            fact.profile.revision,
            fact.profile.digest,
        ):
            raise ValueError("owner security fact profile differs from its owning relation")
    elif relation.profile.profile_id != "participant-boundary-flow-policy-v1":
        raise ValueError("legacy security fact cannot substitute an owner-aware profile")
    validate_participant_flow_control_context(relation, flow_context)
    label = next((label for label in relation.labels if label.label_id == fact.label_ref), None)
    if label is None or label.resolution_status != "resolved":
        raise ValueError("security fact label does not resolve")
    if (relation.document_id, relation.document_revision) != (fact.relation.ref, fact.relation.revision):
        raise ValueError("security relation identity differs")
    _validate_security_sink(relation, fact, cut)
    for name in (
        "policy_id",
        "policy_revision",
        "policy_digest",
        "policy_decision_ref",
        "decision_cut_ref",
        "effective_order",
    ):
        if getattr(label.policy, name) != getattr(cut.policy, name):
            raise ValueError("security fact exact policy cut differs")
