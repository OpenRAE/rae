"""Compile exact tool relations independently of autonomous scheduling."""

from dataclasses import dataclass

from raes_contracts.contracts.participant_temporal import ParticipantTemporalBindingModel
from raes_contracts.errors import InvalidInputError

from ..models import RuntimeModel
from ..models.behavior_resources import ParticipantInvocationToolBindingRuntime
from .participant_autonomous_execution import compile_invocation_tool_bindings
from .participant_temporal import compile_participant_temporal_bindings


@dataclass(frozen=True)
class _ToolBindingScope:
    behavior_specification_address: str
    participant_addresses: tuple[str, ...]
    participant_implementation_ref: str
    max_action_attempts: int
    max_in_flight: int


def compile_participant_invocation_tools(
    model: RuntimeModel,
    specification_address: str,
    *,
    participant_implementation_ref: str,
    max_actions: int,
    max_in_flight: int,
) -> tuple[tuple[ParticipantInvocationToolBindingRuntime, ...], tuple[ParticipantTemporalBindingModel, ...]]:
    """Use the canonical compiler joins with explicit invocation limits and selection.

    The binding scope supplies no cadence, scheduler state or autonomous claim.
    Its limits bound the interaction relation; runtime admission still requires
    the exact installed execution offer and current authority.
    """

    specification = model.behavior_specifications.get(specification_address)
    if specification is None or model.realization_instance is None:
        raise InvalidInputError("invocation tools require retained compiler context")
    if type(max_actions) is not int or type(max_in_flight) is not int or not 1 <= max_in_flight <= max_actions:
        raise InvalidInputError("invocation tool limits must be positive and bounded")
    if not isinstance(participant_implementation_ref, str) or not participant_implementation_ref:
        raise InvalidInputError("invocation tools require an implementation selection")
    scope = _ToolBindingScope(
        specification.address,
        specification.participant_addresses,
        participant_implementation_ref,
        max_actions,
        max_in_flight,
    )
    bindings = compile_invocation_tool_bindings(model.realization_instance, scope, model.tool_affordances)
    actions = list(
        dict.fromkeys(
            binding.action_contract_address.removeprefix("participant.action-contract.") for binding in bindings
        )
    )
    temporal = compile_participant_temporal_bindings(model.realization_instance, actions)
    return bindings, temporal
