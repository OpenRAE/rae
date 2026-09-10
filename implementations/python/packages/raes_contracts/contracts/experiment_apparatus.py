"""Experiment task and apparatus-context contracts and validators."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..observation_demand import ObservationDemandDocument
from ..versions import (
    BACKEND_MANIFEST_V2_SCHEMA_VERSION,
    EXPERIMENT_APPARATUS_CONTEXT_SCHEMA_VERSION,
    EXPERIMENT_TASK_SCHEMA_VERSION,
    PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION,
    PROCESSOR_MANIFEST_V2_SCHEMA_VERSION,
)
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString, _canonical_digest, _parse_rfc3339_datetime
from .capabilities import ApparatusIdentityModel
from .experiment_artifacts import (
    ExperimentApparatusCompatibilityReferenceModel,
    ExperimentArtifactRefModel,
    ExperimentMeasurementChannelReferenceModel,
    _format_reference,
    _identity_matches_reference,
    _manifest_reference_key,
    _reference_satisfies_requirement,
)
from .experiment_capture import ExperimentValidityNoteModel
from .experiment_disclosure import (
    ExperimentApparatusConstraintModel,
    ExperimentEvaluationProtocolModel,
    ExperimentSplitAndLeakageControlsModel,
)
from .experiment_manifest_references import ExperimentManifestReferenceModel
from .experiment_references import (
    ExperimentParameterModel,
    ExperimentReferenceModel,
    ExperimentScenarioReferenceModel,
)
from .manifests import ProcessorManifestV2Model
from .participant_manifests import BackendManifestV2Model
from .random_stream import RandomStreamControlBindingModel
from .schema_invariants import _add_carrier_validation_basis_disclosure_invariant, _add_raes_invariant
from .validation_disclosure import ValidationBasisDisclosureModel, validate_carrier_validation_basis_disclosures

_ManifestReferenceKey = tuple[
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]


class ExperimentTaskModel(ContractModel):
    """Experiment task contract that separates scenario material from protocol intent."""

    schema_version: Literal[EXPERIMENT_TASK_SCHEMA_VERSION]
    task_id: NonEmptyString
    task_version: NonEmptyString
    title: NonEmptyString
    description: NonEmptyString
    scenario_ref: ExperimentScenarioReferenceModel
    evaluation_protocol: ExperimentEvaluationProtocolModel
    intended_use: NonEmptyString
    non_use: list[NonEmptyString] = Field(default_factory=list)
    population_or_construct: NonEmptyString
    split_and_leakage_controls: ExperimentSplitAndLeakageControlsModel
    apparatus_constraints: ExperimentApparatusConstraintModel
    validity_notes: list[ExperimentValidityNoteModel] = Field(min_length=1)
    artifact_refs: list[ExperimentArtifactRefModel] = Field(min_length=1)
    validation_basis_disclosures: list[ValidationBasisDisclosureModel] = Field(default_factory=list)
    observation_demands: ObservationDemandDocument | None = None

    @model_validator(mode="after")
    def _validate_task_validation_basis_disclosures(self) -> ExperimentTaskModel:
        validate_carrier_validation_basis_disclosures(self, subject_kind="experiment_task")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_carrier_validation_basis_disclosure_invariant(
            json_schema, contract_id="experiment-task-v1", subject_kind="experiment_task"
        )
        return json_schema


class ExperimentStochasticControlModel(ContractModel):
    """Seed, randomization, sampling, or scheduler control for reproducibility."""

    control_id: NonEmptyString
    role: Literal["seed", "randomization", "sampling", "scheduler", "agent-policy", "other"]
    value: str | int | None = None
    description: NonEmptyString | None = None
    executable_binding: RandomStreamControlBindingModel | None = None


class ExperimentClockContextModel(ContractModel):
    """Clock authority and time-domain metadata for run interpretation."""

    clock_id: NonEmptyString
    authority: NonEmptyString
    time_domain: Literal["wall-clock", "monotonic", "simulated", "logical", "other"]
    synchronization: NonEmptyString | None = None


class ExperimentApparatusComponentModel(ContractModel):
    """Identity and manifest context for one apparatus component."""

    component_kind: Literal[
        "processor",
        "backend",
        "participant-implementation",
        "host",
        "container",
        "vm",
        "network",
        "device",
        "measurement-channel",
        "other",
    ]
    identity: ApparatusIdentityModel
    manifest_ref: ExperimentManifestReferenceModel | None = None
    compatibility_refs: list[ExperimentApparatusCompatibilityReferenceModel] = Field(default_factory=list)
    observed: bool = False
    limitations: list[NonEmptyString] = Field(default_factory=list)


class ExperimentApparatusContextModel(ContractModel):
    """Run-scoped apparatus context for interpreting experiment evidence."""

    schema_version: Literal[EXPERIMENT_APPARATUS_CONTEXT_SCHEMA_VERSION]
    apparatus_context_id: NonEmptyString
    context_version: NonEmptyString
    declared_at: Rfc3339DateTimeString
    components: dict[NonEmptyString, ExperimentApparatusComponentModel] = Field(min_length=2)
    selected_manifests: list[ExperimentManifestReferenceModel] = Field(min_length=1)
    compatibility_declarations: list[ExperimentApparatusCompatibilityReferenceModel] = Field(min_length=1)
    configuration_parameters: list[ExperimentParameterModel] = Field(min_length=1)
    stochastic_controls: list[ExperimentStochasticControlModel] = Field(min_length=1)
    clocks: list[ExperimentClockContextModel] = Field(min_length=1)
    measurement_channels: list[ExperimentMeasurementChannelReferenceModel] = Field(min_length=1)
    observed_setup_evidence: list[ExperimentArtifactRefModel] = Field(min_length=1)
    known_limitations: list[ExperimentValidityNoteModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_instrument_context(self) -> ExperimentApparatusContextModel:
        _parse_rfc3339_datetime("declared_at", self.declared_at)
        processor, backend = _require_processor_and_backend_components(self.components)
        selected_manifest_keys = _validate_selected_manifest_subject_uniqueness(self.selected_manifests)
        canonical_component_manifest_keys = _validate_core_component_manifest_refs(
            processor, backend, selected_manifest_keys
        )
        _validate_participant_component_manifest_refs(self.components, selected_manifest_keys)
        _validate_digest_qualified_manifests_are_canonical(self.selected_manifests, canonical_component_manifest_keys)
        _validate_observed_setup_evidence_present(self.observed_setup_evidence)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        components_schema = json_schema.get("properties", {}).get("components")
        if isinstance(components_schema, dict):
            components_schema.setdefault("required", ["processor", "backend"])
            components_schema.setdefault("allOf", []).extend(
                [
                    {
                        "properties": {
                            "processor": {
                                "required": ["component_kind", "identity", "manifest_ref"],
                                "properties": {
                                    "component_kind": {"const": "processor"},
                                    "manifest_ref": {"type": "object"},
                                },
                            }
                        }
                    },
                    {
                        "properties": {
                            "backend": {
                                "required": ["component_kind", "identity", "manifest_ref"],
                                "properties": {
                                    "component_kind": {"const": "backend"},
                                    "manifest_ref": {"type": "object"},
                                },
                            }
                        }
                    },
                ]
            )
        _add_raes_invariant(
            json_schema,
            "canonical-apparatus-manifest-selected",
            "The canonical processor and backend component manifest_ref values must be present in selected_manifests; "
            "digest-qualified selected manifests must be canonical component manifests.",
            validator="raes_contracts.contracts.ExperimentApparatusContextModel._validate_instrument_context",
            inputs=[{"contract_id": "experiment-apparatus-context-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "apparatus-manifest-payload-identity-valid",
            "Canonical processor and backend manifest_ref values must resolve to manifest payloads with matching "
            "identities and mutual compatibility declarations.",
            validator="raes_contracts.contracts.validate_experiment_apparatus_context_against_manifests",
            inputs=[
                {"contract_id": "experiment-apparatus-context-v1", "instance_path": "#"},
                {"contract_id": "processor-manifest-v2", "instance_path": "#"},
                {"contract_id": "backend-manifest-v2", "instance_path": "#"},
            ],
        )
        return json_schema


def _require_processor_and_backend_components(
    components: dict[str, ExperimentApparatusComponentModel],
) -> tuple[ExperimentApparatusComponentModel, ExperimentApparatusComponentModel]:
    processor = components.get("processor")
    backend = components.get("backend")
    if processor is None or processor.component_kind != "processor":
        raise ValueError("apparatus components must include a 'processor' component with component_kind='processor'")
    if backend is None or backend.component_kind != "backend":
        raise ValueError("apparatus components must include a 'backend' component with component_kind='backend'")
    return processor, backend


def _validate_selected_manifest_subject_uniqueness(
    selected_manifests: list[ExperimentManifestReferenceModel],
) -> set[_ManifestReferenceKey]:
    selected_manifest_subject_keys: dict[tuple[str, str, str | None, str | None], str] = {}
    for selected_manifest in selected_manifests:
        selected_subject_ref = selected_manifest.subject_ref
        if selected_subject_ref is None:
            continue
        selected_subject_key = (
            selected_subject_ref.ref_kind,
            selected_subject_ref.ref_id,
            selected_subject_ref.ref_version,
            selected_manifest.ref_version,
        )
        prior_manifest_id = selected_manifest_subject_keys.get(selected_subject_key)
        if prior_manifest_id is not None:
            raise ValueError(
                "selected_manifests must not contain multiple manifest refs for the same subject identity "
                f"and manifest schema version: {selected_subject_ref.ref_kind}:{selected_subject_ref.ref_id}"
            )
        selected_manifest_subject_keys[selected_subject_key] = selected_manifest.ref_id
    return {_manifest_reference_key(ref) for ref in selected_manifests}


def _validate_component_manifest_ref_identity(
    *, key: str, component: ExperimentApparatusComponentModel, label: str, expected_ref_kind: str
) -> ExperimentManifestReferenceModel:
    if component.manifest_ref is None:
        raise ValueError(f"{label} component '{key}' must include manifest_ref")
    subject_ref = component.manifest_ref.subject_ref
    if subject_ref is None:
        raise ValueError(f"{label} component '{key}' manifest_ref must include subject_ref")
    if subject_ref.ref_kind != expected_ref_kind:
        raise ValueError(f"{label} component '{key}' manifest_ref subject_ref must use ref_kind='{expected_ref_kind}'")
    if component.manifest_ref.ref_id != component.identity.name:
        raise ValueError(f"{label} component '{key}' manifest_ref ref_id must match component identity")
    if subject_ref.ref_id != component.identity.name or subject_ref.ref_version != component.identity.version:
        raise ValueError(f"{label} component '{key}' manifest_ref subject_ref must match component identity")
    if subject_ref.ref_digest is not None or subject_ref.ref_path is not None:
        raise ValueError(f"{label} component '{key}' manifest_ref subject_ref must not carry ref_digest or ref_path")
    return component.manifest_ref


def _validate_core_component_manifest_refs(
    processor: ExperimentApparatusComponentModel,
    backend: ExperimentApparatusComponentModel,
    selected_manifest_keys: set[_ManifestReferenceKey],
) -> set[_ManifestReferenceKey]:
    canonical_component_manifest_keys: set[_ManifestReferenceKey] = set()
    for key, component in (("processor", processor), ("backend", backend)):
        manifest_ref = _validate_component_manifest_ref_identity(
            key=key, component=component, label="apparatus", expected_ref_kind=key
        )
        expected_manifest_version = (
            PROCESSOR_MANIFEST_V2_SCHEMA_VERSION if key == "processor" else BACKEND_MANIFEST_V2_SCHEMA_VERSION
        )
        if manifest_ref.ref_version != expected_manifest_version:
            raise ValueError(
                f"apparatus component '{key}' manifest_ref must use ref_version='{expected_manifest_version}'"
            )
        component_manifest_key = _manifest_reference_key(manifest_ref)
        canonical_component_manifest_keys.add(component_manifest_key)
        if component_manifest_key not in selected_manifest_keys:
            raise ValueError(f"apparatus component '{key}' manifest_ref must be present in selected_manifests")
    return canonical_component_manifest_keys


def _validate_participant_component_manifest_refs(
    components: dict[str, ExperimentApparatusComponentModel],
    selected_manifest_keys: set[_ManifestReferenceKey],
) -> None:
    participant_components = {
        key: component
        for key, component in components.items()
        if component.component_kind == "participant-implementation"
    }
    for key, component in participant_components.items():
        manifest_ref = _validate_component_manifest_ref_identity(
            key=key,
            component=component,
            label="participant implementation",
            expected_ref_kind="participant-implementation",
        )
        if manifest_ref.ref_version != PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION:
            raise ValueError(
                f"participant implementation component '{key}' manifest_ref must use "
                f"ref_version='{PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION}'"
            )
        if _manifest_reference_key(manifest_ref) not in selected_manifest_keys:
            raise ValueError(
                f"participant implementation component '{key}' manifest_ref must be present in selected_manifests"
            )


def _validate_digest_qualified_manifests_are_canonical(
    selected_manifests: list[ExperimentManifestReferenceModel],
    canonical_component_manifest_keys: set[_ManifestReferenceKey],
) -> None:
    for selected_manifest in selected_manifests:
        if (
            selected_manifest.ref_digest is not None
            and _manifest_reference_key(selected_manifest) not in canonical_component_manifest_keys
        ):
            raise ValueError(
                "digest-qualified selected_manifests must be canonical processor/backend component manifest refs"
            )


def _validate_observed_setup_evidence_present(
    observed_setup_evidence: list[ExperimentArtifactRefModel],
) -> None:
    if not any(artifact.role == "apparatus-evidence" for artifact in observed_setup_evidence):
        raise ValueError("observed_setup_evidence must include at least one apparatus-evidence artifact")


def _component_identity_satisfies_allowed_refs(
    component: ExperimentApparatusComponentModel,
    allowed_refs: list[ExperimentReferenceModel],
) -> bool:
    return any(_identity_matches_reference(component.identity, allowed_ref) for allowed_ref in allowed_refs)


def _apparatus_capability_ids(apparatus_context: ExperimentApparatusContextModel) -> set[str]:
    capability_ids = {
        reference.ref_id
        for reference in apparatus_context.compatibility_declarations
        if reference.ref_kind == "capability"
    }
    for component in apparatus_context.components.values():
        capability_ids.update(
            reference.ref_id for reference in component.compatibility_refs if reference.ref_kind == "capability"
        )
    return capability_ids


def _validate_apparatus_context_satisfies_constraints(
    apparatus_constraints: ExperimentApparatusConstraintModel,
    apparatus_context: ExperimentApparatusContextModel,
) -> None:
    processor = apparatus_context.components["processor"]
    backend = apparatus_context.components["backend"]

    if apparatus_constraints.allowed_processor_refs and not _component_identity_satisfies_allowed_refs(
        processor,
        apparatus_constraints.allowed_processor_refs,
    ):
        allowed = ", ".join(_format_reference(reference) for reference in apparatus_constraints.allowed_processor_refs)
        raise ValueError(f"run apparatus processor identity must satisfy task allowed_processor_refs: {allowed}")

    if apparatus_constraints.allowed_backend_refs and not _component_identity_satisfies_allowed_refs(
        backend,
        apparatus_constraints.allowed_backend_refs,
    ):
        allowed = ", ".join(_format_reference(reference) for reference in apparatus_constraints.allowed_backend_refs)
        raise ValueError(f"run apparatus backend identity must satisfy task allowed_backend_refs: {allowed}")

    missing_manifests = sorted(
        _format_reference(required_manifest)
        for required_manifest in apparatus_constraints.required_manifest_refs
        if not any(
            _reference_satisfies_requirement(selected_manifest, required_manifest)
            for selected_manifest in apparatus_context.selected_manifests
        )
    )
    if missing_manifests:
        joined = ", ".join(missing_manifests)
        raise ValueError(f"run apparatus selected_manifests must satisfy task required_manifest_refs: {joined}")

    available_capabilities = _apparatus_capability_ids(apparatus_context)
    missing_capabilities = sorted(
        capability
        for capability in apparatus_constraints.required_capabilities
        if capability not in available_capabilities
    )
    if missing_capabilities:
        joined = ", ".join(missing_capabilities)
        raise ValueError(f"run apparatus capabilities must satisfy task required_capabilities: {joined}")


def _validate_component_manifest_payload(
    *,
    component_key: Literal["processor", "backend"],
    component: ExperimentApparatusComponentModel,
    manifest: ProcessorManifestV2Model | BackendManifestV2Model,
    expected_schema_version: str,
    supplied_digest: str | None,
) -> None:
    if component.manifest_ref is None:
        raise ValueError(f"apparatus component '{component_key}' must include manifest_ref")
    if component.manifest_ref.ref_id != manifest.identity.name:
        raise ValueError(f"apparatus component '{component_key}' manifest_ref ref_id must match manifest identity name")
    if component.manifest_ref.ref_version != expected_schema_version:
        raise ValueError(
            f"apparatus component '{component_key}' manifest_ref ref_version must match manifest schema_version"
        )
    if component.identity.name != manifest.identity.name or component.identity.version != manifest.identity.version:
        raise ValueError(f"apparatus component '{component_key}' identity must match manifest identity")
    subject_ref = component.manifest_ref.subject_ref
    if subject_ref is None:
        raise ValueError(f"apparatus component '{component_key}' manifest_ref must include subject_ref")
    if not _identity_matches_reference(manifest.identity, subject_ref):
        raise ValueError(f"apparatus component '{component_key}' manifest_ref subject_ref must match manifest identity")
    _validate_component_manifest_digest_match(
        component_key=component_key,
        manifest_ref=component.manifest_ref,
        supplied_digest=supplied_digest,
    )


def _validate_component_manifest_digest_match(
    *,
    component_key: Literal["processor", "backend"],
    manifest_ref: ExperimentManifestReferenceModel,
    supplied_digest: str | None,
) -> None:
    if manifest_ref.ref_digest is None:
        return
    if supplied_digest is None:
        raise ValueError(
            f"apparatus component '{component_key}' manifest_ref digest requires a supplied manifest payload digest"
        )
    if _canonical_digest(manifest_ref.ref_digest) != _canonical_digest(supplied_digest):
        raise ValueError(
            f"apparatus component '{component_key}' manifest_ref digest must match manifest payload digest"
        )


def validate_experiment_apparatus_context_against_manifests(
    apparatus_context: ExperimentApparatusContextModel,
    processor_manifest: ProcessorManifestV2Model,
    backend_manifest: BackendManifestV2Model,
    *,
    processor_manifest_digest: str | None = None,
    backend_manifest_digest: str | None = None,
) -> None:
    """Validate apparatus manifest references against concrete manifest payloads."""

    _validate_component_manifest_payload(
        component_key="processor",
        component=apparatus_context.components["processor"],
        manifest=processor_manifest,
        expected_schema_version=PROCESSOR_MANIFEST_V2_SCHEMA_VERSION,
        supplied_digest=processor_manifest_digest,
    )
    _validate_component_manifest_payload(
        component_key="backend",
        component=apparatus_context.components["backend"],
        manifest=backend_manifest,
        expected_schema_version=BACKEND_MANIFEST_V2_SCHEMA_VERSION,
        supplied_digest=backend_manifest_digest,
    )
    if backend_manifest.identity.name not in processor_manifest.compatibility.backends:
        raise ValueError(
            "processor manifest compatibility.backends must include the selected backend manifest identity"
        )
    if processor_manifest.identity.name not in backend_manifest.compatibility.processors:
        raise ValueError(
            "backend manifest compatibility.processors must include the selected processor manifest identity"
        )
