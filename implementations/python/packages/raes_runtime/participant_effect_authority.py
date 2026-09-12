"""Bind native participant effects to the submitted request and trusted scope."""

from raes_contracts.contracts.participant_execution import ParticipantExecutionControlRequestModel
from raes_contracts.runtime_state import RuntimeSnapshot

from .backend_realization_authority import _RealizationApplyContext


def participant_effect_authority(request: object, snapshot: RuntimeSnapshot) -> _RealizationApplyContext:
    """An execution scope owns its existing schedulers, not every participant."""

    resources = frozenset(getattr(request, "target_addresses", ()))
    targets = set(resources)
    participant = getattr(request, "participant_address", None)
    if participant is not None:
        targets.add(participant)
    if isinstance(request, ParticipantExecutionControlRequestModel):
        scope = request.execution_scope_ref
        targets.add(scope)
        targets.update(
            address
            for address, state in snapshot.participant_autonomous_execution_states.items()
            if state.get("policy_address") == scope
        )
    return _RealizationApplyContext(
        effect_owners=frozenset({"participant"}),
        effect_targets=frozenset(targets),
        resource_targets=resources,
    )
