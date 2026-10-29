"""Plan-scope randomized allocation and its closed pre-allocation addresses."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictInt
from raes.identifiers import PortableIdentifier

from .base import ContractModel, NonEmptyString
from .experiment_apparatus import ExperimentStochasticControlModel
from .random_stream import PublicSeedModel

AllocationOrdinal = Annotated[StrictInt, Field(ge=0, le=999999)]
RECORDED_ALLOCATION_POLICY_ID = "experiment-recorded-allocation-v1"


class ExperimentAllocationPolicyModel(ContractModel):
    """One accepted procedure, separate from descriptive allocation_method."""

    kind: Literal["randomized"]
    policy_id: PortableIdentifier
    algorithm_profile: Literal["fisher-yates-allocation-v1"]
    stochastic_control_ref: NonEmptyString


class AllocationStreamAddressModel(ContractModel):
    """A plan-scope slot, never an SDL point or a selected trial coordinate."""

    address_profile: Literal["allocation-address-v1"] = "allocation-address-v1"
    namespace: PortableIdentifier
    allocation_policy_id: PortableIdentifier
    draw_purpose: Literal["condition-assignment"] = "condition-assignment"
    slot: AllocationOrdinal
    local_coordinate: Literal[0] = 0


class AllocationDrawModel(ContractModel):
    address: AllocationStreamAddressModel
    value: AllocationOrdinal
    rejection_attempts: Annotated[StrictInt, Field(ge=0, lt=32)]


class AdmittedExperimentAllocationModel(ContractModel):
    policy: ExperimentAllocationPolicyModel
    entry_order: list[NonEmptyString] = Field(min_length=1, max_length=10000)
    draws: list[AllocationDrawModel] = Field(max_length=9999)


def resolve_allocation_control(
    policy: ExperimentAllocationPolicyModel,
    controls: dict[str, ExperimentStochasticControlModel],
) -> ExperimentStochasticControlModel:
    control = controls.get(policy.stochastic_control_ref)
    if control is None or control.role != "randomization" or control.executable_binding is None:
        raise ValueError("allocation requires exactly one executable randomization control")
    binding = control.executable_binding
    if binding.profile_ref.ref_id != "blake3-xof-v1" or binding.profile_ref.ref_version != "random-stream-profile/v1":
        raise ValueError("allocation requires exact blake3-xof-v1 profile and version")
    if not isinstance(binding.root_entropy, PublicSeedModel):
        raise ValueError("allocation governed entropy requires an authorized resolver")
    return control


def compile_experiment_allocation(
    policy: ExperimentAllocationPolicyModel,
    canonical_entry_ids: list[str],
    controls: dict[str, ExperimentStochasticControlModel],
) -> AdmittedExperimentAllocationModel:
    """Reverse Fisher–Yates with bounded draws at stable pre-allocation slots."""

    from ..random_stream_engine import decode_public_seed, derive_stream_key, draw_bounded_integer

    if not 1 <= len(canonical_entry_ids) <= 10000 or len(set(canonical_entry_ids)) != len(canonical_entry_ids):
        raise ValueError("allocation domain must be nonempty, bounded, and unique")
    control = resolve_allocation_control(policy, controls)
    binding = control.executable_binding
    key = derive_stream_key(profile_id="blake3-xof-v1", root_entropy=decode_public_seed(binding.root_entropy))
    order = list(canonical_entry_ids)
    draws = []
    for slot, index in enumerate(range(len(order) - 1, 0, -1)):
        address = AllocationStreamAddressModel(
            namespace=binding.namespace, allocation_policy_id=policy.policy_id, slot=slot
        )
        draw = draw_bounded_integer(
            profile_id="blake3-xof-v1",
            stream_key=key,
            address=address,
            minimum=0,
            maximum=index,
            max_rejection_attempts=32,
        )
        if draw.rejection_exhausted or draw.value is None:
            raise ValueError("allocation exhausted its bounded-integer transform")
        order[index], order[draw.value] = order[draw.value], order[index]
        draws.append(AllocationDrawModel(address=address, value=draw.value, rejection_attempts=draw.rejection_attempts))
    return AdmittedExperimentAllocationModel(policy=policy, entry_order=order, draws=draws)
