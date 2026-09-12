"""Pure selection admission under the original recursive realization authority."""

from __future__ import annotations

from copy import deepcopy

from pydantic import TypeAdapter
from raes.realization_envelope import member_projection
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.planning import ProvisioningPlan, RealizationAuthorityMode
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
from ..semantics.realization_runtime_common import OPERATING_SYSTEM_REQUIREMENT_KINDS, matching_observation
from ..semantics.realization_runtime_concern_profiles import runtime_path_annotation
from .operating_system_capability_domains import operating_system_choice_supported
from .prepared_node_projection import prepared_node_delivery_violation

_MISSING = object()


def preparation_authority(manifest: BackendManifest) -> RealizationPreparationAuthority | None:
    """Select the explicitly advertised protocol without changing legacy claims."""

    if BACKEND_PREPARATION_CONTRACT not in manifest.supported_contract_versions:
        return None
    return RealizationPreparationAuthority(
        manifest_digest=canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
    )


def preparation_member_diagnostics(diagnostics: list, requirements: tuple) -> list:
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


def prepared_realization_violation(
    original: ProvisioningPlan, selected: ProvisioningPlan, manifest: BackendManifest
) -> str | None:
    """Check chosen values without claiming that preparation observed delivery."""

    if planned_realization_selection_diagnostics(selected):
        return "Backend preparation selected values outside the submitted authority."
    candidates = {operation.address: operation for operation in selected.operations}
    authorities: dict[str, list] = {}
    for authority in original.realization_authority:
        authorities.setdefault(authority.address, []).append(authority)
    for operation in original.operations:
        candidate = candidates.get(operation.address)
        if candidate is None:
            return "Backend preparation omitted a submitted operation."
        before, after = deepcopy(operation.payload), deepcopy(candidate.payload)
        for authority in authorities.get(operation.address, []):
            if authority.mode is RealizationAuthorityMode.CLOSED:
                continue
            expected = _value(operation.payload, authority.payload_pointer)
            actual = _value(candidate.payload, authority.payload_pointer)
            if actual is _MISSING:
                if expected is not _MISSING:
                    return "Backend preparation omitted a declared concern."
                continue
            actual = project_realization_concern(
                authority.requirement_kind, actual, observed=True, recursive=authority.constraint_document is not None
            )
            if authority.constraint_document is not None:
                valid = evaluate_realization_constraint(authority.constraint_document, actual).conformant
            elif (
                authority.mode in {RealizationAuthorityMode.OPEN, RealizationAuthorityMode.CONSTRAINED}
                and authority.structure is None
            ):
                # The incumbent selection gate above has already checked all
                # finite bounds. The template is one member, not a fixed choice.
                valid = True
            else:
                expected = project_realization_concern(authority.requirement_kind, expected)
                valid = structure_matches(authority.structure or ExactRealizationValue(kind="exact"), expected, actual)
            if not valid:
                return "Backend preparation does not satisfy the recursive constraints."
            _remove(before, authority.payload_pointer)
            _remove(after, authority.payload_pointer)
        if not structure_matches(ExactRealizationValue(kind="exact"), before, after):
            return "Backend preparation changed a value outside realization authority."
    return _prepared_offer_violation(selected, manifest)


def _prepared_offer_violation(selected: ProvisioningPlan, manifest: BackendManifest) -> str | None:
    if manifest.realization_envelope is None:
        return "Backend preparation requires a selected realization envelope."
    operations = {operation.address: operation for operation in selected.operations}
    for operation in selected.operations:
        if operation.resource_type != "node":
            continue
        choice = tuple(operation.payload.get(key, "") for key in ("os_family", "os_distribution", "os_version"))
        if any(choice) and (
            not all(isinstance(value, str) for value in choice)
            or not operating_system_choice_supported(manifest.provisioner, *choice)
        ):
            return "Backend preparation selected an unsupported joint operating-system identity."
    for authority in selected.realization_authority:
        operation = operations.get(authority.address)
        if operation is None:
            return "Backend preparation omitted an offered realization dimension."
        value = _value(operation.payload, authority.payload_pointer)
        value = None if value is _MISSING else value
        shape = None
        descriptor = realization_concern_descriptor(authority.requirement_kind)
        if value is not None and descriptor is not None and descriptor.authored_path[0] == "runtime":
            shape = typed_runtime_observation_shape(
                value,
                adapter=TypeAdapter(runtime_path_annotation(descriptor.authored_path[1:])),
            )
        if not member_projection(
            value, authority.field_path, manifest.realization_envelope.expression, typed_value=shape
        ).holds:
            return "Backend preparation selected a value outside its configured offer."
    return None


def prepared_delivery_violation(selected: ProvisioningPlan, snapshot: RuntimeSnapshot) -> str | None:
    """A supported completion is a delivery obligation, not a replaceable hint."""

    operations = {operation.address: operation for operation in selected.operations}
    for authority in selected.realization_authority:
        if authority.mode is RealizationAuthorityMode.CLOSED:
            continue
        operation, entry = operations.get(authority.address), snapshot.entries.get(authority.address)
        if operation is None or entry is None:
            continue
        expected = _value(operation.payload, authority.payload_pointer)
        actual = _value(entry.payload, authority.payload_pointer)
        if authority.requirement_kind in OPERATING_SYSTEM_REQUIREMENT_KINDS:
            observation = matching_observation(authority, snapshot)
            if observation is not None and observation.operating_system is not None:
                attribute = {"os-family": "family", "os-distribution": "distribution", "os-version": "version"}[
                    authority.requirement_kind
                ]
                actual = getattr(observation.operating_system, attribute)
        if expected is _MISSING and actual is _MISSING:
            continue
        if expected is _MISSING or actual is _MISSING:
            return "Backend did not deliver its admitted realization completion."
        expected = project_realization_concern(
            authority.requirement_kind, expected, recursive=authority.constraint_document is not None
        )
        actual = project_realization_concern(
            authority.requirement_kind, actual, observed=True, recursive=authority.constraint_document is not None
        )
        if not structure_matches(ExactRealizationValue(kind="exact"), expected, actual):
            return "Backend did not deliver its admitted realization completion."
    return prepared_node_delivery_violation(selected, snapshot)


__all__ = [
    "prepared_realization_violation",
    "prepared_delivery_violation",
    "preparation_authority",
    "preparation_member_diagnostics",
]
