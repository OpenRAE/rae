"""Rev1 mixed-control compilation and the trusted API-409 v2 occurrence-policy projection.

A rev1 policy compiles to the shared controller-state children plus one child per
permitted transition and one per finite-script step, nested in
``MixedControlPolicyRuntime``. Compiled addresses that do not fit API-424
``ControlRef`` are reported, never truncated (MC-08).
"""

import re

from raes import ReferencePurpose
from raes.participant_behavior_specification import ParticipantBehaviorSpecification
from raes.participant_inject_delivery import ParticipantInjectDelivery
from raes.participant_mixed_control_policy import (
    MIXED_CONTROL_POLICY_SEMANTICS,
    MixedControlPolicy,
)
from raes.scenario import InstantiatedScenario
from raes_contracts.contracts import ParticipantControlOccurrencePolicyModel

from ..models import (
    Diagnostic,
    MixedControlControllerStateRuntime,
    MixedControlPermittedTransitionRuntime,
    MixedControlPolicyRuntime,
    MixedControlScriptStepRuntime,
    ParticipantBehaviorSpecificationRuntime,
    ParticipantInjectDeliveryControlRuntime,
    RuntimeModel,
)
from ._mixed_control import _compile_controller_states, _compile_dispositions, _compile_mixed_control
from .addresses import (
    _behavior_specification_address,
    _mixed_control_state_address,
    _participant_behavior_address,
    _section_ref_name,
)
from .alias_index import _runtime_addresses_for_refs, _RuntimeAddressableRefIndex
from .support import _address, _dedupe, _dump

FIXED_COORDINATE_SEMANTICS = "fixed-coordinate-v1"
_CONTROL_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")
_CONTROL_REF_MAX_LENGTH = 256


def _policy_child_address(spec_name: str, *parts: str) -> str:
    return _address("participant", "behavior-specification", spec_name, *parts)


def _policy_address(spec_name: str) -> str:
    return _policy_child_address(spec_name, "mixed-control-policy")


def _permitted_transition_address(spec_name: str, transition_id: str) -> str:
    return _policy_child_address(spec_name, "permitted-transition", transition_id)


def _script_step_address(spec_name: str, step_id: str) -> str:
    return _policy_child_address(spec_name, "script-step", step_id)


def _window(item: object) -> dict[str, int | None]:
    return {"valid_from_order": item.valid_from_order, "valid_until_order": item.valid_until_order}


def mixed_control_semantics(declaration: object) -> str:
    """Return the explicit compiled interpretation discriminant of one ``mixed_control`` value."""

    if declaration is None:
        return ""
    if isinstance(declaration, MixedControlPolicy):
        return MIXED_CONTROL_POLICY_SEMANTICS
    return FIXED_COORDINATE_SEMANTICS


def _compile_permitted_transitions(
    declaration: MixedControlPolicy,
    *,
    spec_name: str,
    addressable_ref_index: dict[str, set[str]],
) -> tuple[MixedControlPermittedTransitionRuntime, ...]:
    transitions = []
    for transition_id, transition in sorted(declaration.permitted_transitions.items()):
        from_address = _mixed_control_state_address(spec_name, transition.from_state_ref)
        to_address = _mixed_control_state_address(spec_name, transition.to_state_ref)
        completion = tuple(transition.completion_evidence_refs or ())
        evidence_addresses = _runtime_addresses_for_refs(
            list(transition.evidence_refs), addressable_ref_index=addressable_ref_index
        )
        completion_addresses = _runtime_addresses_for_refs(
            list(completion), addressable_ref_index=addressable_ref_index
        )
        transitions.append(
            MixedControlPermittedTransitionRuntime(
                address=_permitted_transition_address(spec_name, transition_id),
                name=transition_id,
                spec=_dump(transition),
                transition_id=transition_id,
                transition_kind=str(getattr(transition.transition_kind, "value", transition.transition_kind)),
                from_state_address=from_address,
                to_state_address=to_address,
                valid_from_order=transition.valid_from_order,
                valid_until_order=transition.valid_until_order,
                target_kinds=tuple(sorted(kind.value for kind in transition.target_kinds_allowed())),
                evidence_refs=tuple(transition.evidence_refs),
                evidence_addresses=evidence_addresses,
                completion_evidence_refs=completion,
                completion_evidence_addresses=completion_addresses,
                refresh_dependencies=_dedupe([from_address, to_address, *evidence_addresses, *completion_addresses]),
            )
        )
    return tuple(transitions)


def _compile_script_steps(
    declaration: MixedControlPolicy, *, spec_name: str
) -> tuple[MixedControlScriptStepRuntime, ...]:
    if declaration.script_steps is None:
        return ()
    steps = []
    for position, step in enumerate(declaration.script_steps, start=1):
        transition_address = _permitted_transition_address(spec_name, step.permitted_transition_ref)
        target_step = _script_step_address(spec_name, step.target_step_ref) if step.target_step_ref else ""
        steps.append(
            MixedControlScriptStepRuntime(
                address=_script_step_address(spec_name, step.step_id),
                name=step.step_id,
                spec=_dump(step),
                step_id=step.step_id,
                position=position,
                permitted_transition_address=transition_address,
                expected_state_revision=step.expected_state_revision,
                valid_from_order=step.valid_from_order,
                valid_until_order=step.valid_until_order,
                target_kind=step.target_kind.value if step.target_kind is not None else "",
                target_step_address=target_step,
                refresh_dependencies=_dedupe([transition_address, *([target_step] if target_step else [])]),
            )
        )
    return tuple(steps)


def _ref_range_diagnostics(
    spec_name: str,
    policy: MixedControlPolicyRuntime,
    states: tuple[MixedControlControllerStateRuntime, ...],
) -> list[Diagnostic]:
    refs = [
        ("policy", policy.address),
        ("participant-behavior", policy.participant_address),
        *(("permitted-transition", item.address) for item in policy.permitted_transitions),
        *(("script-step", item.address) for item in policy.script_steps),
        *(("controller-state", item.address) for item in states),
        *(("controller", item.controller_address) for item in states),
    ]
    return [
        Diagnostic(
            code="participant.mixed-control-ref-out-of-range",
            domain="participant",
            address=_behavior_specification_address(spec_name),
            message=(
                f"Compiled rev1 mixed-control {label} address does not fit an API-424 ControlRef "
                f"(at most {_CONTROL_REF_MAX_LENGTH} characters, portable pattern); it is never truncated."
            ),
        )
        for label, ref in sorted(set(refs))
        if len(ref) > _CONTROL_REF_MAX_LENGTH or _CONTROL_REF_RE.fullmatch(ref) is None
    ]


def _compile_mixed_control_declaration(
    *,
    spec_name: str,
    behavior_spec: ParticipantBehaviorSpecification,
    addressable_ref_index: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> tuple[object, ...]:
    """Compile either form: the legacy eight-part result plus the rev1 policy child or ``None``."""

    declaration = behavior_spec.mixed_control
    if not isinstance(declaration, MixedControlPolicy):
        legacy = _compile_mixed_control(
            spec_name=spec_name, behavior_spec=behavior_spec, addressable_ref_index=addressable_ref_index
        )
        return (*legacy, None)
    participant_address = _participant_behavior_address(declaration.participant_ref)
    states, state_dependencies = _compile_controller_states(
        declaration,
        spec_name=spec_name,
        participant_address=participant_address,
        addressable_ref_index=addressable_ref_index,
    )
    transitions = _compile_permitted_transitions(
        declaration, spec_name=spec_name, addressable_ref_index=addressable_ref_index
    )
    steps = _compile_script_steps(declaration, spec_name=spec_name)
    order_strategy = str(getattr(declaration.order_strategy, "value", declaration.order_strategy))
    initial_state = _mixed_control_state_address(spec_name, declaration.initial_state_ref)
    dependencies = _dedupe(
        [
            participant_address,
            *state_dependencies,
            *(item.address for item in transitions),
            *(dependency for item in transitions for dependency in item.refresh_dependencies),
        ]
    )
    policy = MixedControlPolicyRuntime(
        address=_policy_address(spec_name),
        name=spec_name,
        spec=_dump(declaration),
        semantics=declaration.semantics,
        form=declaration.form,
        participant_address=participant_address,
        policy_revision=declaration.policy_revision,
        order_strategy=order_strategy,
        initial_state_address=initial_state,
        permitted_transitions=transitions,
        script_steps=steps,
        refresh_dependencies=dependencies,
    )
    diagnostics.extend(_ref_range_diagnostics(spec_name, policy, states))
    return (
        participant_address,
        declaration.policy_revision,
        order_strategy,
        initial_state,
        _compile_dispositions(declaration.dispositions),
        states,
        (),
        dependencies,
        policy,
    )


def _compile_delivery_policy_control(
    scenario: InstantiatedScenario,
    spec_name: str,
    binding: ParticipantInjectDelivery,
    participant_address: str,
    addressable_ref_index: dict[str, set[str]],
) -> ParticipantInjectDeliveryControlRuntime | None:
    control = binding.control
    if control is None:
        return None
    controller_address = participant_address
    if control.controller_ref != "self":
        controller_address = _participant_behavior_address(
            _section_ref_name(control.controller_ref, "agents", scenario.agents)
        )
    return ParticipantInjectDeliveryControlRuntime(
        semantics=control.semantics,
        policy_revision=control.policy_revision,
        permitted_transition_address=_permitted_transition_address(spec_name, control.permitted_transition_ref),
        controller_address=controller_address,
        authority_scope_refs=tuple(control.authority_scope_refs),
        authority_scope_addresses=_runtime_addresses_for_refs(
            control.authority_scope_refs,
            addressable_ref_index=addressable_ref_index,
            purpose=ReferencePurpose.AUTHORITY_SCOPE,
        ),
        evidence_refs=tuple(control.evidence_refs),
        evidence_addresses=_runtime_addresses_for_refs(
            control.evidence_refs,
            addressable_ref_index=addressable_ref_index,
            purpose=ReferencePurpose.TARGETABLE,
        ),
    )


def _occurrence_identity_refs(
    refs: tuple[str, ...],
    *,
    addressable_ref_index: _RuntimeAddressableRefIndex,
    purpose: ReferencePurpose,
) -> list[str]:
    """Project each resolved identity, preserving anchors without runtime records."""

    identities: set[str] = set()
    for ref in refs:
        candidates = addressable_ref_index.declarations.resolve_for(ref, purpose)
        if len(candidates) != 1:
            raise ValueError("occurrence policy references must resolve to one declared identity")
        canonical = next(iter(candidates))
        identities.update(addressable_ref_index.get(canonical) or {canonical})
    return sorted(identities)


def occurrence_policy_projection(
    specification: ParticipantBehaviorSpecificationRuntime,
    *,
    episode_id: str,
    addressable_ref_index: _RuntimeAddressableRefIndex,
) -> ParticipantControlOccurrencePolicyModel:
    """Build a trusted episode policy with the declaration context used for compilation."""

    policy = specification.mixed_control_policy
    if policy is None:
        raise ValueError("behavior specification has no rev1 mixed-control policy")
    return ParticipantControlOccurrencePolicyModel.model_validate(
        {
            "semantics": policy.semantics,
            "participant_address": policy.participant_address,
            "episode_id": episode_id,
            "pin": {
                "behavior_specification_ref": specification.address,
                "policy_ref": policy.address,
                "policy_revision": policy.policy_revision,
                "form": policy.form,
            },
            "order_strategy": policy.order_strategy,
            "initial_state_ref": policy.initial_state_address,
            "behavior_scope_refs": _occurrence_identity_refs(
                specification.authority_scope_refs,
                addressable_ref_index=addressable_ref_index,
                purpose=ReferencePurpose.AUTHORITY_SCOPE,
            ),
            "states": [
                {
                    "state_ref": state.address,
                    "controller_ref": state.controller_address,
                    "authority_basis_refs": _occurrence_identity_refs(
                        state.authority_basis_refs,
                        addressable_ref_index=addressable_ref_index,
                        purpose=ReferencePurpose.AUTHORITY_ANCHOR,
                    ),
                    "scope_refs": _occurrence_identity_refs(
                        state.scope_refs,
                        addressable_ref_index=addressable_ref_index,
                        purpose=ReferencePurpose.AUTHORITY_SCOPE,
                    ),
                    "authority_status": state.authority_status,
                    **_window(state),
                }
                for state in specification.controller_states
            ],
            "transitions": [
                {
                    "transition_ref": item.address,
                    "kind": item.transition_kind,
                    "from_state_ref": item.from_state_address,
                    "to_state_ref": item.to_state_address,
                    **_window(item),
                    "target_kinds": list(item.target_kinds),
                }
                for item in policy.permitted_transitions
            ],
            "script_steps": [
                {
                    "step_ref": step.address,
                    "transition_ref": step.permitted_transition_address,
                    "expected_state_revision": step.expected_state_revision,
                    **_window(step),
                    "target_kind": step.target_kind or None,
                    "target_step_ref": step.target_step_address or None,
                }
                for step in policy.script_steps
            ],
        }
    )


def project_control_episode_policy(
    model: RuntimeModel, specification_ref: str, *, episode_id: str
) -> ParticipantControlOccurrencePolicyModel:
    """Project an admitted episode without exposing compiler-private identity indexes."""

    from .alias_index import _runtime_addressable_ref_index

    if model.realization_instance is None:
        raise ValueError("control policy projection requires retained instantiated compiler context")
    return occurrence_policy_projection(
        model.behavior_specifications[specification_ref],
        episode_id=episode_id,
        addressable_ref_index=_runtime_addressable_ref_index(model.realization_instance),
    )


__all__ = [
    "FIXED_COORDINATE_SEMANTICS",
    "mixed_control_semantics",
    "occurrence_policy_projection",
    "project_control_episode_policy",
]
