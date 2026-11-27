"""Execution admission for explicitly installed delivery-tool drivers."""

from __future__ import annotations

from raes_contracts.contracts.participant_invocation_tools import delivery_tool_actions_enabled
from raes_contracts.contracts.participant_temporal import ParticipantTemporalBindingModel
from raes_processor.compiler import compile_participant_invocation_tools


def delivery_tool_driver_actions(plane: object, model: object) -> frozenset[str]:
    installed = getattr(plane, "_inject_delivery", None)
    target = plane.delivery_target
    capability = target.manifest.participant_runtime
    if not _driver_available(installed, model, capability, target.participant_runtime):
        return frozenset()
    claim = capability.invocation_tool_actions
    driven = set()
    implementations = {offer.participant_implementation_ref for offer in capability.execution_bindings}
    for delivery in model.participant_inject_deliveries.values():
        for implementation in implementations:
            bindings, temporal = compile_participant_invocation_tools(
                model,
                delivery.behavior_specification_address,
                participant_implementation_ref=implementation,
                max_actions=claim.max_tool_actions_per_invocation,
                max_in_flight=claim.max_concurrent_tool_actions_per_invocation,
            )
            for binding in bindings:
                if _binding_executable(delivery, binding, capability, implementation, temporal):
                    driven.add(binding.action_contract_address)
    return frozenset(driven)


def _driver_available(installed: object, model: object, capability: object, executor: object) -> bool:
    return (
        installed is not None
        and installed.model == model
        and capability is not None
        and delivery_tool_actions_enabled(capability.invocation_tool_actions)
        and callable(getattr(executor, "invoke_delivery", None))
        and callable(getattr(installed.resolver, "resolve_invocation_cut", None))
    )


def _binding_executable(
    delivery: object,
    binding: object,
    capability: object,
    implementation: str,
    temporal: tuple[ParticipantTemporalBindingModel, ...],
) -> bool:
    if delivery.participant_address not in binding.participant_addresses or not binding.target_addresses:
        return False
    offers = matching_delivery_tool_offers(
        capability,
        action_contract_address=binding.action_contract_address,
        implementation_ref=implementation,
        target_addresses=binding.target_addresses,
        temporal_bindings=temporal,
    )
    return len(offers) == 1


def matching_delivery_tool_offers(
    capability: object,
    *,
    action_contract_address: str,
    implementation_ref: str,
    target_addresses: tuple[str, ...],
    temporal_bindings: tuple[ParticipantTemporalBindingModel, ...],
) -> list[object]:
    digests = {
        item.contract_digest for item in temporal_bindings if item.action_contract_address == action_contract_address
    }
    return [
        offer
        for offer in capability.execution_bindings
        if (
            offer.action_contract_address == action_contract_address
            and offer.participant_implementation_ref == implementation_ref
            and set(target_addresses) <= set(offer.target_addresses)
            and digests <= set(offer.temporal_contract_digests)
        )
    ]
