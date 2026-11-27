"""Programmatic profile carriage through the incumbent reconciliation owner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.planning import BACKEND_PREPARATION_CONTRACT
from raes_contracts.profile_selections import authored_resource_profiles, selected_profile_authority
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
) -> tuple[Mapping[str, object], list[Diagnostic], object]:
    """Retain a still-admitted backend choice; changed authority reconciles normally."""

    authority = model.profile_authority
    diagnostic = Diagnostic(
        "realization.profile-unsupported",
        "provisioning",
        "profiles",
        "Plan profiles lack supported, pinned target authority.",
    )
    # The contract owner refuses an authored selection with ValueError (E3).
    try:
        authority = selected_profile_authority(authored_resource_profiles(resources.values()), context, authority)
    except ValueError:
        return resources, [diagnostic], authority
    if authority is None:
        diagnostics = []
    elif (
        not {PLAN_PROFILE_CONTRACT, BACKEND_PREPARATION_CONTRACT} <= manifest.supported_contract_versions
        or profile_authority_violation(authority, context)
        or profile_context_digest(context) != manifest.domain_profile_context_digest
    ):
        diagnostics = [diagnostic]
    else:
        resources, diagnostics = _retained_profile_resources(authority, resources, snapshot, context, diagnostic)
    return resources, diagnostics, authority


def _owned_profile_address(binding: object, resources: Mapping[str, object]) -> str | None:
    """Return the address of the planned resource that owns a profile binding, or ``None``."""

    try:
        address = profile_resource_address(binding)
    except ValueError:
        # The contract owner refuses an unaddressable binding with ValueError (E3).
        return None
    # Every profile binding needs its owning planned resource.
    return address if address in resources else None


def _retained_profile_resources(
    authority: object,
    resources: Mapping[str, object],
    snapshot: Mapping[str, object],
    context: DomainProfileResolutionContextModel | None,
    diagnostic: Diagnostic,
) -> tuple[Mapping[str, object], list[Diagnostic]]:
    """Retain a still-admitted backend choice, or report the unsupported authority."""

    by_address: dict[str, list[object]] = {}
    for binding in authority.bindings:
        address = _owned_profile_address(binding, resources)
        if address is None:
            return resources, [diagnostic]
        by_address.setdefault(address, []).append(binding)
    previous = tuple(
        binding for address in by_address if (entry := snapshot.get(address)) for binding in entry.profile_bindings
    )
    retain = profile_selection_violation(authority, previous, context) is None
    retained = dict(resources)
    for address, bindings in by_address.items():
        entry = snapshot.get(address)
        if retain and entry is None:
            return retained, [diagnostic]
        values = entry.profile_bindings if retain else tuple(bindings)
        retained[address] = replace(retained[address], profile_bindings=values)
    return retained, []
