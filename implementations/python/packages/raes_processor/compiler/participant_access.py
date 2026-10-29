"""Compile participant interactive access and its resource dependencies."""

from raes.agents import Agent
from raes.scenario import InstantiatedScenario
from raes_contracts.domain_profiles import DomainProfileBindingModel

from ..models import ParticipantInteractiveAccessRuntime
from .addresses import _account_address, _resource_address_for_node, _section_ref_name


def _participant_interactive_access(
    scenario: InstantiatedScenario, agent: Agent
) -> tuple[list[ParticipantInteractiveAccessRuntime], list[str]]:
    interactive_access: list[ParticipantInteractiveAccessRuntime] = []
    addresses: list[str] = []
    for access_id, access in sorted(agent.interactive_access.items()):
        target_name = _section_ref_name(access.target_ref, "nodes", scenario.nodes)
        target_addresses = (_resource_address_for_node(scenario, target_name),)
        account_addresses = (
            (_account_address(_section_ref_name(access.account_ref, "accounts", scenario.accounts)),)
            if access.account_ref
            else ()
        )
        channel = (
            access.channel
            if isinstance(access.channel, DomainProfileBindingModel)
            else str(getattr(access.channel, "value", access.channel))
        )
        interactive_access.append(
            ParticipantInteractiveAccessRuntime(
                access_id=access_id,
                target_ref=access.target_ref,
                target_address=target_addresses[0],
                channel=channel,
                account_ref=access.account_ref or "",
                account_address=account_addresses[0] if account_addresses else "",
            )
        )
        addresses.extend(target_addresses)
        addresses.extend(account_addresses)
    return interactive_access, addresses
