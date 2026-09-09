"""Leaf component contracts for the admitted experiment trial-plan (SCE-002/SCE-006).

These are the closed sub-models composed by :mod:`admitted_trial_plan`: the
versioned profile set, pinned input references, per-entry selection/binding/
apparatus/execution-control/provenance records, and the bounded admission
disclosure. They reuse owning contracts rather than duplicating meaning; the
entry and plan models, the acyclic digest chain, and the seal helpers live in
:mod:`admitted_trial_plan`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator
from raes.identifiers import PortableIdentifier

from ..diagnostics import DiagnosticModel
from .base import ContractModel, NonEmptyString, PositiveInteger, PrefixedDigestString
from .experiment_bindings import ExperimentBindingDescriptorModel
from .experiment_manifest_references import ExperimentManifestReferenceModel
from .experiment_references import (
    ExperimentReferenceModel,
    ExperimentTaskReferenceModel,
)
from .experiment_selection import ExperimentSelectionOutcomeModel
from .realization_plans import RealizationEnvelopeIdentityModel

SelectionPolicyKind = Literal["fixed", "enumerate", "product", "stratified", "sample"]
BindingOrigin = Literal["selection", "default"]

#: The plan's single supported random-stream profile for v1; every stochastic
#: control's executable binding must name it (enforced in the plan-local join).
ADMITTED_TRIAL_RANDOM_STREAM_PROFILE = "blake3-xof-v1"


class AdmittedTrialPlanProfilesModel(ContractModel):
    """Exact versioned profile set fixing the plan's compatibility surface.

    ADR-084 extensibility seam: a new coordinate dimension, identity algorithm,
    random transform, cleanup action, or execution-control policy adds one
    governed profile version, never a generic parameter bag. Each field is a
    closed literal of the versions this contract implements, so the *published*
    JSON Schema — not just the Python validator — encodes the supported set as a
    ``const``/``enum`` and every implementation fails closed on an unknown
    canonicalization, integrity, isolation, cleanup, or execution-control
    profile. A new profile version adds a literal alternative here together with
    the semantics that implement it.
    """

    coordinate_profile: Literal["trial-coordinate-v1"]
    entry_identity_profile: Literal["trial-entry-identity-v1"]
    run_identity_profile: Literal["archival-run-identity-v1"]
    canonicalization_profile: Literal["jcs-sha256-v1"]
    integrity_profile: Literal["acyclic-digest-chain-v1"]
    compiler_profile: Literal["trial-compiler-v1"]
    selection_policy_profile: Literal["experiment-selection-v1"]
    random_stream_profile: Literal["blake3-xof-v1"]
    execution_control_profile: Literal["attempt-control-v1"]
    cleanup_profile: Literal["trial-cleanup-v1"]
    isolation_profile: Literal["scheduler-isolation-v1"]


class ExperimentScenarioFamilyReferenceModel(ContractModel):
    """Digest-pinned identity of one semantically admitted expanded SDL family."""

    ref_kind: Literal["scenario-family"]
    ref_id: NonEmptyString
    ref_version: Literal["expanded-scenario-family/v1"]
    ref_digest: PrefixedDigestString


def _require_ref(ref: ExperimentReferenceModel, kind: str, *, digest: bool, field: str) -> None:
    if ref.ref_kind != kind:
        raise ValueError(f"{field} must have ref_kind {kind!r}")
    if digest and ref.ref_digest is None:
        raise ValueError(f"{field} must pin a ref_digest")


class AdmittedTrialPlanInputRefsModel(ContractModel):
    """Pinned, digest-bound references to the admitted plan's exact inputs (SVR-023)."""

    authoring_input_ref: ExperimentReferenceModel
    task_ref: ExperimentTaskReferenceModel
    task_digest: PrefixedDigestString
    scenario_family_ref: ExperimentScenarioFamilyReferenceModel
    capture_spec_refs: list[ExperimentReferenceModel] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    binding_descriptor_set_ref: ExperimentReferenceModel | None = None
    study_ref: ExperimentReferenceModel | None = None
    associated_artifact_set_ref: ExperimentReferenceModel | None = None

    @model_validator(mode="after")
    def _validate_input_refs(self) -> AdmittedTrialPlanInputRefsModel:
        _require_ref(self.authoring_input_ref, "authoring-input", digest=True, field="authoring_input_ref")
        for reference in self.capture_spec_refs:
            _require_ref(reference, "capture-spec", digest=True, field="capture_spec_refs")
        capture_keys = {(reference.ref_id, reference.ref_version) for reference in self.capture_spec_refs}
        if len(capture_keys) != len(self.capture_spec_refs):
            raise ValueError("capture_spec_refs must identify unique capture specifications")
        if self.binding_descriptor_set_ref is not None:
            _require_ref(self.binding_descriptor_set_ref, "other", digest=True, field="binding_descriptor_set_ref")
        if self.study_ref is not None:
            _require_ref(self.study_ref, "study", digest=False, field="study_ref")
        if self.associated_artifact_set_ref is not None:
            _require_ref(self.associated_artifact_set_ref, "other", digest=True, field="associated_artifact_set_ref")
        return self


class AdmittedSelectionRecordModel(ContractModel):
    """One resolved variation selection with its selection-policy origin as provenance."""

    variation_point_id: PortableIdentifier
    origin_policy_id: PortableIdentifier
    origin_policy_kind: SelectionPolicyKind
    outcome: ExperimentSelectionOutcomeModel


class AdmittedBindingModel(ContractModel):
    """One admitted binding: an authoritative descriptor plus admitted origin.

    This is admitted intent, not realized provenance; #790 and the run contract
    own actual realization.
    """

    descriptor: ExperimentBindingDescriptorModel
    origin: BindingOrigin


class AdmittedParticipantManifestReferenceModel(ContractModel):
    """Digest-pinned participant implementation manifest authority."""

    participant_address: NonEmptyString
    implementation_name: NonEmptyString
    implementation_version: NonEmptyString
    manifest_version: NonEmptyString
    manifest_digest: PrefixedDigestString


class AdmittedApparatusBindingModel(ContractModel):
    """Pre-run apparatus selection intent pinned by manifest and realization envelope.

    SVR-029 envelope-governed realization: the entry pins selected apparatus
    claims. It is admitted intent, never a fabricated, observed
    ``ExperimentApparatusContextModel``.
    """

    manifest_refs: list[ExperimentManifestReferenceModel] = Field(min_length=1)
    participant_manifest_refs: list[AdmittedParticipantManifestReferenceModel] = Field(default_factory=list)
    realization_envelope: RealizationEnvelopeIdentityModel
    capability_refs: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_apparatus(self) -> AdmittedApparatusBindingModel:
        if len(self.capability_refs) != len(set(self.capability_refs)):
            raise ValueError("apparatus capability_refs must be unique")
        for manifest_ref in self.manifest_refs:
            if manifest_ref.ref_digest is None:
                raise ValueError(
                    "admitted apparatus manifest references must be digest-pinned to a concrete "
                    "processor/backend manifest payload; id/version-only references are not sealable"
                )
        participant_keys = [
            (
                reference.participant_address,
                reference.implementation_name,
                reference.implementation_version,
                reference.manifest_version,
            )
            for reference in self.participant_manifest_refs
        ]
        if len(participant_keys) != len(set(participant_keys)):
            raise ValueError("apparatus participant_manifest_refs must identify unique participant manifests")
        return self

    @model_serializer(mode="wrap")
    def _serialize_optional_participant_manifest_refs(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = handler(self)
        if not self.participant_manifest_refs:
            payload.pop("participant_manifest_refs", None)
        return payload


class AdmittedExecutionControlModel(ContractModel):
    """Minimal schedule-independent attempt policy.

    Carries only whole-trial attempt timeout, the required cancellation/timeout
    disposition, and the cleanup-plan reference. The reset/compensation retry
    policy is owned by the referenced ``TrialCleanupPlanModel.retry_policy`` and
    is not duplicated here, so a sealed plan cannot hold two contradicting retry
    policies. It never carries worker, queue, placement, host, lease, or mutable
    status data.
    """

    attempt_timeout_seconds: PositiveInteger
    on_timeout: Literal["cancel", "abort", "cleanup-and-fail"]
    on_cancellation: Literal["abort", "cleanup-and-fail"]
    cleanup_plan_ref: NonEmptyString


class AdmittedInstantiationProvenanceModel(ContractModel):
    """Plan/run/family linkage that becomes instantiated-snapshot identity (SVR-025)."""

    plan_id: NonEmptyString
    plan_entry_id: NonEmptyString
    run_id: NonEmptyString
    scenario_family_id: NonEmptyString


class AdmittedTrialPlanAdmissionModel(ContractModel):
    """Bounded admission success facts and limitations.

    A sealed plan may carry safe success-stage/count facts and limitations plus
    bounded diagnostics; it never carries failed partial entries or raw
    validation payloads. The portable lifecycle has exactly one successful
    state — admitted and sealed — so ``admitted_at_stage`` is a closed literal
    and a caller cannot seal a plan marked ``partial``/``failed``.
    """

    admitted_at_stage: Literal["admitted-sealed"]
    entry_count: PositiveInteger
    limitations: list[NonEmptyString] = Field(default_factory=list)
    diagnostics: list[DiagnosticModel] = Field(default_factory=list)


__all__ = [
    "AdmittedApparatusBindingModel",
    "AdmittedBindingModel",
    "AdmittedExecutionControlModel",
    "AdmittedInstantiationProvenanceModel",
    "AdmittedSelectionRecordModel",
    "AdmittedTrialPlanAdmissionModel",
    "AdmittedTrialPlanInputRefsModel",
    "AdmittedTrialPlanProfilesModel",
    "BindingOrigin",
    "ExperimentScenarioFamilyReferenceModel",
    "SelectionPolicyKind",
]
