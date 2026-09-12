"""Runtime evaluation for registered SEM-218 realization concerns."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from raes.explicitness import ExplicitnessClass
from raes.runtime_resource_limits import (
    process_resource_limit_capability_admits,
    process_resource_limit_identity_digest,
)
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.apparatus import (
    ProcessResourceLimitCapability,
    RealizationSupportDeclaration,
)
from raes_contracts.bounded_domains import scalar_in_domain
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.realization_structure import (
    RealizationRelationStatus,
    evaluate_realization_constraint,
    structure_matches,
)
from raes_contracts.runtime_state import (
    RealizationObservationDisclosure,
    RealizationProvenanceEntry,
    RuntimeSnapshot,
)
from raes_contracts.vocabulary import (
    observation_strength_satisfies,
    verification_scope_satisfies,
)

from .realization_compute_substrate import evaluate_compute_substrate
from .realization_concerns import CONCERN_PAYLOAD_PATH, project_realization_concern
from .realization_process_limits import bound_process_resource_limit_capabilities
from .realization_runtime_common import (
    BACKEND_CONTRACT_INVALID,
    MISSING_CONCERN_VALUE,
    OPERATING_SYSTEM_REQUIREMENT_KINDS,
    concern_value,
    manifest_corroborates,
    matching_observation,
    observation_posture_supported,
    observed_projection,
    realization_provenance_entry,
    silent_approximation_diagnostic,
)
from .realization_snapshot_sanitization import invalid_observation_diagnostic
from .realization_specialized_projection import native_process_limit_projection

if TYPE_CHECKING:
    from .realization import CompiledRealizationRequirement


def evaluate_registered_realization(
    requirement: CompiledRealizationRequirement,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    *,
    manifest: BackendManifest | None = None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    """Gate one compiled requirement against its realized value."""

    if requirement.requirement_kind == "compute-substrate":
        result = evaluate_compute_substrate(requirement, declared_plan, returned_snapshot, manifest)
    else:
        result = _evaluate_non_compute_registered_realization(
            requirement,
            declared_plan,
            returned_snapshot,
            manifest,
        )
    return result


def _evaluate_non_compute_registered_realization(
    requirement: CompiledRealizationRequirement,
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    path = CONCERN_PAYLOAD_PATH.get(requirement.requirement_kind)
    declared_ops = {op.address: op for op in declared_plan.operations}
    op = declared_ops.get(requirement.address)
    if requirement.explicitness is None or path is None or op is None or op.action is ChangeAction.DELETE:
        return None, None
    if requirement.requirement_kind in OPERATING_SYSTEM_REQUIREMENT_KINDS:
        realized_value = _observed_operating_system_value(requirement, returned_snapshot)
    else:
        snapshot_entry = returned_snapshot.entries.get(requirement.address)
        realized_value = (
            concern_value(snapshot_entry.payload, path) if snapshot_entry is not None else MISSING_CONCERN_VALUE
        )
    if requirement.structure_error:
        result = silent_approximation_diagnostic(requirement), None
    elif (
        requirement.explicitness is ExplicitnessClass.OPEN
        and requirement.structure is None
        and requirement.constraint_document is None
    ):
        result = _evaluate_open_realization(requirement, realized_value, returned_snapshot, manifest)
    else:
        result = _evaluate_declared_realization(
            requirement,
            concern_value(op.payload, path),
            realized_value,
            returned_snapshot,
            manifest,
        )
    return result


def _evaluate_open_realization(
    requirement: CompiledRealizationRequirement,
    realized_value: object,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    diagnostic: Diagnostic | None = None
    provenance: RealizationProvenanceEntry | None = None
    if realized_value is not MISSING_CONCERN_VALUE:
        diagnostic, projection = observed_projection(requirement, realized_value)
        if diagnostic is None:
            diagnostic = _corroboration_diagnostic(requirement, returned_snapshot, manifest)
        if diagnostic is None:
            diagnostic = _process_limit_apparatus_diagnostic(requirement, projection, manifest)
        if diagnostic is None:
            provenance = realization_provenance_entry(requirement, False)
    return diagnostic, provenance


def _evaluate_declared_realization(
    requirement: CompiledRealizationRequirement,
    declared_value: object,
    realized_value: object,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    if declared_value is MISSING_CONCERN_VALUE:
        return None, None
    corroboration_diagnostic = _corroboration_diagnostic(requirement, returned_snapshot, manifest)
    if corroboration_diagnostic is not None:
        return corroboration_diagnostic, None
    declared_projection = _project_declared_realization(requirement, declared_value)
    diagnostic, realized_projection = observed_projection(requirement, realized_value)
    if diagnostic is not None:
        result = (diagnostic, None)
    else:
        result = _projected_declared_realization_result(
            requirement,
            declared_projection,
            realized_projection,
            realized_value,
            manifest,
        )
    return result


def _project_declared_realization(
    requirement: CompiledRealizationRequirement,
    declared_value: object,
) -> object:
    try:
        projection = project_realization_concern(
            requirement.requirement_kind,
            declared_value,
            recursive=requirement.constraint_document is not None,
        )
    except (TypeError, ValueError):
        projection = MISSING_CONCERN_VALUE
    return projection


def _projected_declared_realization_result(
    requirement: CompiledRealizationRequirement,
    declared_projection: object,
    realized_projection: object,
    realized_value: object,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    process_limit_diagnostic, honoured = _process_limit_realization_result(
        requirement,
        declared_projection,
        realized_projection,
        manifest,
    )
    if process_limit_diagnostic is not None:
        return process_limit_diagnostic, None
    if honoured is None or requirement.structure is not None:
        honoured = realized_projection == declared_projection
    if _projected_constraints_rejected(requirement, declared_projection, realized_projection, honoured):
        result = (silent_approximation_diagnostic(requirement), None)
    elif realized_value is not MISSING_CONCERN_VALUE:
        result = (None, realization_provenance_entry(requirement, honoured))
    else:
        result = (None, None)
    return result


def _projected_constraints_rejected(
    requirement: CompiledRealizationRequirement,
    declared_projection: object,
    realized_projection: object,
    honoured: bool,
) -> bool:
    if requirement.constraint_document is not None:
        return (
            evaluate_realization_constraint(requirement.constraint_document, realized_projection).status
            is not RealizationRelationStatus.CONFORMANT
        )
    if requirement.structure is not None and not structure_matches(
        requirement.structure, declared_projection, realized_projection
    ):
        return True
    constrained_os_rejected = (
        requirement.requirement_kind in OPERATING_SYSTEM_REQUIREMENT_KINDS
        and requirement.explicitness is ExplicitnessClass.CONSTRAINED
        and requirement.value_domain is not None
        and not scalar_in_domain(realized_projection, requirement.value_domain)
    )
    return constrained_os_rejected or (requirement.explicitness is ExplicitnessClass.EXACT and not honoured)


def _observation_corroborates(
    requirement: CompiledRealizationRequirement,
    observation: RealizationObservationDisclosure,
    manifest: BackendManifest | None,
) -> bool:
    """Return whether one disclosed observation satisfies the requirement's evidence bar."""

    required_scope = requirement.verification_scope
    return (
        (required_scope is None or verification_scope_satisfies(observation.verification_scope, required_scope))
        and (
            requirement.required_observation_strength is None
            or observation_strength_satisfies(
                observation.observation_strength,
                requirement.required_observation_strength,
            )
        )
        and manifest_corroborates(requirement, observation, manifest)
    )


def _corroboration_diagnostic(
    requirement: CompiledRealizationRequirement,
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> Diagnostic | None:
    """Reject exact inventory equality that lacks its declared observation basis."""

    required_scope = requirement.verification_scope
    if required_scope is None and requirement.required_observation_strength is None:
        return None
    observation = matching_observation(requirement, returned_snapshot)
    if observation is not None and _observation_corroborates(requirement, observation, manifest):
        return None
    return Diagnostic(
        code=BACKEND_CONTRACT_INVALID,
        domain=requirement.domain,
        address=requirement.address,
        message=(
            f"Backend returned no valid effective corroboration for "
            f"'{requirement.requirement_kind}' requirement at '{requirement.field_path}'; "
            "matching inventory values alone do not establish realization (SEM-218 I2)."
        ),
        severity=Severity.ERROR,
    )


def _observed_operating_system_value(
    requirement: CompiledRealizationRequirement,
    returned_snapshot: RuntimeSnapshot,
) -> object:
    observation = matching_observation(requirement, returned_snapshot)
    identity = observation.operating_system if observation is not None else None
    if identity is None:
        return MISSING_CONCERN_VALUE
    attribute = {
        "os-family": "family",
        "os-distribution": "distribution",
        "os-version": "version",
    }[requirement.requirement_kind]
    return getattr(identity, attribute)


def _process_limit_declaration_supported(
    requirement: CompiledRealizationRequirement,
    declaration: RealizationSupportDeclaration,
) -> bool:
    capability = declaration.observation_capabilities.get(requirement.requirement_kind)
    return (
        observation_posture_supported(requirement, declaration)
        and capability is not None
        and (
            requirement.verification_scope is None
            or verification_scope_satisfies(capability.verification_scope, requirement.verification_scope)
        )
        and (
            requirement.required_observation_strength is None
            or observation_strength_satisfies(
                capability.observation_strength,
                requirement.required_observation_strength,
            )
        )
    )


def _process_limit_realization_result(
    requirement: CompiledRealizationRequirement,
    declared_projection: object,
    realized_projection: object,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, bool | None]:
    if requirement.requirement_kind != "process-resource-limits":
        result = (None, None)
    else:
        if requirement.constraint_document is not None:
            declared_projection = native_process_limit_projection(declared_projection)
            realized_projection = native_process_limit_projection(realized_projection)
        apparatus = _process_limit_apparatus_diagnostic(requirement, realized_projection, manifest)
        if apparatus is not None:
            result = (apparatus, None)
        elif requirement.explicitness is not ExplicitnessClass.CONSTRAINED:
            result = (None, declared_projection == realized_projection)
        else:
            result = _constrained_process_limit_realization_result(
                requirement,
                declared_projection,
                realized_projection,
            )
    return result


def _process_limit_projection_maps(
    requirement: CompiledRealizationRequirement,
    declared_projection: object,
    realized_projection: object,
) -> tuple[Diagnostic | None, dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    diagnostic: Diagnostic | None = None
    if not isinstance(declared_projection, list) or not isinstance(realized_projection, list):
        return silent_approximation_diagnostic(requirement), {}, {}
    try:
        declared = _process_limit_projection_map(declared_projection)
        realized = _process_limit_projection_map(realized_projection)
    except (TypeError, ValueError):
        return invalid_observation_diagnostic(requirement), {}, {}
    diagnostic = None
    if declared.keys() != realized.keys():
        diagnostic = silent_approximation_diagnostic(requirement)
    return diagnostic, declared, realized


def _process_limit_projection_map(projection: list[object]) -> dict[str, dict[str, object]]:
    return {process_resource_limit_identity_digest(item): cast(dict[str, object], item) for item in projection}


def _constrained_process_limit_values_admitted(
    requirement: CompiledRealizationRequirement,
    declared: dict[str, dict[str, object]],
    realized: dict[str, dict[str, object]],
) -> tuple[bool, bool]:
    constraints = {
        (constraint.identity_digest, constraint.leaf): constraint.allowed_values
        for constraint in requirement.value_constraints
    }
    admitted = True
    exact = True
    for identity, expected in declared.items():
        actual = realized[identity]
        for leaf in ("soft", "hard"):
            expected_value = expected[leaf]
            actual_value = actual[leaf]
            allowed = constraints.get((identity, leaf))
            leaf_admitted = actual_value == expected_value if allowed is None else _strict_member(actual_value, allowed)
            admitted = admitted and leaf_admitted
            exact = exact and actual_value == expected_value
    return admitted, exact


def _constrained_process_limit_realization_result(
    requirement: CompiledRealizationRequirement,
    declared_projection: object,
    realized_projection: object,
) -> tuple[Diagnostic | None, bool | None]:
    diagnostic, declared, realized = _process_limit_projection_maps(
        requirement,
        declared_projection,
        realized_projection,
    )
    exact: bool | None = None
    if diagnostic is None:
        admitted, exact = _constrained_process_limit_values_admitted(requirement, declared, realized)
        if not admitted:
            diagnostic = silent_approximation_diagnostic(requirement)
            exact = None
    return diagnostic, exact


def _strict_member(value: object, domain: tuple[object, ...]) -> bool:
    return any(type(value) is type(candidate) and value == candidate for candidate in domain)


def _bound_process_limit_capabilities(
    requirement: CompiledRealizationRequirement,
    manifest: BackendManifest,
) -> tuple[ProcessResourceLimitCapability, ...]:
    return tuple(
        capability
        for declaration in manifest.realization_support
        if declaration.domain == requirement.domain and _process_limit_declaration_supported(requirement, declaration)
        for capability in bound_process_resource_limit_capabilities(declaration, manifest.realization_envelope)
    )


def _process_limit_projection_admitted(
    realized_projection: list[object],
    capabilities: tuple[ProcessResourceLimitCapability, ...],
) -> bool:
    try:
        admitted = all(
            any(process_resource_limit_capability_admits(capability, item) for capability in capabilities)
            for item in realized_projection
        )
    except (TypeError, ValueError):
        admitted = False
    return admitted


def _process_limit_apparatus_diagnostic(
    requirement: CompiledRealizationRequirement,
    realized_projection: object,
    manifest: BackendManifest | None,
) -> Diagnostic | None:
    if requirement.requirement_kind != "process-resource-limits" or realized_projection is MISSING_CONCERN_VALUE:
        diagnostic = None
    elif not isinstance(realized_projection, list) or manifest is None:
        diagnostic = silent_approximation_diagnostic(requirement)
    else:
        capabilities = _bound_process_limit_capabilities(requirement, manifest)
        admitted = _process_limit_projection_admitted(realized_projection, capabilities)
        diagnostic = None if admitted else silent_approximation_diagnostic(requirement)
    return diagnostic


__all__ = ["evaluate_registered_realization"]
