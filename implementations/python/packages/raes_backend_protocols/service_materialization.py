"""Shared fail-closed admission for service-owned content placements."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from raes_contracts.addressing import require_compiled_address
from raes_contracts.apparatus import RUNTIME_REALIZATION_DOMAIN, RealizationSupportDeclaration
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.profile_selections import profile_selection_binding
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ConcernDisposition,
    ObservationStrength,
    RealizationConcern,
)

from .capabilities import ProvisionerCapabilities

_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_FIELD_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.ASCII)
_FIELD_SEMANTICS = frozenset({"exact-token", "full-text", "integer", "temporal", "boolean"})
_COMMON_BINDING_FIELDS = {
    "target_service_address",
    "interface_profile",
    "profile_version",
    "content_type",
    "operation",
    "conflict_policy",
    "readback",
    "canonical_content_digest",
    "shared_service_relationship_ref",
    "consumer_tenant_ref",
    "mutable_state_owner",
    "reset_generation_owner",
    "readback_assertion_addresses",
    "evidence_requirement_refs",
    "observation_boundary_addresses",
}


@dataclass(frozen=True)
class _ProfileContract:
    profile: str
    version: str
    capability_term: str
    requirement_kind: str
    requirements: Mapping[str, str]
    binding_fields: frozenset[str]
    schema_profile: bool = False


_PROFILE_CONTRACTS = {
    "service-content": _ProfileContract(
        profile="service-content",
        version="1",
        capability_term="service-content-v1",
        requirement_kind="service-content-materialization",
        requirements={
            "operation": "ensure-owned-items",
            "conflict_policy": "reject-unowned-collision",
            "readback": "canonical-content-digest",
        },
        binding_fields=frozenset(_COMMON_BINDING_FIELDS),
    ),
    "service-search-index-schema": _ProfileContract(
        profile="service-search-index-schema",
        version="1",
        capability_term="service-search-index-schema-v1",
        requirement_kind="service-search-index-schema-materialization",
        requirements={
            "operation": "ensure-search-index-field-schema",
            "conflict_policy": "reject-unowned-collision",
            "readback": "canonical-portable-field-schema-digest",
        },
        binding_fields=frozenset(
            {
                *_COMMON_BINDING_FIELDS,
                "field_semantics",
                "canonical_field_schema_digest",
            }
        ),
        schema_profile=True,
    ),
}


def service_materialization_plan_diagnostics(
    plan: ProvisioningPlan,
    capabilities: ProvisionerCapabilities,
    envelope: BackendRealizationEnvelopeModel | None,
    realization_support: Sequence[RealizationSupportDeclaration] = (),
) -> list[Diagnostic]:
    """Validate exact profile, ownership, target, and readback before backend I/O."""

    diagnostics: list[Diagnostic] = []
    for operation in plan.operations:
        if operation.resource_type != "content-placement" or operation.action is ChangeAction.DELETE:
            continue
        handled, diagnostic = _private_service_selection(operation, capabilities)
        if not handled:
            diagnostic = _legacy_service_diagnostic(operation, capabilities, envelope, realization_support)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return diagnostics


def _private_service_selection(
    operation: object, capabilities: ProvisionerCapabilities
) -> tuple[bool, Diagnostic | None]:
    spec = operation.payload.get("spec")
    selected = spec.get("service_materialization") if isinstance(spec, Mapping) else None
    try:
        private = profile_selection_binding(selected)
        if private is not None and (
            operation.payload.get("service_materialization") is not None
            or private.coordinate not in capabilities.supported_service_materialization_profiles
        ):
            raise ValueError("Unadvertised private service profile")
    except (TypeError, ValueError):
        return True, _diagnostic(
            "provisioner.unsupported-service-materialization-profile",
            operation.address,
            "Provisioner does not support the selected service materialization profile.",
        )
    return private is not None, None


def _legacy_service_diagnostic(
    operation: object,
    capabilities: ProvisionerCapabilities,
    envelope: BackendRealizationEnvelopeModel | None,
    realization_support: Sequence[RealizationSupportDeclaration],
) -> Diagnostic | None:
    binding = operation.payload.get("service_materialization")
    if binding is None:
        return None
    message = _binding_violation(operation.payload, binding)
    if message is not None:
        return _diagnostic("provisioner.service-materialization-contract-invalid", operation.address, message)
    contract = _profile_contract(binding)
    assert contract is not None
    return _service_support_diagnostic(operation.address, contract, capabilities, envelope, realization_support)


def _service_support_diagnostic(
    address: str,
    contract: _ProfileContract,
    capabilities: ProvisionerCapabilities,
    envelope: BackendRealizationEnvelopeModel | None,
    realization_support: Sequence[RealizationSupportDeclaration],
) -> Diagnostic | None:
    diagnostic = None
    if contract.capability_term not in capabilities.supported_service_materialization_profiles:
        diagnostic = _diagnostic(
            "provisioner.unsupported-service-materialization-profile",
            address,
            f"Provisioner does not support service materialization profile '{contract.capability_term}'.",
        )
    elif not _exact_requirement_supported(realization_support, contract.requirement_kind):
        diagnostic = _diagnostic(
            "realization.unsupported-exact-requirement",
            address,
            "Backend does not declare exact realization support for service "
            f"materialization requirement '{contract.requirement_kind}'.",
        )
    elif not _independent_readback_supported(envelope):
        diagnostic = _diagnostic(
            "provisioner.service-materialization-readback-unsupported",
            address,
            "Backend realization envelope does not provide independent native readback for service materialization.",
        )
    return diagnostic


def _binding_violation(payload: Mapping[str, object], binding: object) -> str | None:
    if not isinstance(binding, Mapping):
        violation = "Service materialization binding is missing required closed contract fields."
    else:
        contract = _profile_contract(binding)
        if contract is None:
            violation = "Service materialization profile identity is unsupported or incomplete."
        elif set(binding) != contract.binding_fields:
            violation = "Service materialization binding is missing required closed contract fields."
        else:
            violations = (
                _requirements_violation(binding, contract),
                _content_type_violation(payload, binding, contract),
                _target_violation(payload, binding),
                _digest_violation(binding),
                _field_schema_violation(binding, contract),
                _readback_violation(binding),
                _ownership_violation(binding),
            )
            violation = next((message for message in violations if message is not None), None)
    return violation


def _profile_contract(binding: Mapping[str, object]) -> _ProfileContract | None:
    profile = binding.get("interface_profile")
    contract = _PROFILE_CONTRACTS.get(profile) if isinstance(profile, str) else None
    if contract is None or binding.get("profile_version") != contract.version:
        return None
    return contract


def _requirements_violation(
    binding: Mapping[str, object],
    contract: _ProfileContract,
) -> str | None:
    valid = all(binding.get(field) == expected for field, expected in contract.requirements.items())
    return None if valid else "Service materialization exact operation requirements are unsupported or incomplete."


def _content_type_violation(
    payload: Mapping[str, object],
    binding: Mapping[str, object],
    contract: _ProfileContract,
) -> str | None:
    content_type = binding.get("content_type")
    spec = payload.get("spec")
    valid = isinstance(spec, Mapping) and content_type == spec.get("type")
    if contract.schema_profile:
        source_is_absent = isinstance(spec, Mapping) and ("source" not in spec or spec.get("source") is None)
        items_are_empty_sequence = isinstance(spec, Mapping) and spec.get("items") == []
        valid = valid and content_type == "dataset" and source_is_absent and items_are_empty_sequence
    return None if valid else "Service materialization content type does not match the content placement."


def _target_violation(payload: Mapping[str, object], binding: Mapping[str, object]) -> str | None:
    valid = _service_belongs_to_target(payload.get("target_address"), binding.get("target_service_address"))
    return None if valid else "Service materialization target service does not belong to the content target node."


def _digest_violation(binding: Mapping[str, object]) -> str | None:
    digest = binding.get("canonical_content_digest")
    valid = isinstance(digest, str) and _DIGEST_RE.fullmatch(digest) is not None
    return None if valid else "Service materialization canonical content digest is invalid."


def _field_schema_violation(
    binding: Mapping[str, object],
    contract: _ProfileContract,
) -> str | None:
    violation = None
    if contract.schema_profile:
        field_semantics = binding.get("field_semantics")
        if (
            not isinstance(field_semantics, Mapping)
            or not field_semantics
            or any(
                not isinstance(name, str) or _FIELD_NAME_RE.fullmatch(name) is None or semantic not in _FIELD_SEMANTICS
                for name, semantic in field_semantics.items()
            )
        ):
            violation = "Search-index schema field semantics are empty, non-portable, or unsupported."
        else:
            digest = binding.get("canonical_field_schema_digest")
            expected = canonical_json_digest(
                {
                    "interface_profile": contract.profile,
                    "profile_version": contract.version,
                    "projection_scope": "declared-fields",
                    "field_semantics": dict(field_semantics),
                }
            )
            if digest != expected:
                violation = "Search-index schema canonical portable field-schema digest is invalid."
    return violation


def _exact_requirement_supported(
    realization_support: Sequence[RealizationSupportDeclaration],
    requirement_kind: str,
) -> bool:
    return any(
        declaration.domain == RUNTIME_REALIZATION_DOMAIN
        and requirement_kind in declaration.supported_exact_requirement_kinds
        for declaration in realization_support
    )


def _readback_violation(binding: Mapping[str, object]) -> str | None:
    if _readback_refs_valid(binding):
        return None
    return "Service materialization readback assertions, evidence, and observation boundaries are required."


def _ownership_violation(binding: Mapping[str, object]) -> str | None:
    if _ownership_valid(binding):
        return None
    return "Service materialization shared-state and reset ownership is incomplete or inconsistent."


def _service_belongs_to_target(target_address: object, service_address: object) -> bool:
    if not isinstance(target_address, str) or not isinstance(service_address, str):
        return False
    try:
        require_compiled_address(target_address)
        require_compiled_address(service_address)
    except ValueError:
        return False
    return service_address.startswith(f"{target_address}.service.")


def _readback_refs_valid(binding: Mapping[str, object]) -> bool:
    checks = (
        ("readback_assertion_addresses", "evaluation.assertion."),
        ("observation_boundary_addresses", "participant.observation-boundary."),
    )
    for field, prefix in checks:
        values = binding.get(field)
        if not _unique_non_empty_sequence(values) or any(not str(value).startswith(prefix) for value in values):
            return False
    return _unique_non_empty_sequence(binding.get("evidence_requirement_refs"))


def _unique_non_empty_sequence(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return False
    rendered = [str(item) for item in value]
    return all(item.strip() for item in rendered) and len(rendered) == len(set(rendered))


def _ownership_valid(binding: Mapping[str, object]) -> bool:
    relationship = binding.get("shared_service_relationship_ref")
    if relationship == "":
        return all(
            binding.get(field) == ""
            for field in ("consumer_tenant_ref", "mutable_state_owner", "reset_generation_owner")
        )
    return (
        isinstance(relationship, str)
        and bool(relationship.strip())
        and isinstance(binding.get("consumer_tenant_ref"), str)
        and bool(str(binding.get("consumer_tenant_ref")).strip())
        and binding.get("mutable_state_owner") in {"consumer_tenant", "shared_service"}
        and binding.get("reset_generation_owner") == binding.get("mutable_state_owner")
    )


def _independent_readback_supported(envelope: BackendRealizationEnvelopeModel | None) -> bool:
    if envelope is None:
        return False
    disclosure = next(
        (item for item in envelope.concerns if item.concern is RealizationConcern.CONTENT_PLACEMENT),
        None,
    )
    return (
        disclosure is not None
        and disclosure.disposition is ConcernDisposition.REALIZED
        and disclosure.observation_strength in {ObservationStrength.DAEMON_OBSERVED, ObservationStrength.GUEST_OBSERVED}
    )


def _diagnostic(code: str, address: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, domain="provisioning", address=address, message=message)


__all__ = ["service_materialization_plan_diagnostics"]
