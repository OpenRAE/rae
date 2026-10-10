"""Semantic validation for proposition, assertion, and probe references."""

from .._reference_targetability import ReferencePurpose
from ..propositions import AssertionRole


class _PropositionsMixin:
    def _verify_propositions_and_assertions(self) -> None:
        self._verify_proposition_refs()
        self._verify_assertion_refs()
        self._verify_condition_proposition_refs()

    def _verify_proposition_refs(self) -> None:
        for name, proposition in self._s.propositions.items():
            label = f"Proposition '{name}'"
            for subject in proposition.subjects:
                if not self._is_unresolved_var(subject):
                    self._validate_named_ref(
                        subject,
                        owner_label=label,
                        ref_label="subject",
                        purpose=ReferencePurpose.OBSERVATION_SUBJECT,
                    )
            self._verify_membership_refs(
                proposition.evidence_requirements,
                self._s.evidence_requirements,
                lambda ref, proposition_label=label: (
                    f"{proposition_label} evidence_requirement '{ref}' not in evidence_requirements section"
                ),
            )

    def _verify_assertion_refs(self) -> None:
        for name, assertion in self._s.assertions.items():
            if not self._is_unresolved_var(assertion.proposition) and assertion.proposition not in self._s.propositions:
                self._err(f"Assertion '{name}' proposition '{assertion.proposition}' not in propositions section")

    def _verify_condition_proposition_refs(self) -> None:
        for name, condition in self._s.conditions.items():
            if condition.proposition and not self._is_unresolved_var(condition.proposition):
                if condition.proposition not in self._s.propositions:
                    self._err(f"Condition '{name}' proposition '{condition.proposition}' not in propositions section")

    def _verify_objective_success_assertions(self) -> None:
        allowed_roles = {AssertionRole.INVARIANT, AssertionRole.POSTCONDITION}
        for objective_name, objective in self._s.objectives.items():
            for assertion_name in objective.success.assertions:
                if self._is_unresolved_var(assertion_name):
                    continue
                assertion = self._s.assertions.get(assertion_name)
                if assertion is None:
                    self._err(
                        f"Objective '{objective_name}' success assertion '{assertion_name}' not in assertions section"
                    )
                elif assertion.role not in allowed_roles:
                    self._err(
                        f"Objective '{objective_name}' success assertion '{assertion_name}' "
                        "must be an invariant or postcondition"
                    )

    def _verify_precondition_assertion_uses(self) -> None:
        uses = [(f"Event '{name}'", event.assertions, "event trigger") for name, event in self._s.events.items()]
        uses.extend(
            (f"Agent '{name}'", agent.starting_assertions, "agent starting state")
            for name, agent in self._s.agents.items()
        )
        for owner, refs, use_label in uses:
            for assertion_name in refs:
                if self._is_unresolved_var(assertion_name):
                    continue
                assertion = self._s.assertions.get(assertion_name)
                if assertion is None:
                    self._err(f"{owner} assertion '{assertion_name}' not in assertions section")
                elif assertion.role is not AssertionRole.PRECONDITION:
                    self._err(f"{owner} assertion '{assertion_name}' {use_label} must be a precondition")
