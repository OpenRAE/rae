"""Bind action-local guarantees to a real execution scope and shared clock."""

from raes_contracts.contracts.participant_runtime import ParticipantTemporalRuntimeContextModel
from raes_contracts.contracts.participant_temporal import (
    ParticipantTemporalBindingModel,
    ParticipantTemporalExecutionContextModel,
)
from raes_contracts.contracts.time_model import RuntimeClockStateModel


def bind_shared_time_context(
    binding: ParticipantTemporalBindingModel,
    *,
    participant_address: str,
    episode_id: str,
    action_instance_id: str,
    execution_scope_ref: str,
    execution_generation: int,
    clock: RuntimeClockStateModel,
) -> ParticipantTemporalRuntimeContextModel:
    segment = clock.coordinate.segment
    return ParticipantTemporalRuntimeContextModel(
        temporal_contract_id=binding.temporal_id,
        time_domain=binding.time_domain,
        clock_authority=binding.clock_authority,
        event_points=list(binding.event_points),
        observation_point=(
            f"shared-time:{action_instance_id}:{binding.clock_address}:segment={segment},"
            f"tick={clock.coordinate.tick},microstep={clock.coordinate.microstep}"
        ),
        backend_disclosure_refs=list(binding.backend_disclosure_refs),
        reset_boundary=binding.reset_boundary,
        replay_boundary=binding.replay_boundary,
        shared_time=ParticipantTemporalExecutionContextModel(
            binding=binding.model_copy(deep=True),
            participant_address=participant_address,
            episode_id=episode_id,
            action_instance_id=action_instance_id,
            execution_scope_ref=execution_scope_ref,
            execution_generation=execution_generation,
            submitted_at=clock.coordinate.model_copy(deep=True),
            clock_sequence=clock.sequence,
            bound_start=binding.start.model_copy(update={"segment": segment}) if binding.start is not None else None,
            bound_end=binding.end.model_copy(update={"segment": segment}),
        ),
    )
