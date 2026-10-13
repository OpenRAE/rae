"""Participant-directed inject delivery compilation (DSL-142)."""

from dataclasses import dataclass, replace

from raes.participant_inject_delivery import ParticipantInjectDelivery
from raes.scenario import InstantiatedScenario

from ..models import ParticipantInjectDeliveryRuntime
from ._mixed_control_policy import _compile_delivery_policy_control
from .addresses import (
    _behavior_specification_address,
    _observation_boundary_address,
    _participant_behavior_address,
    _participant_inject_delivery_address,
    _section_ref_name,
)
from .alias_index import _runtime_addressable_ref_index, _runtime_addresses_for_refs
from .support import _address, _dedupe, _dump


@dataclass(frozen=True)
class _DeliveryAddresses:
    owner: str
    participant: str
    inject: str
    event: str
    script: str
    story: str
    source_item: str
    result_item: str
    observation_boundary: str
    temporal: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class _DeliveryControlAddresses:
    transition: str = ""
    controller: str = ""
    authority_scope: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


def _compile_participant_inject_deliveries(
    scenario: InstantiatedScenario,
) -> dict[str, ParticipantInjectDeliveryRuntime]:
    """Compile admitted delivery declarations as participant metadata."""

    deliveries: dict[str, ParticipantInjectDeliveryRuntime] = {}
    addressable_ref_index = _runtime_addressable_ref_index(scenario)
    for spec_name, behavior_spec in scenario.behavior_specifications.items():
        for binding_id, binding in sorted(behavior_spec.participant_inject_deliveries.items()):
            runtime = _compile_participant_inject_delivery(
                scenario,
                spec_name,
                binding_id,
                binding,
                addressable_ref_index,
            )
            deliveries[runtime.address] = runtime
    return deliveries


def _compile_participant_inject_delivery(
    scenario: InstantiatedScenario,
    spec_name: str,
    binding_id: str,
    binding: ParticipantInjectDelivery,
    addressable_ref_index: dict[str, set[str]],
) -> ParticipantInjectDeliveryRuntime:
    addresses = _delivery_addresses(scenario, spec_name, binding, addressable_ref_index)
    control = _delivery_control_addresses(
        scenario,
        spec_name,
        binding,
        addresses.participant,
        addressable_ref_index,
    )
    runtime = _delivery_runtime(
        spec_name,
        binding_id,
        binding,
        addresses,
        control,
        _delivery_dependencies(addresses, control),
    )
    policy_control = _compile_delivery_policy_control(
        scenario, spec_name, binding, addresses.participant, addressable_ref_index
    )
    if policy_control is None:
        return runtime
    dependencies = (
        policy_control.permitted_transition_address,
        policy_control.controller_address,
        *policy_control.authority_scope_addresses,
        *policy_control.evidence_addresses,
    )
    return replace(
        runtime,
        control=policy_control,
        refresh_dependencies=_dedupe([*runtime.refresh_dependencies, *dependencies]),
    )


def _delivery_addresses(
    scenario: InstantiatedScenario,
    spec_name: str,
    binding: ParticipantInjectDelivery,
    addressable_ref_index: dict[str, set[str]],
) -> _DeliveryAddresses:
    participant_name = _section_ref_name(binding.participant_ref, "agents", scenario.agents)
    inject_name = _section_ref_name(binding.inject_ref, "injects", scenario.injects)
    event_name = _section_ref_name(binding.occurrence.event_ref, "events", scenario.events)
    script_name = _section_ref_name(binding.occurrence.script_ref, "scripts", scenario.scripts)
    story_name = _section_ref_name(binding.occurrence.story_ref, "stories", scenario.stories)
    boundary_name = _section_ref_name(
        binding.observation_boundary_ref,
        "observation_boundaries",
        scenario.observation_boundaries,
    )
    return _DeliveryAddresses(
        owner=_behavior_specification_address(spec_name),
        participant=_participant_behavior_address(participant_name),
        inject=_address("orchestration", "inject", inject_name),
        event=_address("orchestration", "event", event_name),
        script=_address("orchestration", "script", script_name),
        story=_address("orchestration", "story", story_name),
        source_item=_runtime_addresses_for_refs(
            [binding.source_item_ref],
            addressable_ref_index=addressable_ref_index,
        )[0],
        result_item=_runtime_addresses_for_refs(
            [binding.result_item_ref],
            addressable_ref_index=addressable_ref_index,
        )[0],
        observation_boundary=_observation_boundary_address(boundary_name),
        temporal=tuple(
            _address(
                "time",
                "constraint",
                _section_ref_name(ref, "temporal_constraints", scenario.temporal_constraints),
            )
            for ref in binding.temporal_constraint_refs
        ),
        evidence=tuple(
            _address(
                "sdl",
                "evidence-requirements",
                _section_ref_name(ref, "evidence_requirements", scenario.evidence_requirements),
            )
            for ref in binding.evidence_requirement_refs
        ),
    )


def _delivery_control_addresses(
    scenario: InstantiatedScenario,
    spec_name: str,
    binding: ParticipantInjectDelivery,
    participant_address: str,
    addressable_ref_index: dict[str, set[str]],
) -> _DeliveryControlAddresses:
    if binding.control_transition_ref is None:
        return _DeliveryControlAddresses()
    controller_address = participant_address
    if binding.controller_ref != "self":
        controller_name = _section_ref_name(binding.controller_ref, "agents", scenario.agents)
        controller_address = _participant_behavior_address(controller_name)
    return _DeliveryControlAddresses(
        transition=_address(
            "participant",
            "behavior-specification",
            spec_name,
            "control-transition",
            binding.control_transition_ref,
        ),
        controller=controller_address,
        authority_scope=_runtime_addresses_for_refs(
            binding.control_authority_scope_refs,
            addressable_ref_index=addressable_ref_index,
        ),
        evidence=_runtime_addresses_for_refs(
            binding.control_evidence_refs,
            addressable_ref_index=addressable_ref_index,
        ),
    )


def _delivery_dependencies(
    addresses: _DeliveryAddresses,
    control: _DeliveryControlAddresses,
) -> tuple[str, ...]:
    return _dedupe(
        [
            addresses.owner,
            addresses.participant,
            addresses.inject,
            addresses.event,
            addresses.script,
            addresses.story,
            addresses.source_item,
            addresses.result_item,
            addresses.observation_boundary,
            *addresses.temporal,
            *addresses.evidence,
            *([control.transition] if control.transition else []),
            *([control.controller] if control.controller else []),
            *control.authority_scope,
            *control.evidence,
        ]
    )


def _delivery_runtime(
    spec_name: str,
    binding_id: str,
    binding: ParticipantInjectDelivery,
    addresses: _DeliveryAddresses,
    control: _DeliveryControlAddresses,
    dependencies: tuple[str, ...],
) -> ParticipantInjectDeliveryRuntime:
    policy = binding.delivery_policy
    return ParticipantInjectDeliveryRuntime(
        address=_participant_inject_delivery_address(spec_name, binding_id),
        name=binding_id,
        binding_id=binding_id,
        behavior_specification_address=addresses.owner,
        participant_address=addresses.participant,
        inject_address=addresses.inject,
        event_address=addresses.event,
        script_address=addresses.script,
        story_address=addresses.story,
        source_item_ref=binding.source_item_ref,
        source_item_address=addresses.source_item,
        result_item_ref=binding.result_item_ref,
        result_item_address=addresses.result_item,
        observation_boundary_address=addresses.observation_boundary,
        delivery_kind=binding.delivery_kind.value,
        policy_ref=policy.policy_ref,
        policy_revision=policy.policy_revision,
        exposure_policy_ref=policy.exposure_policy_ref,
        audience_scope_ref=policy.audience_scope_ref,
        visibility_basis_ref=policy.visibility_basis_ref,
        disclosure_basis_ref=policy.disclosure_basis_ref,
        order_basis=binding.order_basis.value,
        temporal_constraint_addresses=addresses.temporal,
        evidence_requirement_addresses=addresses.evidence,
        failure_disposition=binding.failure_disposition.value,
        control_transition_address=control.transition,
        controller_address=control.controller,
        control_authority_scope_refs=tuple(binding.control_authority_scope_refs),
        control_authority_scope_addresses=control.authority_scope,
        control_effective_order=binding.control_effective_order,
        control_valid_from_order=binding.control_valid_from_order,
        control_valid_until_order=binding.control_valid_until_order,
        control_evidence_refs=tuple(binding.control_evidence_refs),
        control_evidence_addresses=control.evidence,
        ordering_dependencies=(addresses.inject, addresses.event, addresses.script, addresses.story),
        refresh_dependencies=dependencies,
        spec=_dump(binding),
    )
