"""Programmatic profile carriage through the incumbent reconciliation owner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.realization_preparation import BACKEND_PREPARATION_CONTRACT
from raes_contracts.realization_profiles import (
    PLAN_PROFILE_CONTRACT,
    profile_authority_violation,
    profile_context_digest,
    profile_resource_address,
    profile_selection_violation,
)


def profile_resources(
    model: object,
    resources: Mapping[str, object],
    manifest: BackendManifest,
    snapshot: Mapping[str, object],
    context: DomainProfileResolutionContextModel | None,
) -> tuple[Mapping[str, object], list[Diagnostic]]:
    """Retain a still-admitted backend choice; changed authority reconciles normally."""

    authority = model.profile_authority
    if authority is None:
        return resources, []
    diagnostic = Diagnostic(
        "realization.profile-unsupported",
        "provisioning",
        "profiles",
        "Plan profiles lack supported, pinned target authority.",
    )
    if (
        not {PLAN_PROFILE_CONTRACT, BACKEND_PREPARATION_CONTRACT} <= manifest.supported_contract_versions
        or profile_authority_violation(authority, context)
        or profile_context_digest(context) != manifest.domain_profile_context_digest
    ):
        return resources, [diagnostic]
    return _retained_profile_resources(authority, resources, snapshot, context, diagnostic)


def _retained_profile_resources(
    authority: object,
    resources: Mapping[str, object],
    snapshot: Mapping[str, object],
    context: DomainProfileResolutionContextModel | None,
    diagnostic: Diagnostic,
) -> tuple[Mapping[str, object], list[Diagnostic]]:
    """Retain a still-admitted backend choice, or report the unsupported authority."""

    try:
        by_address = {}
        for binding in authority.bindings:
            address = profile_resource_address(binding)
            if address not in resources:
                raise ValueError("Missing profile owner")
            by_address.setdefault(address, []).append(binding)
        previous = tuple(
            binding for address in by_address if (entry := snapshot.get(address)) for binding in entry.profile_bindings
        )
        retain = profile_selection_violation(authority, previous, context) is None
        resources = dict(resources)
        for address, bindings in by_address.items():
            values = snapshot.get(address).profile_bindings if retain else tuple(bindings)
            resources[address] = replace(resources[address], profile_bindings=values)
    except (AttributeError, TypeError, ValueError):
        return resources, [diagnostic]
    return resources, []
