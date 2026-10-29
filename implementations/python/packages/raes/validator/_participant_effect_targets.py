"""Declared effect targets use the complete index, including unreferenceable kinds."""

from .._reference_targetability import ReferencePurpose


class _ParticipantEffectTargetsMixin:
    def _verify_effect_target_refs(self) -> None:
        declared = self._require_declaration_index()
        for action_name, action_contract in self._s.action_contracts.items():
            for effect in action_contract.effects:
                # A genuinely undeclared token is observation-boundary information.
                # Registered declarations must instead satisfy the action-target policy.
                self._verify_purpose_refs(
                    f"Action contract '{action_name}' effect '{effect.effect_id}'",
                    "target_ref",
                    [ref for ref in effect.target_refs if declared.resolve(ref)],
                    ReferencePurpose.ACTION_TARGET,
                )
