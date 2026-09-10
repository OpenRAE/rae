"""Governed owner-specific structural and semantic projections."""

from __future__ import annotations

from pydantic import BaseModel
from raes.phase_contracts import ResolvedImportProvenance
from raes.scenario import Scenario
from raes_contracts.contracts import (
    ExperimentCaptureSpecModel,
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ExternalConceptBindingDocumentModel,
)

ArtifactForProjection = (
    Scenario
    | ResolvedImportProvenance
    | ExperimentTaskModel
    | ExperimentRunModel
    | ExperimentCaptureSpecModel
    | ExperimentStudyModel
    | ExternalConceptBindingDocumentModel
)

_SCENARIO_DECLARATION_FIELDS = (
    "nodes",
    "infrastructure",
    "features",
    "conditions",
    "propositions",
    "assertions",
    "entities",
    "injects",
    "events",
    "scripts",
    "stories",
    "content",
    "generated_artifacts",
    "persistent_volumes",
    "accounts",
    "identity_domains",
    "identity_forests",
    "identity_facades",
    "deployment_tenants",
    "deployment_cells",
    "relationships",
    "agents",
    "action_contracts",
    "observation_boundaries",
    "outcome_interpretation_rules",
    "behavior_specifications",
    "evidence_requirements",
    "time_domains",
    "clocks",
    "time_domain_mappings",
    "time_progression_policies",
    "temporal_constraints",
    "objectives",
    "workflows",
    "variables",
    "variation_points",
)

_SCENARIO_SEMANTIC_FIELDS = {
    "name",
    "version",
    *_SCENARIO_DECLARATION_FIELDS,
    "forwarding_agents",
    "module",
    "imports",
    "realization",
}


def _owner_semantic_payload(artifact: ArtifactForProjection) -> object:
    """Return the governed semantic projection selected by the artifact owner."""

    payload: object | None = None
    if isinstance(artifact, Scenario):
        payload = _scenario_semantic_payload(artifact)
    elif isinstance(artifact, ResolvedImportProvenance):
        payload = _module_semantic_payload(artifact)
    elif isinstance(artifact, ExperimentTaskModel):
        payload = _task_semantic_payload(artifact)
    elif isinstance(artifact, ExperimentRunModel):
        payload = _run_semantic_payload(artifact)
    elif isinstance(artifact, ExperimentCaptureSpecModel):
        payload = _capture_spec_semantic_payload(artifact)
    elif isinstance(artifact, ExperimentStudyModel):
        payload = _study_semantic_payload(artifact)
    elif isinstance(artifact, ExternalConceptBindingDocumentModel):
        payload = {"bindings": artifact.model_dump(mode="json", include={"bindings"})["bindings"]}
    if payload is None:
        raise TypeError("semantic projection requires an admitted RAES artifact model")
    return payload


def _scenario_semantic_payload(artifact: Scenario) -> object:
    return _without_editorial_description(artifact.model_dump(mode="json", include=_SCENARIO_SEMANTIC_FIELDS))


def _module_semantic_payload(artifact: ResolvedImportProvenance) -> object:
    return {
        "module_id": artifact.module_id,
        "module_version": artifact.module_version,
        "export_hash": artifact.export_hash,
        "bindings": [binding.model_dump(mode="json") for binding in artifact.bindings],
    }


def _task_semantic_payload(artifact: ExperimentTaskModel) -> object:
    return artifact.model_dump(
        mode="json",
        include={
            "schema_version",
            "task_id",
            "task_version",
            "scenario_ref",
            "evaluation_protocol",
            "intended_use",
            "non_use",
            "population_or_construct",
            "split_and_leakage_controls",
            "apparatus_constraints",
            "validity_notes",
            "artifact_refs",
            "validation_basis_disclosures",
        },
    )


def _run_semantic_payload(artifact: ExperimentRunModel) -> object:
    return artifact.model_dump(
        mode="json",
        include={
            "schema_version",
            "run_id",
            "run_version",
            "task_ref",
            "scenario_snapshot_ref",
            "trial_provenance",
            "difficulty_provenance",
            "apparatus_context",
            "participant_implementation_provenance",
            "parameter_set",
            "realized_bindings",
            "stochastic_controls",
            "stochastic_draws",
            "started_at",
            "ended_at",
            "clock_context",
            "realized_time_model",
            "run_status",
            "outcome_status",
            "traceability",
            "realized_form_disclosures",
            "augmentation_disclosures",
            "evidence_artifacts",
            "result_summaries",
            "deviations",
            "invalidation",
            "used_refs",
            "generated_refs",
            "derived_from_refs",
            "validation_basis_disclosures",
        },
    )


def _capture_spec_semantic_payload(artifact: ExperimentCaptureSpecModel) -> object:
    return artifact.model_dump(
        mode="json",
        include={
            "schema_version",
            "capture_spec_id",
            "spec_version",
            "scope_refs",
            "capture_windows",
            "capture_requirements",
            "validity_notes",
            "artifact_refs",
        },
    )


def _study_semantic_payload(artifact: ExperimentStudyModel) -> object:
    payload = artifact.model_dump(
        mode="json",
        include={
            "schema_version",
            "study_id",
            "study_version",
            "study_kind",
            "purpose",
            "research_questions",
            "behavioral_claims",
            "inclusion_criteria",
            "factors",
            "run_allocation",
            "analysis_plan",
            "validity_notes",
            "report_artifacts",
            "export_artifacts",
            "validation_basis_disclosures",
        },
    )
    payload["membership"] = {
        key: _study_member_semantics(member) for key, member in sorted(artifact.membership.items())
    }
    return payload


def _owner_structural_payload(artifact: ArtifactForProjection) -> object:
    """Return a closed owner-specific shape projection, not a recursive JSON shape."""

    payload: object | None = None
    if isinstance(artifact, Scenario):
        payload = _scenario_structural_payload(artifact)
    elif isinstance(artifact, ResolvedImportProvenance):
        payload = _module_structural_payload(artifact)
    elif isinstance(artifact, ExperimentTaskModel):
        payload = _task_structural_payload(artifact)
    elif isinstance(artifact, ExperimentRunModel):
        payload = _run_structural_payload(artifact)
    elif isinstance(artifact, ExperimentCaptureSpecModel):
        payload = _capture_spec_structural_payload(artifact)
    elif isinstance(artifact, ExperimentStudyModel):
        payload = _study_structural_payload(artifact)
    elif isinstance(artifact, ExternalConceptBindingDocumentModel):
        payload = _external_bindings_structural_payload(artifact)
    if payload is None:
        raise TypeError("structural projection requires an admitted RAES artifact model")
    return payload


def _scenario_structural_payload(artifact: Scenario) -> object:
    return {
        "declarations": {
            field_name: sorted(getattr(artifact, field_name)) for field_name in _SCENARIO_DECLARATION_FIELDS
        },
        "forwarding_agent_count": len(artifact.forwarding_agents),
        "has_module_descriptor": artifact.module is not None,
        "import_namespaces": sorted(item.namespace for item in artifact.imports),
        "has_realization_designation": artifact.realization is not None,
    }


def _module_structural_payload(artifact: ResolvedImportProvenance) -> object:
    return {
        "namespace_depth": len(artifact.namespace),
        "binding_parameters": sorted(".".join(binding.parameter) for binding in artifact.bindings),
        "has_export_surface": bool(artifact.export_hash),
    }


def _task_structural_payload(artifact: ExperimentTaskModel) -> object:
    return {
        "scenario_reference_kind": artifact.scenario_ref.ref_kind,
        "evaluation_protocol_fields": sorted(artifact.evaluation_protocol.model_fields_set),
        "non_use_count": len(artifact.non_use),
        "artifact_ref_count": len(artifact.artifact_refs),
        "validation_basis_count": len(artifact.validation_basis_disclosures),
    }


def _run_structural_payload(artifact: ExperimentRunModel) -> object:
    return {
        "task_reference_kind": artifact.task_ref.ref_kind,
        "scenario_reference_kind": artifact.scenario_snapshot_ref.ref_kind,
        "result_summary_ids": sorted(artifact.result_summaries),
        "evidence_artifact_count": len(artifact.evidence_artifacts),
        "used_ref_kinds": sorted(item.ref_kind for item in artifact.used_refs),
        "generated_ref_kinds": sorted(item.ref_kind for item in artifact.generated_refs),
        "derived_ref_kinds": sorted(item.ref_kind for item in artifact.derived_from_refs),
    }


def _capture_spec_structural_payload(artifact: ExperimentCaptureSpecModel) -> object:
    return {
        "scope_ref_kinds": sorted(item.ref_kind for item in artifact.scope_refs),
        "window_ids": sorted(item.window_id for item in artifact.capture_windows),
        "requirement_ids": sorted(artifact.capture_requirements),
        "artifact_ref_count": len(artifact.artifact_refs),
    }


def _study_structural_payload(artifact: ExperimentStudyModel) -> object:
    return {
        "membership": {
            key: {"role": member.role, "target_kind": member.target_ref.ref_kind}
            for key, member in sorted(artifact.membership.items())
        },
        "factor_ids": sorted(artifact.factors),
        "has_run_allocation": artifact.run_allocation is not None,
        "has_analysis_plan": artifact.analysis_plan is not None,
    }


def _external_bindings_structural_payload(artifact: ExternalConceptBindingDocumentModel) -> object:
    return {
        "bindings": {
            key: {
                "relationship_kind": binding.assertion.relationship_kind,
                "subject_kind": binding.subject.subject_kind,
                "lifecycle_phase": binding.subject.lifecycle_phase,
            }
            for key, binding in sorted(artifact.bindings.items())
        }
    }


def _study_member_semantics(member: BaseModel) -> dict[str, object]:
    payload = member.model_dump(mode="json", include={"target_ref", "role", "grouping"})
    return payload


def _without_editorial_description(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_editorial_description(item) for key, item in sorted(value.items()) if key != "description"
        }
    if isinstance(value, list):
        return [_without_editorial_description(item) for item in value]
    return value


__all__: list[str] = []
