"""Test-only construction of complete exact/closed plan authority."""

from __future__ import annotations

from dataclasses import replace

from raes_contracts.observation_demand import EffectiveObservationDemand, ObservationSelector
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
)
from raes_processor.semantics.realization_concerns import (
    CONCERN_PAYLOAD_PATH,
    processor_derived_provisioning_concern_kinds,
    realization_concern_descriptors,
)

_MISSING = object()


def _nested_value(payload: object, path: tuple[str, ...]) -> object:
    current = payload
    for token in path:
        if not isinstance(current, dict) or token not in current:
            return _MISSING
        current = current[token]
    return current


def _payload_pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in path)


def _descriptor_applies(resource_type: str, section: str) -> bool:
    return (section == "nodes" and resource_type in {"node", "network"}) or (
        section == "content" and resource_type == "content-placement"
    )


def complete_test_realization_authority(plan: ProvisioningPlan) -> ProvisioningPlan:
    """Attach compiler-shaped authority to synthetic backend unit-test plans."""

    authority: list[ResolvedRealizationAuthority] = []
    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE:
            continue
        for descriptor in realization_concern_descriptors():
            if not _descriptor_applies(operation.resource_type, descriptor.section):
                continue
            value = _nested_value(operation.payload, descriptor.payload_path)
            if not descriptor.includes_authored_value(None if value is _MISSING else value):
                continue
            exact = value is not _MISSING and value not in (None, "", [], {})
            authority.append(
                ResolvedRealizationAuthority(
                    address=operation.address,
                    field_path=f"test.{operation.address}.{descriptor.concern_kind}",
                    domain="runtime-realization",
                    requirement_kind=descriptor.concern_kind,
                    payload_pointer=_payload_pointer(descriptor.payload_path),
                    mode=RealizationAuthorityMode.EXACT if exact else RealizationAuthorityMode.CLOSED,
                    source=(
                        RealizationResolutionSource.AUTHORED_LEAF
                        if exact
                        else RealizationResolutionSource.LEGACY_DEFAULT
                    ),
                    verification_scope=None,
                    required_observation_strength=None,
                )
            )
        for concern_kind in processor_derived_provisioning_concern_kinds(
            operation.resource_type,
            operation.payload,
        ):
            authority.append(
                ResolvedRealizationAuthority(
                    address=operation.address,
                    field_path=f"test.{operation.address}.{concern_kind}",
                    domain="runtime-realization",
                    requirement_kind=concern_kind,
                    payload_pointer=_payload_pointer(CONCERN_PAYLOAD_PATH[concern_kind]),
                    mode=RealizationAuthorityMode.EXACT,
                    source=RealizationResolutionSource.PROCESSOR_DERIVED,
                )
            )
    return replace(plan, realization_authority=tuple(authority))


def with_compute_substrate_collection_demand(
    plan: ProvisioningPlan,
    *,
    semantic_scope: str,
    address: str,
) -> ProvisioningPlan:
    """Attach an explicit non-persistent operational substrate readback owner."""

    selector = ObservationSelector(
        semantic_scope=semantic_scope,
        component_refs=(address,),
        data_kind="field",
        names=("compute-substrate",),
    )
    demand = EffectiveObservationDemand(
        scope=semantic_scope,
        purpose="operational",
        mode="operational-only",
        selectors=(selector,),
        collection="require",
        retention="disable",
        export="disable",
        basis="operational",
    )
    return replace(plan, observation_demands=(*plan.observation_demands, demand))


__all__ = ["complete_test_realization_authority", "with_compute_substrate_collection_demand"]
