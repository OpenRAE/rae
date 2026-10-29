"""Portable artifact admission and runtime satisfaction semantics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes.artifact_requirements import ArtifactMechanismProfile, ArtifactRequirement
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.apparatus import RealizationSupportDeclaration
from raes_contracts.artifact_requirements import (
    ArtifactAvailabilityContext,
    ArtifactRequirementAvailability,
    ArtifactSatisfactionDisclosureModel,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ChangeAction, ProvisionOp
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot
from raes_contracts.vocabulary import RealizationSupportMode

if TYPE_CHECKING:
    from .realization import CompiledRealizationRequirement

_BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"


def artifact_requirement_diagnostics(
    requirements: tuple[CompiledRealizationRequirement, ...],
    manifest: BackendManifest,
    *,
    availability: ArtifactAvailabilityContext | None = None,
) -> list[Diagnostic]:
    """Validate portable artifact demand against facts and backend routes."""

    facts = availability or ArtifactAvailabilityContext()
    diagnostics: list[Diagnostic] = []

    for compiled in requirements:
        requirement = compiled.artifact_requirement
        if requirement is not None:
            diagnostics.extend(
                _compiled_artifact_diagnostics(
                    compiled,
                    requirement,
                    manifest,
                    facts.for_address(compiled.address),
                )
            )
    return diagnostics


def _compiled_artifact_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    manifest: BackendManifest,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    declarations = [
        declaration for declaration in manifest.realization_support if declaration.domain == compiled.domain
    ]
    return [
        *_open_support_diagnostics(compiled, requirement, declarations),
        *_artifact_availability_diagnostics(compiled, requirement, facts),
        *_artifact_route_diagnostics(compiled, requirement, declarations),
    ]


def _open_support_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    declarations: list[RealizationSupportDeclaration],
) -> list[Diagnostic]:
    supported = any(declaration.support_mode is RealizationSupportMode.OPEN_REALIZATION for declaration in declarations)
    if requirement.explicitness is ExplicitnessClass.OPEN and not supported:
        return [
            _artifact_diagnostic(
                compiled,
                "artifact.unsupported-open-realization",
                "Backend declares no open artifact realization support.",
            )
        ]
    return []


def _artifact_availability_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    return [
        *_exact_artifact_availability_diagnostics(compiled, requirement, facts),
        *_constraint_availability_diagnostics(compiled, requirement, facts),
        *_locked_input_availability_diagnostics(compiled, requirement, facts),
        *_candidate_availability_diagnostics(compiled, requirement, facts),
        *_materialization_availability_diagnostics(compiled, requirement, facts),
    ]


def _exact_artifact_availability_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    exact = requirement.exact_artifact
    if exact is not None and exact.digest not in facts.available_artifact_digests:
        return [
            _artifact_diagnostic(
                compiled,
                "artifact.unavailable-exact-artifact",
                "The required immutable artifact is not available.",
            )
        ]
    return []


def _constraint_availability_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    satisfied = set(facts.satisfied_constraint_ids)
    return [
        _artifact_diagnostic(
            compiled,
            "artifact.unsatisfied-constraint",
            f"Artifact constraint '{constraint.constraint_id}' is not satisfied.",
        )
        for constraint in requirement.constraints
        if constraint.constraint_id not in satisfied
    ]


def _locked_input_availability_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    verified = set(facts.verified_locked_input_ids)
    return [
        _artifact_diagnostic(
            compiled,
            "artifact.missing-locked-input",
            f"Locked artifact input '{locked_input.input_id}' is not verified.",
        )
        for locked_input in requirement.locked_inputs
        if locked_input.input_id not in verified
    ]


def _candidate_availability_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    available = set(facts.available_candidate_ids)
    if requirement.candidates and not any(candidate.candidate_id in available for candidate in requirement.candidates):
        return [
            _artifact_diagnostic(
                compiled,
                "artifact.unavailable-candidate",
                "No declared artifact candidate is available.",
            )
        ]
    return []


def _materialization_availability_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    facts: ArtifactRequirementAvailability,
) -> list[Diagnostic]:
    available = set(facts.available_materialization_specification_digests)
    if requirement.materialization_specifications and not any(
        specification.digest in available for specification in requirement.materialization_specifications
    ):
        return [
            _artifact_diagnostic(
                compiled,
                "artifact.unavailable-materialization-specification",
                "No declared digest-bound materialization specification is available.",
            )
        ]
    return []


def _artifact_route_diagnostics(
    compiled: CompiledRealizationRequirement,
    requirement: ArtifactRequirement,
    declarations: list[RealizationSupportDeclaration],
) -> list[Diagnostic]:
    supported_routes = {
        (
            _artifact_mechanism_key(capability.mechanism),
            route.acquisition,
            route.timing,
        )
        for declaration in declarations
        for capability in declaration.artifact_mechanisms
        if compiled.requirement_kind in capability.supported_requirement_kinds
        for route in capability.supported_routes
    }
    permitted = any(
        (
            _artifact_mechanism_key(route.mechanism),
            route.acquisition,
            route.timing,
        )
        in supported_routes
        for route in requirement.permitted_routes
    )
    if permitted:
        return []
    return [
        _artifact_diagnostic(
            compiled,
            "artifact.unsupported-backend-mechanism",
            "Backend declares no supported artifact mechanism and acquisition/timing route.",
        )
    ]


def evaluate_artifact_realization(
    requirement: CompiledRealizationRequirement,
    declared_ops: dict[str, ProvisionOp],
    returned_snapshot: RuntimeSnapshot,
    *,
    manifest: BackendManifest | None,
    availability: ArtifactAvailabilityContext | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    """Validate one returned artifact satisfaction before snapshot admission."""

    contract = requirement.artifact_requirement
    op = declared_ops.get(requirement.address)
    if contract is None or op is None or op.action is ChangeAction.DELETE:
        return None, None
    snapshot_entry = returned_snapshot.entries.get(requirement.address)
    payload = snapshot_entry.payload.get("artifact_satisfaction") if snapshot_entry is not None else None
    try:
        satisfaction = ArtifactSatisfactionDisclosureModel.model_validate(payload)
    except TypeError, ValueError:
        return _silent_approximation_diagnostic(requirement), None

    facts = (availability or ArtifactAvailabilityContext()).for_address(requirement.address)
    invalid = _artifact_satisfaction_invalid(requirement, contract, satisfaction, facts, manifest)
    diagnostic = _silent_approximation_diagnostic(requirement) if invalid else None
    provenance = None if invalid else _artifact_realization_provenance(requirement, contract, satisfaction)
    return diagnostic, provenance


def _artifact_satisfaction_invalid(
    requirement: CompiledRealizationRequirement,
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    facts: ArtifactRequirementAvailability,
    manifest: BackendManifest | None,
) -> bool:
    return any(
        (
            _identity_or_route_invalid(requirement, contract, satisfaction, facts, manifest),
            _candidate_selection_invalid(contract, satisfaction, facts),
            _materialization_selection_invalid(contract, satisfaction, facts),
            _locked_input_or_constraint_invalid(contract, satisfaction, facts),
            not _trust_claims_verified(contract, satisfaction, facts),
        )
    )


def _identity_or_route_invalid(
    requirement: CompiledRealizationRequirement,
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    facts: ArtifactRequirementAvailability,
    manifest: BackendManifest | None,
) -> bool:
    if manifest is None:
        return True
    selected_route = (
        _artifact_mechanism_key(satisfaction.mechanism),
        satisfaction.acquisition,
        satisfaction.timing,
    )
    permitted_routes = {
        (
            _artifact_mechanism_key(route.mechanism),
            route.acquisition,
            route.timing,
        )
        for route in contract.permitted_routes
    }
    exact = contract.exact_artifact
    return any(
        (
            satisfaction.backend != manifest.identity,
            not _backend_route_supported(requirement, satisfaction, manifest),
            satisfaction.requirement_id != contract.requirement_id,
            selected_route not in permitted_routes,
            exact is not None and satisfaction.artifact != exact,
            exact is not None and exact.digest not in facts.available_artifact_digests,
        )
    )


def _candidate_selection_invalid(
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    facts: ArtifactRequirementAvailability,
) -> bool:
    candidates = {candidate.candidate_id: candidate for candidate in contract.candidates}
    selected = candidates.get(satisfaction.candidate_id) if satisfaction.candidate_id is not None else None
    selected_invalid = selected is not None and (
        satisfaction.artifact != selected.artifact or selected.candidate_id not in facts.available_candidate_ids
    )
    return any(
        (
            satisfaction.candidate_id is not None and selected is None,
            bool(candidates) and satisfaction.candidate_id is None,
            not candidates and satisfaction.candidate_id is not None,
            selected_invalid,
        )
    )


def _materialization_selection_invalid(
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    facts: ArtifactRequirementAvailability,
) -> bool:
    specifications = {
        specification.specification_id: specification for specification in contract.materialization_specifications
    }
    selected = (
        specifications.get(satisfaction.materialization_specification_id)
        if satisfaction.materialization_specification_id is not None
        else None
    )
    selected_mechanism = _artifact_mechanism_key(satisfaction.mechanism)
    requires_selection = any(
        _artifact_mechanism_key(specification.profile) == selected_mechanism
        for specification in contract.materialization_specifications
    )
    return any(
        (
            satisfaction.materialization_specification_id is not None and selected is None,
            selected is not None and _artifact_mechanism_key(selected.profile) != selected_mechanism,
            selected is None and satisfaction.materialization_specification_digest is not None,
            selected is not None and satisfaction.materialization_specification_digest != selected.digest,
            selected is not None and selected.digest not in facts.available_materialization_specification_digests,
            requires_selection and satisfaction.materialization_specification_id is None,
        )
    )


def _locked_input_or_constraint_invalid(
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    facts: ArtifactRequirementAvailability,
) -> bool:
    specifications = {
        specification.specification_id: specification for specification in contract.materialization_specifications
    }
    selected = specifications.get(satisfaction.materialization_specification_id)
    locked_input_ids = {locked_input.input_id for locked_input in contract.locked_inputs}
    required_locked_input_ids = set(selected.locked_input_ids) if selected is not None else locked_input_ids
    constraint_ids = {constraint.constraint_id for constraint in contract.constraints}
    return any(
        (
            set(satisfaction.locked_input_ids) != required_locked_input_ids,
            not required_locked_input_ids.issubset(facts.verified_locked_input_ids),
            set(satisfaction.satisfied_constraint_ids) != constraint_ids,
            not constraint_ids.issubset(facts.satisfied_constraint_ids),
        )
    )


def _artifact_realization_provenance(
    requirement: CompiledRealizationRequirement,
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
) -> RealizationProvenanceEntry:
    honoured = contract.explicitness is ExplicitnessClass.EXACT and contract.exact_artifact == satisfaction.artifact
    return RealizationProvenanceEntry(
        address=requirement.address,
        field_path=requirement.field_path,
        domain=requirement.domain,
        requirement_kind=requirement.requirement_kind,
        explicitness=requirement.explicitness,
        provenance=requirement.provenance if honoured else ExplicitnessProvenance.BACKEND_REALIZED,
        governing_scope=requirement.governing_scope,
        artifact_satisfaction=satisfaction,
    )


def _artifact_diagnostic(
    requirement: CompiledRealizationRequirement,
    code: str,
    reason: str,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain=requirement.domain,
        address=requirement.address,
        message=(
            f"{reason} Requirement '{requirement.requirement_kind}' at '{requirement.field_path}' cannot be admitted."
        ),
        severity=Severity.ERROR,
    )


def _artifact_mechanism_key(
    mechanism: ArtifactMechanismProfile,
) -> tuple[str, str, str, str]:
    return (
        mechanism.mechanism,
        mechanism.profile,
        mechanism.version,
        mechanism.digest,
    )


def _backend_route_supported(
    requirement: CompiledRealizationRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    manifest: BackendManifest,
) -> bool:
    selected = (
        _artifact_mechanism_key(satisfaction.mechanism),
        satisfaction.acquisition,
        satisfaction.timing,
    )
    return any(
        selected
        == (
            _artifact_mechanism_key(capability.mechanism),
            route.acquisition,
            route.timing,
        )
        for declaration in manifest.realization_support
        if declaration.domain == requirement.domain
        for capability in declaration.artifact_mechanisms
        if requirement.requirement_kind in capability.supported_requirement_kinds
        for route in capability.supported_routes
    )


def _trust_claims_verified(
    contract: ArtifactRequirement,
    satisfaction: ArtifactSatisfactionDisclosureModel,
    facts: ArtifactRequirementAvailability,
) -> bool:
    required_admission_refs = {
        *contract.trust_policy_refs,
        *(locked_input.trust_policy_ref for locked_input in contract.locked_inputs),
    }
    required_evidence_refs = {
        *contract.associated_artifact_manifest_refs,
        *(locked_input.associated_artifact_manifest_ref for locked_input in contract.locked_inputs),
    }
    disclosed_integrity = set(satisfaction.integrity_refs)
    disclosed_authenticity = set(satisfaction.authenticity_refs)
    disclosed_admission = set(satisfaction.admission_refs)
    disclosed_provenance = set(satisfaction.provenance_refs)
    disclosed_evidence = set(satisfaction.evidence_refs)
    return (
        satisfaction.artifact.digest in disclosed_integrity
        and disclosed_integrity.issubset(facts.verified_integrity_refs)
        and disclosed_authenticity.issubset(facts.verified_authenticity_refs)
        and required_admission_refs.issubset(disclosed_admission)
        and disclosed_admission.issubset(facts.verified_admission_refs)
        and disclosed_provenance.issubset(facts.verified_provenance_refs)
        and required_evidence_refs.issubset(disclosed_evidence)
        and disclosed_evidence.issubset(facts.verified_evidence_refs)
    )


def _silent_approximation_diagnostic(
    requirement: CompiledRealizationRequirement,
) -> Diagnostic:
    return Diagnostic(
        code=_BACKEND_CONTRACT_INVALID,
        domain=requirement.domain,
        address=requirement.address,
        message=(
            f"Backend did not realize the exact '{requirement.requirement_kind}' requirement at "
            f"'{requirement.field_path}' as the author declared it (the realized value is absent "
            "or differs); silent approximation or omission of an exact declaration is forbidden "
            "(SEM-218 I2)."
        ),
        severity=Severity.ERROR,
    )


__all__ = [
    "artifact_requirement_diagnostics",
    "evaluate_artifact_realization",
]
