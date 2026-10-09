"""Participant episode policy reference validation (DSL-120).

Every reference an authored episode policy makes must resolve to an existing
closed SDL declaration of the right kind and role, and the policy must be the
only one that governs each participant it selects. Nothing here evaluates a
condition or observes an episode; realized episode state stays on the ADR-013
contracts. Checks that depend on a participant selection or reference that is
still a ``${var}`` wait for the post-instantiation validation pass.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..participant_episode_policy import ParticipantEpisodeTimeoutCondition
from ..propositions import AssertionRole
from ..semantics.participant_behavior import select_participants
from ..time_model import TemporalConstraintKind

_DECLARATION_INDEX_REQUIRED = "declaration index must be built before reference validation"
# Constraint kinds that bound elapsed shared time, so their expiry can be a
# timeout. Precedence and cadence constrain order or rhythm, not a limit.
_TIMEOUT_CONSTRAINT_KINDS = frozenset(
    {
        TemporalConstraintKind.DEADLINE,
        TemporalConstraintKind.WINDOW,
        TemporalConstraintKind.DURATION,
    }
)
# Initialization constrains the start boundary of each episode generation;
# terminal and truncation conditions constrain its end boundary.
_INITIALIZATION_ROLES = frozenset({AssertionRole.PRECONDITION})
_CLOSURE_ROLES = frozenset({AssertionRole.INVARIANT, AssertionRole.POSTCONDITION})


@dataclass(frozen=True)
class _EpisodeOwner:
    """The behavior specification that owns a policy and the participants it selects."""

    spec_name: str
    behavior_spec: object
    participants: frozenset[str]
    selection_resolved: bool


class _ParticipantEpisodePoliciesMixin:
    def _verify_participant_episode_policies(self) -> None:
        if self._declaration_index is None:
            raise RuntimeError(_DECLARATION_INDEX_REQUIRED)
        governed = [
            (str(spec_name), behavior_spec)
            for spec_name, behavior_spec in self._s.behavior_specifications.items()
            if behavior_spec.episode_policy is not None
        ]
        if not governed:
            return
        roles = self._participant_roles_by_agent()
        owners = [self._episode_owner(spec_name, behavior_spec, roles) for spec_name, behavior_spec in governed]
        for owner in owners:
            self._verify_episode_policy(owner)
        self._verify_one_episode_policy_per_participant(owners)

    def _episode_owner(self, spec_name: str, behavior_spec: object, roles: dict[str, str]) -> _EpisodeOwner:
        role_selected = bool(behavior_spec.participant_role_refs)
        unresolved = any(self._is_unresolved_var(ref) for ref in behavior_spec.participant_refs) or (
            role_selected
            and any(self._is_unresolved_var(ref) for ref in (*behavior_spec.participant_role_refs, *roles.values()))
        )
        participants = frozenset(select_participants(behavior_spec, set(self._s.agents), roles))
        return _EpisodeOwner(spec_name, behavior_spec, participants, selection_resolved=not unresolved)

    def _verify_one_episode_policy_per_participant(self, owners: list[_EpisodeOwner]) -> None:
        # Realized ADR-013 episodes are keyed by participant, so a participant whose
        # episodes two policies govern would have no single authored structure.
        governing: dict[str, list[str]] = {}
        for owner in owners:
            for participant in owner.participants:
                governing.setdefault(participant, []).append(owner.spec_name)
        for participant, spec_names in sorted(governing.items()):
            if len(spec_names) > 1:
                joined = ", ".join(f"'{name}'" for name in sorted(spec_names))
                self._err(
                    f"Participant '{participant}' is governed by more than one episode policy "
                    f"(behavior specifications {joined})"
                )

    def _verify_episode_policy(self, owner: _EpisodeOwner) -> None:
        policy = owner.behavior_spec.episode_policy
        label = f"Behavior specification '{owner.spec_name}' episode policy"
        if policy.initialization is not None:
            self._verify_episode_assertions(
                f"{label} initialization",
                policy.initialization.assertion_refs,
                _INITIALIZATION_ROLES,
                "a precondition",
            )
        if policy.interaction_structure is not None:
            self._verify_episode_turn_actions(label, owner, policy.interaction_structure.action_contract_refs)
        for condition_id, condition in policy.terminal_conditions.items():
            condition_label = f"{label} terminal condition '{condition_id}'"
            if isinstance(condition, ParticipantEpisodeTimeoutCondition):
                self._verify_episode_timeout(condition_label, condition.temporal_constraint_ref, owner)
            else:
                self._verify_closure_assertions(condition_label, condition.assertion_refs)
            self._verify_episode_evidence(condition_label, condition.evidence_requirement_refs)
        for condition_id, condition in policy.truncation_conditions.items():
            condition_label = f"{label} truncation condition '{condition_id}'"
            self._verify_closure_assertions(condition_label, condition.assertion_refs)
            self._verify_episode_evidence(condition_label, condition.evidence_requirement_refs)
        if policy.reset_policy is not None:
            self._verify_episode_evidence(f"{label} reset policy", policy.reset_policy.evidence_requirement_refs)

    def _verify_closure_assertions(self, label: str, refs: Iterable[str]) -> None:
        self._verify_episode_assertions(label, refs, _CLOSURE_ROLES, "an invariant or postcondition")

    def _verify_episode_assertions(
        self,
        label: str,
        refs: Iterable[str],
        roles: frozenset[AssertionRole],
        role_label: str,
    ) -> None:
        for ref in refs:
            if self._is_unresolved_var(ref):
                continue
            assertion = self._s.assertions.get(ref)
            if assertion is None:
                self._err(f"{label} assertion '{ref}' not in assertions section")
            elif assertion.role not in roles:
                self._err(f"{label} assertion '{ref}' must be {role_label}")

    def _verify_episode_turn_actions(self, label: str, owner: _EpisodeOwner, refs: Iterable[str]) -> None:
        spec_actions = owner.behavior_spec.action_contract_refs
        spec_actions_resolved = not any(self._is_unresolved_var(ref) for ref in spec_actions)
        for ref in refs:
            if self._is_unresolved_var(ref):
                continue
            ref_label = f"{label} interaction_structure action_contract_ref '{ref}'"
            if spec_actions_resolved and ref not in spec_actions:
                self._err(f"{ref_label} is outside the owning behavior specification")
            for participant in sorted(owner.participants):
                actions = self._s.agents[participant].actions
                if ref not in actions and not any(self._is_unresolved_var(action) for action in actions):
                    self._err(f"{ref_label} is outside participant '{participant}'")

    def _verify_episode_timeout(self, label: str, ref: str, owner: _EpisodeOwner) -> None:
        if self._is_unresolved_var(ref):
            return
        constraint = self._s.temporal_constraints.get(ref)
        if constraint is None:
            self._err(f"{label} temporal_constraint_ref '{ref}' does not reference a declared temporal constraint")
            return
        if constraint.constraint_kind not in _TIMEOUT_CONSTRAINT_KINDS:
            self._err(f"{label} temporal_constraint_ref '{ref}' must be a deadline, window, or duration constraint")
        if not owner.selection_resolved or any(self._is_unresolved_var(subject) for subject in constraint.subject_refs):
            return
        subjects: set[str] = set()
        for subject in constraint.subject_refs:
            subjects |= self._declaration_index.resolve(subject)
        if not self._timeout_binds_owner(owner, subjects):
            self._err(
                f"{label} temporal_constraint_ref '{ref}' binds neither the owning behavior specification "
                "nor every participant it selects"
            )

    def _timeout_binds_owner(self, owner: _EpisodeOwner, subjects: set[str]) -> bool:
        # A timeout applies to every selected participant's episode, so its clock limit
        # must bind the specification itself or each of those participants.
        if self._declaration_index.resolve(f"behavior_specifications.{owner.spec_name}") & subjects:
            return True
        return bool(owner.participants) and all(
            self._declaration_index.resolve(f"agents.{participant}") & subjects for participant in owner.participants
        )

    def _verify_episode_evidence(self, label: str, refs: Iterable[str]) -> None:
        for ref in refs:
            if self._is_unresolved_var(ref):
                continue
            if ref not in self._s.evidence_requirements:
                self._err(
                    f"{label} evidence_requirement_ref '{ref}' does not reference a declared evidence requirement"
                )
