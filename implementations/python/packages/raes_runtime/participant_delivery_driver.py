"""Execution admission for explicitly installed delivery-tool drivers."""

from raes_contracts.contracts.participant_invocation_tools import delivery_tool_actions_enabled
from raes_processor.compiler import compile_participant_invocation_tools


def delivery_tool_driver_actions(plane, model):
    installed = getattr(plane, "_inject_delivery", None)
    target = plane._target
    capability = target.manifest.participant_runtime
    if (
        installed is None
        or installed.model != model
        or capability is None
        or not delivery_tool_actions_enabled(capability.invocation_tool_actions)
        or not callable(getattr(target.participant_runtime, "invoke_delivery", None))
        or not callable(getattr(installed.resolver, "resolve_invocation_cut", None))
    ):
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
                if delivery.participant_address not in binding.participant_addresses or not binding.target_addresses:
                    continue
                offers = matching_delivery_tool_offers(
                    capability,
                    action_contract_address=binding.action_contract_address,
                    implementation_ref=implementation,
                    target_addresses=binding.target_addresses,
                    temporal_bindings=temporal,
                )
                if len(offers) == 1:
                    driven.add(binding.action_contract_address)
    return frozenset(driven)


def matching_delivery_tool_offers(
    capability,
    *,
    action_contract_address,
    implementation_ref,
    target_addresses,
    temporal_bindings,
):
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
