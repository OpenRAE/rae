"""Mixed-control participant behavior compilation helpers."""

from raes import ReferencePurpose
from raes.participant_behavior_specification import (
    MixedControlDeclaration,
    MixedControlDispositionRules,
    MixedControlParticipantOperation,
    ParticipantBehaviorSpecification,
)

from ..models import (
    MixedControlControllerStateRuntime,
    MixedControlDispositionRulesRuntime,
    MixedControlTransitionRuntime,
)
from .addresses import (
    _mixed_control_state_address,
    _mixed_control_transition_address,
    _participant_behavior_address,
)
from .alias_index import _runtime_addresses_for_refs
from .support import _dedupe, _dump


def _compile_controller_states(
    declaration: MixedControlDeclaration,
    *,
    spec_name: str,
    participant_address: str,
    addressable_ref_index: dict[str, set[str]],
) -> tuple[tuple[MixedControlControllerStateRuntime, ...], tuple[str, ...]]:
    states: list[MixedControlControllerStateRuntime] = []
    dependencies: list[str] = []
    for state_id, state in sorted(declaration.controller_states.items()):
        controller_address = (
            participant_address
            if state.controller_ref == "self"
            else _participant_behavior_address(state.controller_ref)
        )
        authority_addresses = _runtime_addresses_for_refs(
            list(state.authority_basis_refs),
            addressable_ref_index=addressable_ref_index,
            purpose=ReferencePurpose.AUTHORITY_ANCHOR,
        )
        scope_addresses = _runtime_addresses_for_refs(
            list(state.scope_refs),
            addressable_ref_index=addressable_ref_index,
            purpose=ReferencePurpose.AUTHORITY_SCOPE,
        )
        evidence_addresses = _runtime_addresses_for_refs(
            list(state.evidence_refs),
            addressable_ref_index=addressable_ref_index,
        )
        state_dependencies = _dedupe([controller_address, *authority_addresses, *scope_addresses, *evidence_addresses])
        dependencies.extend(state_dependencies)
        states.append(
            MixedControlControllerStateRuntime(
                address=_mixed_control_state_address(spec_name, state_id),
                name=state_id,
                spec=_dump(state),
                state_id=state_id,
                controller_ref=state.controller_ref,
                controller_address=controller_address,
                authority_basis_refs=tuple(state.authority_basis_refs),
                authority_basis_addresses=authority_addresses,
                scope_refs=tuple(state.scope_refs),
                scope_addresses=scope_addresses,
                policy_revision=state.policy_revision,
                valid_from_order=state.valid_from_order,
                valid_until_order=state.valid_until_order,
                authority_status=str(getattr(state.authority_status, "value", state.authority_status)),
                evidence_refs=tuple(state.evidence_refs),
                evidence_addresses=evidence_addresses,
                refresh_dependencies=state_dependencies,
            )
        )
    return tuple(states), _dedupe(dependencies)


def _compile_control_transitions(
    declaration: MixedControlParticipantOperation,
    *,
    spec_name: str,
    addressable_ref_index: dict[str, set[str]],
) -> tuple[tuple[MixedControlTransitionRuntime, ...], tuple[str, ...]]:
    transitions: list[MixedControlTransitionRuntime] = []
    dependencies: list[str] = []
    ordered = sorted(declaration.transitions.items(), key=lambda item: (item[1].effective_order, item[0]))
    for transition_id, transition in ordered:
        from_state_address = _mixed_control_state_address(spec_name, transition.from_state_ref)
        to_state_address = _mixed_control_state_address(spec_name, transition.to_state_ref)
        proposal_address = (
            _mixed_control_transition_address(spec_name, transition.proposal_ref)
            if transition.proposal_ref is not None
            else ""
        )
        evidence_addresses = _runtime_addresses_for_refs(
            list(transition.evidence_refs),
            addressable_ref_index=addressable_ref_index,
        )
        completion_addresses = _runtime_addresses_for_refs(
            list(transition.completion_evidence_refs),
            addressable_ref_index=addressable_ref_index,
        )
        transition_dependencies = _dedupe(
            [
                from_state_address,
                to_state_address,
                *([proposal_address] if proposal_address else []),
                *evidence_addresses,
                *completion_addresses,
            ]
        )
        dependencies.extend(transition_dependencies)
        transitions.append(
            MixedControlTransitionRuntime(
                address=_mixed_control_transition_address(spec_name, transition_id),
                name=transition_id,
                spec=_dump(transition),
                transition_id=transition_id,
                transition_kind=str(getattr(transition.transition_kind, "value", transition.transition_kind)),
                from_state_address=from_state_address,
                to_state_address=to_state_address,
                policy_revision=transition.policy_revision,
                expected_state_revision=transition.expected_state_revision,
                resulting_state_revision=transition.resulting_state_revision,
                effective_order=transition.effective_order,
                valid_from_order=transition.valid_from_order,
                valid_until_order=transition.valid_until_order,
                proposal_address=proposal_address,
                proposal_revision=transition.proposal_revision,
                evidence_refs=tuple(transition.evidence_refs),
                evidence_addresses=evidence_addresses,
                completion_evidence_refs=tuple(transition.completion_evidence_refs),
                completion_evidence_addresses=completion_addresses,
                refresh_dependencies=transition_dependencies,
            )
        )
    return tuple(transitions), _dedupe(dependencies)


def _compile_dispositions(dispositions: MixedControlDispositionRules) -> MixedControlDispositionRulesRuntime:
    return MixedControlDispositionRulesRuntime(
        duplicate=str(getattr(dispositions.duplicate, "value", dispositions.duplicate)),
        stale=str(getattr(dispositions.stale, "value", dispositions.stale)),
        revoked=str(getattr(dispositions.revoked, "value", dispositions.revoked)),
        late=str(getattr(dispositions.late, "value", dispositions.late)),
        concurrent=str(getattr(dispositions.concurrent, "value", dispositions.concurrent)),
        conflict=str(getattr(dispositions.conflict, "value", dispositions.conflict)),
    )


def _compile_mixed_control(
    *,
    spec_name: str,
    behavior_spec: ParticipantBehaviorSpecification,
    addressable_ref_index: dict[str, set[str]],
) -> tuple[
    str,
    str,
    str,
    str,
    MixedControlDispositionRulesRuntime | None,
    tuple[MixedControlControllerStateRuntime, ...],
    tuple[MixedControlTransitionRuntime, ...],
    tuple[str, ...],
]:
    """Compile one behavior specification's mixed-control declaration."""
    declaration = getattr(behavior_spec, "mixed_control", None)
    if declaration is None:
        return "", "", "", "", None, (), (), ()

    participant_address = _participant_behavior_address(declaration.participant_ref)
    states, state_dependencies = _compile_controller_states(
        declaration,
        spec_name=spec_name,
        participant_address=participant_address,
        addressable_ref_index=addressable_ref_index,
    )
    transitions, transition_dependencies = _compile_control_transitions(
        declaration,
        spec_name=spec_name,
        addressable_ref_index=addressable_ref_index,
    )
    return (
        participant_address,
        declaration.policy_revision,
        str(getattr(declaration.order_strategy, "value", declaration.order_strategy)),
        _mixed_control_state_address(spec_name, declaration.initial_state_ref),
        _compile_dispositions(declaration.dispositions),
        states,
        transitions,
        _dedupe([participant_address, *state_dependencies, *transition_dependencies]),
    )
