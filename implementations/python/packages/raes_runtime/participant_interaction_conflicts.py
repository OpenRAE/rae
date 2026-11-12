"""Authored interaction conflicts between participant actions that may overlap.

Two actions conflict when their compiled interaction footprints relate them or
overlap on shared state, unless both declare commutativity or the same governed
merge rule. The autonomous scheduler and hosted tool actions use one rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_processor.models import ParticipantExecutionBindingRuntime


def _related_actions_conflict(
    left: ParticipantExecutionBindingRuntime,
    right: ParticipantExecutionBindingRuntime,
) -> bool:
    left_related = set(left.related_action_contract_addresses)
    right_related = set(right.related_action_contract_addresses)
    related = right.action_contract_address in left_related or left.action_contract_address in right_related
    if not related:
        return False
    related_commutes = right.action_contract_address in set(
        left.commutative_related_action_contract_addresses
    ) and left.action_contract_address in set(right.commutative_related_action_contract_addresses)
    left_rule = dict(left.related_action_merge_rules).get(right.action_contract_address)
    right_rule = dict(right.related_action_merge_rules).get(left.action_contract_address)
    return not related_commutes and (left_rule is None or left_rule != right_rule)


def _shared_state_conflicts(
    left: ParticipantExecutionBindingRuntime,
    right: ParticipantExecutionBindingRuntime,
) -> bool:
    shared_overlap = set(left.shared_state_refs) & set(right.shared_state_refs)
    commutative_overlap = set(left.commutative_shared_state_refs) & set(right.commutative_shared_state_refs)
    left_shared_rules = dict(left.shared_state_merge_rules)
    right_shared_rules = dict(right.shared_state_merge_rules)
    authorized_rule_refs = {
        ref
        for ref in shared_overlap
        if left_shared_rules.get(ref) is not None and left_shared_rules.get(ref) == right_shared_rules.get(ref)
    }
    return bool(shared_overlap - commutative_overlap - authorized_rule_refs)


def bindings_semantically_conflict(
    left: ParticipantExecutionBindingRuntime | None,
    right: ParticipantExecutionBindingRuntime | None,
) -> bool:
    if left is None or right is None:
        return False
    return _related_actions_conflict(left, right) or _shared_state_conflicts(left, right)


__all__ = ("bindings_semantically_conflict",)
