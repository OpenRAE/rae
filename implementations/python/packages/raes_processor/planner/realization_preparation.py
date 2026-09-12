"""Pure selection admission under the original recursive realization authority."""

from __future__ import annotations

from copy import deepcopy

from pydantic import TypeAdapter
from raes.realization_envelope import member_projection
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan, RealizationAuthorityMode, ResolvedRealizationAuthority
from raes_contracts.realization_authority import planned_realization_selection_diagnostics
from raes_contracts.realization_preparation import BACKEND_PREPARATION_CONTRACT, RealizationPreparationAuthority
from raes_contracts.realization_structure import (
    ExactRealizationValue,
    evaluate_realization_constraint,
    structure_matches,
)
from raes_contracts.runtime_state import RuntimeSnapshot

from ..semantics.realization_concern_observations import typed_runtime_observation_shape
from ..semantics.realization_concerns import project_realization_concern, realization_concern_descriptor
from ..semantics.realization_requirement import CompiledRealizationRequirement
from ..semantics.realization_runtime_common import OPERATING_SYSTEM_REQUIREMENT_KINDS, matching_observation
from ..semantics.realization_runtime_concern_profiles import runtime_path_annotation
from .operating_system_capability_domains import operating_system_choice_supported
from .prepared_node_projection import prepared_node_delivery_violation

_MISSING = object()
_OPERATING_SYSTEM_KEYS = ("os_family", "os_distribution", "os_version")
_OPERATING_SYSTEM_ATTRIBUTES = {
    "os-family": "family",
    "os-distribution": "distribution",
    "os-version": "version",
}
_OPEN_AUTHORITY_MODES = frozenset({RealizationAuthorityMode.OPEN, RealizationAuthorityMode.CONSTRAINED})


def preparation_authority(manifest: BackendManifest) -> RealizationPreparationAuthority | None:
    """Select the explicitly advertised protocol without changing legacy claims."""

    if BACKEND_PREPARATION_CONTRACT not in manifest.supported_contract_versions:
        return None
    return RealizationPreparationAuthority(
        manifest_digest=canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
    )


def preparation_member_diagnostics(
    diagnostics: list[Diagnostic], requirements: tuple[CompiledRealizationRequirement, ...]
) -> list[Diagnostic]:
    """Keep static membership failures; choice-dependent checks precede apply."""

    paths = [
        requirement.field_path
        for requirement in requirements
        if getattr(requirement.explicitness, "value", None) in {"open", "constrained"}
    ]
    return [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.code
        not in {"realization-envelope.membership.path-absent", "realization-envelope.membership.domain-mismatch"}
        or not any(
            diagnostic.address == path or diagnostic.address.startswith((path + ".", path + "[")) for path in paths
        )
    ]


def _tokens(pointer: str) -> tuple[str, ...]:
    return tuple(token.replace("~1", "/").replace("~0", "~") for token in pointer.split("/")[1:])


def _value(payload: object, pointer: str) -> object:
    current = payload
    for token in _tokens(pointer):
        if not isinstance(current, dict) or token not in current:
            return _MISSING
        current = current[token]
    return current


def _remove(payload: dict[str, object], pointer: str) -> None:
    current = payload
    tokens = _tokens(pointer)
    for token in tokens[:-1]:
        if not isinstance(current.get(token), dict):
            return
        current = current[token]
    current.pop(tokens[-1], None)


def _authority_index(plan: ProvisioningPlan) -> dict[str, list[ResolvedRealizationAuthority]]:
    """Index declared realization authority by the address it governs."""

    authorities: dict[str, list[ResolvedRealizationAuthority]] = {}
    for authority in plan.realization_authority:
        authorities.setdefault(authority.address, []).append(authority)
    return authorities


def _authority_value_valid(authority: ResolvedRealizationAuthority, expected: object, actual: object) -> bool:
    """Check one chosen value against the authority that admitted it."""

    if authority.constraint_document is not None:
        return evaluate_realization_constraint(authority.constraint_document, actual).conformant
    if authority.mode in _OPEN_AUTHORITY_MODES and authority.structure is None:
        # The incumbent selection gate above has already checked all finite
        # bounds. The template is one member, not a fixed choice.
        return True
    projected = project_realization_concern(authority.requirement_kind, expected)
    return structure_matches(authority.structure or ExactRealizationValue(kind="exact"), projected, actual)


def _authority_selection_violation(
    authority: ResolvedRealizationAuthority,
    operation: object,
    candidate: object,
    before: dict[str, object],
    after: dict[str, object],
) -> str | None:
    """Compare one authority's chosen value, then strip it from the residual payload."""

    expected = _value(operation.payload, authority.payload_pointer)
    actual = _value(candidate.payload, authority.payload_pointer)
    if actual is _MISSING:
        return "Backend preparation omitted a declared concern." if expected is not _MISSING else None
    actual = project_realization_concern(
        authority.requirement_kind, actual, observed=True, recursive=authority.constraint_document is not None
    )
    if not _authority_value_valid(authority, expected, actual):
        return "Backend preparation does not satisfy the recursive constraints."
    _remove(before, authority.payload_pointer)
    _remove(after, authority.payload_pointer)
    return None


def _residual_payload_violation(
    operation: object, candidate: object, authorities: list[ResolvedRealizationAuthority]
) -> str | None:
    """Compare every authority on one operation, then compare the residual payload."""

    before, after = deepcopy(operation.payload), deepcopy(candidate.payload)
    for authority in authorities:
        if authority.mode is RealizationAuthorityMode.CLOSED:
            continue
        violation = _authority_selection_violation(authority, operation, candidate, before, after)
        if violation:
            return violation
    exact = structure_matches(ExactRealizationValue(kind="exact"), before, after)
    return None if exact else "Backend preparation changed a value outside realization authority."


def prepared_realization_violation(
    original: ProvisioningPlan, selected: ProvisioningPlan, manifest: BackendManifest
) -> str | None:
    """Check chosen values without claiming that preparation observed delivery."""

    if planned_realization_selection_diagnostics(selected):
        return "Backend preparation selected values outside the submitted authority."
    candidates = {operation.address: operation for operation in selected.operations}
    authorities = _authority_index(original)
    for operation in original.operations:
        candidate = candidates.get(operation.address)
        violation = (
            "Backend preparation omitted a submitted operation."
            if candidate is None
            else _residual_payload_violation(operation, candidate, authorities.get(operation.address, []))
        )
        if violation:
            return violation
    return _prepared_offer_violation(selected, manifest)


def _unsupported_operating_system(operation: object, manifest: BackendManifest) -> bool:
    """Report whether one node's joint operating-system identity is unsupported."""

    choice = tuple(operation.payload.get(key, "") for key in _OPERATING_SYSTEM_KEYS)
    if not any(choice):
        return False
    return not all(isinstance(value, str) for value in choice) or not operating_system_choice_supported(
        manifest.provisioner, *choice
    )


def _operating_system_offer_violation(selected: ProvisioningPlan, manifest: BackendManifest) -> str | None:
    """Reject any prepared node whose operating-system identity is unsupported."""

    for operation in selected.operations:
        if operation.resource_type == "node" and _unsupported_operating_system(operation, manifest):
            return "Backend preparation selected an unsupported joint operating-system identity."
    return None


def _offered_dimension_violation(
    authority: ResolvedRealizationAuthority, operations: dict[str, object], manifest: BackendManifest
) -> str | None:
    """Check one offered realization dimension against the configured envelope."""

    operation = operations.get(authority.address)
    if operation is None:
        return "Backend preparation omitted an offered realization dimension."
    raw = _value(operation.payload, authority.payload_pointer)
    value = None if raw is _MISSING else raw
    shape = None
    descriptor = realization_concern_descriptor(authority.requirement_kind)
    if value is not None and descriptor is not None and descriptor.authored_path[0] == "runtime":
        shape = typed_runtime_observation_shape(
            value,
            adapter=TypeAdapter(runtime_path_annotation(descriptor.authored_path[1:])),
        )
    holds = member_projection(
        value, authority.field_path, manifest.realization_envelope.expression, typed_value=shape
    ).holds
    return None if holds else "Backend preparation selected a value outside its configured offer."


def _prepared_offer_violation(selected: ProvisioningPlan, manifest: BackendManifest) -> str | None:
    if manifest.realization_envelope is None:
        return "Backend preparation requires a selected realization envelope."
    operations = {operation.address: operation for operation in selected.operations}
    violation = _operating_system_offer_violation(selected, manifest)
    for authority in selected.realization_authority:
        if violation:
            break
        violation = _offered_dimension_violation(authority, operations, manifest)
    return violation


def _delivered_value(authority: ResolvedRealizationAuthority, entry: object, snapshot: RuntimeSnapshot) -> object:
    """Read the delivered value, preferring a matching typed observation."""

    actual = _value(entry.payload, authority.payload_pointer)
    if authority.requirement_kind not in OPERATING_SYSTEM_REQUIREMENT_KINDS:
        return actual
    observation = matching_observation(authority, snapshot)
    if observation is None or observation.operating_system is None:
        return actual
    return getattr(observation.operating_system, _OPERATING_SYSTEM_ATTRIBUTES[authority.requirement_kind])


def _delivery_violation(
    authority: ResolvedRealizationAuthority, operation: object, entry: object, snapshot: RuntimeSnapshot
) -> str | None:
    """Compare one admitted completion against what the backend delivered."""

    expected = _value(operation.payload, authority.payload_pointer)
    actual = _delivered_value(authority, entry, snapshot)
    if expected is _MISSING and actual is _MISSING:
        return None
    if expected is _MISSING or actual is _MISSING:
        return "Backend did not deliver its admitted realization completion."
    recursive = authority.constraint_document is not None
    expected = project_realization_concern(authority.requirement_kind, expected, recursive=recursive)
    actual = project_realization_concern(authority.requirement_kind, actual, observed=True, recursive=recursive)
    exact = structure_matches(ExactRealizationValue(kind="exact"), expected, actual)
    return None if exact else "Backend did not deliver its admitted realization completion."


def prepared_delivery_violation(selected: ProvisioningPlan, snapshot: RuntimeSnapshot) -> str | None:
    """A supported completion is a delivery obligation, not a replaceable hint."""

    operations = {operation.address: operation for operation in selected.operations}
    for authority in selected.realization_authority:
        if authority.mode is RealizationAuthorityMode.CLOSED:
            continue
        operation, entry = operations.get(authority.address), snapshot.entries.get(authority.address)
        if operation is None or entry is None:
            continue
        violation = _delivery_violation(authority, operation, entry, snapshot)
        if violation:
            return violation
    return prepared_node_delivery_violation(selected, snapshot)


__all__ = [
    "prepared_realization_violation",
    "prepared_delivery_violation",
    "preparation_authority",
    "preparation_member_diagnostics",
]
