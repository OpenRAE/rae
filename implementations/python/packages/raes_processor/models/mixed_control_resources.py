"""Compiled rev1 mixed-control policy children and directed-delivery control bindings.

One child per authored permitted transition and one per finite-script step: the
compiler never unrolls visits or assigns occurrence coordinates (MC-01).
"""

from dataclasses import dataclass

from .resources import ResolvedResource


@dataclass(frozen=True)
class MixedControlPermittedTransitionRuntime(ResolvedResource):
    """One reusable permission: kind, states, order window, target kinds and evidence."""

    transition_id: str = ""
    transition_kind: str = ""
    from_state_address: str = ""
    to_state_address: str = ""
    valid_from_order: int = 0
    valid_until_order: int = 0
    target_kinds: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    evidence_addresses: tuple[str, ...] = ()
    completion_evidence_refs: tuple[str, ...] = ()
    completion_evidence_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class MixedControlScriptStepRuntime(ResolvedResource):
    """One ordered finite-script step; every optional coordinate only narrows its transition."""

    step_id: str = ""
    position: int = 0
    permitted_transition_address: str = ""
    expected_state_revision: int | None = None
    valid_from_order: int | None = None
    valid_until_order: int | None = None
    target_kind: str = ""
    target_step_address: str = ""


@dataclass(frozen=True)
class MixedControlPolicyRuntime(ResolvedResource):
    """Compiled rev1 policy: explicit semantic pin and form, with its typed children."""

    semantics: str = ""
    form: str = ""
    participant_address: str = ""
    policy_revision: str = ""
    order_strategy: str = ""
    initial_state_address: str = ""
    permitted_transitions: tuple[MixedControlPermittedTransitionRuntime, ...] = ()
    script_steps: tuple[MixedControlScriptStepRuntime, ...] = ()


@dataclass(frozen=True)
class ParticipantInjectDeliveryControlRuntime:
    """Compiled rev1 delivery binding to one permission, never to an occurrence."""

    semantics: str = ""
    policy_revision: str = ""
    permitted_transition_address: str = ""
    controller_address: str = ""
    authority_scope_refs: tuple[str, ...] = ()
    authority_scope_addresses: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    evidence_addresses: tuple[str, ...] = ()
