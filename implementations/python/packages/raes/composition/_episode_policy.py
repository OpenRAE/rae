"""Participant episode-policy reference handling for module composition (DSL-120).

An imported unit's episode-policy references are renamed into the import's
namespace, while condition identifiers stay local to the policy. Before that
rename, the unit's own declaration index rejects a reset authority that the
unit alone finds ambiguous, as for behavior authority scopes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .._base import is_variable_ref
from .._reference_targetability import ReferencePurpose
from ._references import _maybe_rename

if TYPE_CHECKING:
    from .._declarations import DeclarationIndex
    from ..scenario import ScenarioContent

_EPISODE_POLICY_REF_LISTS = (
    ("assertion_refs", "assertions"),
    ("action_contract_refs", "action_contracts"),
    ("evidence_requirement_refs", "evidence_requirements"),
)
_EPISODE_POLICY_REFS = (
    ("temporal_constraint_ref", "temporal_constraints"),
    # The reset authority is any one targetable declaration.
    ("memory_reset_authority_ref", "named"),
)


def _unit_reset_authority_ambiguities(unit: ScenarioContent, index: DeclarationIndex) -> list[str]:
    """Use the standalone reset-authority purpose and diagnostic before the import is renamed."""

    errors = []
    for spec_name, behavior_spec in unit.behavior_specifications.items():
        policy = behavior_spec.episode_policy
        ref = policy.reset_policy.memory_reset_authority_ref if policy and policy.reset_policy else None
        if ref is None or is_variable_ref(ref):
            continue
        candidates = index.resolve_for(ref, ReferencePurpose.TARGETABLE)
        if len(candidates) > 1:
            errors.append(
                f"Behavior specification '{spec_name}' episode policy reset policy memory_reset_authority_ref "
                f"'{ref}' is ambiguous; use one of: {', '.join(sorted(candidates))}"
            )
    return errors


def _episode_policy_records(policy: dict[str, Any]) -> list[object]:
    records: list[object] = [
        policy.get("initialization"),
        policy.get("interaction_structure"),
        policy.get("reset_policy"),
    ]
    for field_name in ("terminal_conditions", "truncation_conditions"):
        conditions = policy.get(field_name)
        if isinstance(conditions, dict):
            records.extend(conditions.values())
    return records


def _rewrite_participant_episode_policy(
    policy: object,
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    """Rewrite episode-policy refs; condition ids stay local to the policy."""

    if not isinstance(policy, dict):
        return
    for record in _episode_policy_records(policy):
        if isinstance(record, dict):
            _rewrite_episode_policy_record(record, symbols)


def _rewrite_episode_policy_record(
    record: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    for field_name, section in _EPISODE_POLICY_REF_LISTS:
        if isinstance(record.get(field_name), list):
            record[field_name] = [_maybe_rename(str(ref), symbols[section]) for ref in record[field_name]]
    for field_name, section in _EPISODE_POLICY_REFS:
        if record.get(field_name):
            record[field_name] = _maybe_rename(str(record[field_name]), symbols[section])
