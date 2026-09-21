"""Wire projection helpers for participant execution capabilities."""

from raes_contracts.contracts.participant_execution import ParticipantExecutionBindingModel

from .participant_capabilities import ParticipantExecutionBinding, ParticipantRuntimeCapabilities
from .participant_resource_budgets import (
    participant_resource_budget_capability_from_model,
    participant_resource_budget_capability_payload,
)


def participant_execution_capability_payload(
    capability: ParticipantRuntimeCapabilities,
) -> dict[str, object]:
    """Project portable execution claims into a manifest payload."""

    return {
        "execution_bindings": [
            ParticipantExecutionBindingModel(
                binding_id=binding.binding_id,
                action_contract_address=binding.action_contract_address,
                target_addresses=binding.target_addresses,
                participant_implementation_ref=binding.participant_implementation_ref,
                constraint_refs=binding.constraint_refs,
                evidence_refs=binding.evidence_refs,
                max_action_attempts=binding.max_action_attempts,
                max_in_flight=binding.max_in_flight,
                timeout_seconds=binding.timeout_seconds,
                max_retries=binding.max_retries,
                temporal_contract_digests=binding.temporal_contract_digests,
            )
            for binding in capability.execution_bindings
        ],
        "supports_execution_control": capability.supports_execution_control,
        "supported_execution_control_actions": sorted(capability.supported_execution_control_actions),
        "supports_bounded_concurrency": capability.supports_bounded_concurrency,
        "max_execution_services": capability.max_execution_services,
        "max_concurrent_actions": capability.max_concurrent_actions,
        "resource_budgets": (
            participant_resource_budget_capability_payload(capability.resource_budgets)
            if capability.resource_budgets is not None
            else None
        ),
    }


def participant_execution_capability_kwargs(model: object) -> dict[str, object]:
    """Restore portable execution claims from a validated manifest model."""

    return {
        "execution_bindings": tuple(
            ParticipantExecutionBinding(
                binding_id=binding.binding_id,
                action_contract_address=binding.action_contract_address,
                target_addresses=tuple(binding.target_addresses),
                participant_implementation_ref=binding.participant_implementation_ref,
                constraint_refs=tuple(binding.constraint_refs),
                evidence_refs=tuple(binding.evidence_refs),
                max_action_attempts=binding.max_action_attempts,
                max_in_flight=binding.max_in_flight,
                timeout_seconds=binding.timeout_seconds,
                max_retries=binding.max_retries,
                temporal_contract_digests=tuple(binding.temporal_contract_digests),
            )
            for binding in model.execution_bindings
        ),
        "supports_execution_control": model.supports_execution_control,
        "supported_execution_control_actions": frozenset(model.supported_execution_control_actions),
        "supports_bounded_concurrency": model.supports_bounded_concurrency,
        "max_execution_services": model.max_execution_services,
        "max_concurrent_actions": model.max_concurrent_actions,
        "resource_budgets": (
            participant_resource_budget_capability_from_model(model.resource_budgets)
            if model.resource_budgets is not None
            else None
        ),
    }


__all__ = [
    "participant_execution_capability_kwargs",
    "participant_execution_capability_payload",
]
