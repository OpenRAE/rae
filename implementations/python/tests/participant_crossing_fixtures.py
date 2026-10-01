"""Shared deterministic fixtures for participant-crossing tests.

RUN-319 enforcement tests and ASR-535 assurance/conformance probes drive the
same runtime boundary, so the target, identity, behavior, evidence, and
policy-resolver builders live here once instead of being re-derived per suite.
Every value is safe synthetic test data: no credential, policy body, hidden
world state, or participant payload.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from raes.participant_behavior_specification import MixedControlTransitionKind
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.capabilities import (
    PARTICIPANT_RUNTIME_POLICY_FEATURES,
    ParticipantFeatureSupport,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingGateDisposition,
    ParticipantCrossingOperation,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_operations.deterministic_participant_fixtures import (
    build_implementation_manifest,
    build_implementation_selection,
)
from raes_processor.models import (
    MixedControlControllerStateRuntime,
    MixedControlDispositionRulesRuntime,
    MixedControlTransitionRuntime,
    ParticipantBehaviorRuntime,
    ParticipantBehaviorSpecificationRuntime,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ParticipantAudienceSubjectBinding,
    ParticipantControlSubjectBinding,
)
from raes_runtime.participant_crossing_boundary import _action_subject
from raes_runtime.participant_crossing_egress import _view_subject
from raes_runtime.participant_crossing_mediation import (
    ParticipantCrossingEvidence,
    ParticipantCrossingIntent,
    ParticipantCrossingPolicyResolution,
    ParticipantCrossingSemanticGates,
    ParticipantCrossingTransformationResolution,
    ParticipantCrossingValidationContext,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

PARTICIPANT = "participant.behavior.red-agent"
CONTROLLER = "participant.behavior.supervisor"
AUDIENCE = "audience:red-operator"
ACTION = "participant.action-contract.contain-host"
TRANSFORMED_ACTION = "participant.action-contract.redacted-contain-host"
OBSERVATION = "participant.observation-boundary.red-view"


def crossing_request() -> dict[str, object]:
    """Load the published API-423 valid crossing-occurrence request fixture."""

    fixture = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "participant-crossing-occurrence-v1"
        / "valid"
        / "request.json"
    )
    return json.loads(fixture.read_text(encoding="utf-8"))


def evidence() -> ParticipantCrossingEvidence:
    return ParticipantCrossingEvidence(
        audience_scope_ref=AUDIENCE,
        required_evidence_refs=["evidence-requirement:crossing-decision"],
        provenance_refs=["provenance:crossing-1"],
        evidence_refs=["evidence:crossing-1"],
        object_marking_refs=["marking:participant-control"],
        authorization_scope="scope:red-team",
        loss_and_limitations=["limitation:bounded-reference-runtime"],
    )


def identity(
    *,
    bound: bool = True,
    audience_bound: bool = False,
    participant_address: str = PARTICIPANT,
    audience_scope_ref: str = AUDIENCE,
) -> ControlPlaneIdentity:
    return ControlPlaneIdentity(
        identity="operator.red",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
        participant_control_subjects=(
            (
                ParticipantControlSubjectBinding(
                    participant_address=participant_address,
                    controller_ref=CONTROLLER,
                ),
            )
            if bound
            else ()
        ),
        participant_audience_subjects=(
            (
                ParticipantAudienceSubjectBinding(
                    participant_address=participant_address,
                    audience_scope_ref=audience_scope_ref,
                ),
            )
            if audience_bound
            else ()
        ),
    )


def behavior() -> ParticipantBehaviorRuntime:
    return ParticipantBehaviorRuntime(
        address=PARTICIPANT,
        name="red-agent",
        spec={},
        authority_anchor_refs=("red-team",),
        authority_anchor_addresses=("authority:red-team",),
        action_contract_addresses=(ACTION, TRANSFORMED_ACTION),
        observation_boundary_addresses=(OBSERVATION,),
    )


def admission_request(
    *,
    action_contract_address: str = ACTION,
    action_instance_id: str = "action-1",
) -> ParticipantActionAdmissionRequest:
    return ParticipantActionAdmissionRequest(
        participant_address=PARTICIPANT,
        action_contract_address=action_contract_address,
        observation_boundary_address=OBSERVATION,
        action_instance_id=action_instance_id,
        implementation_manifest=build_implementation_manifest(),
        implementation_selection=build_implementation_selection(PARTICIPANT),
        evidence_refs=("evidence:action",),
        observation_boundary_evidence_refs=("evidence:action",),
    )


def policy_capable_target(
    *features: str,
    support_level: ParticipantFeatureSupportLevel = ParticipantFeatureSupportLevel.EXACT,
):
    """Return a stub target declaring ``features`` at ``support_level``."""

    selected_features = set(features or ("participant_ingress_admission",))
    target = create_stub_target()
    manifest = target.manifest
    capabilities = manifest.participant_runtime
    assert capabilities is not None
    feature_support = tuple(
        (
            ParticipantFeatureSupport(
                feature=entry.feature,
                support_level=support_level,
                constraint_refs=(
                    (f"constraint:{entry.feature}:bounded",)
                    if support_level is ParticipantFeatureSupportLevel.BOUNDED
                    else ()
                ),
                limitation_refs=(
                    (f"limitation:{entry.feature}:bounded",)
                    if support_level is not ParticipantFeatureSupportLevel.EXACT
                    else ()
                ),
                disclosure_refs=(
                    (f"disclosure:{entry.feature}:bounded",)
                    if support_level is not ParticipantFeatureSupportLevel.EXACT
                    else ()
                ),
                evidence_refs=(f"evidence:backend:{entry.feature}",),
            )
            if entry.feature in selected_features
            else entry
        )
        for entry in capabilities.feature_support
    )
    participant_runtime = replace(
        capabilities,
        supported_behavior_features=(capabilities.supported_behavior_features | selected_features),
        feature_support=feature_support,
    )
    updated_manifest = BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=manifest.supported_contract_versions,
        compatibility=manifest.compatibility,
        realization_support=manifest.realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=replace(manifest.capabilities, participant_runtime=participant_runtime),
        realization_envelope=manifest.realization_envelope,
    )
    return replace(target, manifest=updated_manifest)


class StaticCrossingResolver:
    """Deterministic exact-cut policy resolver with per-gate overrides."""

    def __init__(
        self,
        *,
        gate_overrides: dict[str, ParticipantCrossingGateDisposition] | None = None,
        allowed_downgrades: dict[str, ParticipantFeatureSupportLevel] | None = None,
    ) -> None:
        self.gate_overrides = gate_overrides or {}
        self.allowed_downgrades = allowed_downgrades or {}
        self.seen_intents: list[ParticipantCrossingIntent] = []
        self.subjects: list[ParticipantCrossingSubjectReferenceModel] = []
        self.evidence_refs: set[str] = set()
        self.authority_refs: set[str] = {
            "authority:red-team",
            "entities.red-team",
            "runtime.authority:participant-projection",
        }
        fixture_policy = ParticipantCrossingPolicyReferenceModel.model_validate(
            crossing_request()["occurrence"]["policy"]
        )
        self.policy = fixture_policy.model_copy(
            update={
                "effective_order": 0,
                "valid_from_order": 0,
                "valid_until_order": 1000,
            }
        )

    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantCrossingPolicyResolution:
        del snapshot
        self._remember(intent)
        defaults = {
            "participant_authority": ParticipantCrossingGateDisposition.PERMIT,
            "action_admission": (
                ParticipantCrossingGateDisposition.PERMIT
                if intent.direction.value == "ingress"
                else ParticipantCrossingGateDisposition.NOT_APPLICABLE
            ),
            "visibility": (
                ParticipantCrossingGateDisposition.PERMIT
                if intent.direction.value == "egress"
                else ParticipantCrossingGateDisposition.NOT_APPLICABLE
            ),
            "marking_authorization": ParticipantCrossingGateDisposition.PERMIT,
            "declassification": ParticipantCrossingGateDisposition.NOT_APPLICABLE,
            "transformation_validity": ParticipantCrossingGateDisposition.NOT_APPLICABLE,
        }
        if intent.requested_operation in {
            ParticipantCrossingOperation.PROJECTION,
            ParticipantCrossingOperation.MASKING,
            ParticipantCrossingOperation.REDACTION,
            ParticipantCrossingOperation.TRANSFORMATION,
            ParticipantCrossingOperation.DECLASSIFICATION,
        }:
            defaults["transformation_validity"] = ParticipantCrossingGateDisposition.PERMIT
        defaults.update(self.gate_overrides)
        return ParticipantCrossingPolicyResolution(
            policy=self.policy,
            gates=ParticipantCrossingSemanticGates(**defaults),
            reason_code="policy-satisfied",
            allowed_downgrades=self.allowed_downgrades,
            downgrade_policy_ref=("policy:downgrade:authorized" if self.allowed_downgrades else None),
            downgrade_provenance_ref=("provenance:downgrade:authorized" if self.allowed_downgrades else None),
        )

    def _remember(self, intent: ParticipantCrossingIntent) -> None:
        self.seen_intents.append(intent)
        if intent.subject not in self.subjects:
            self.subjects.append(intent.subject)
        self.evidence_refs.update(intent.evidence_refs)
        self.evidence_refs.update(intent.required_evidence_refs)
        self.authority_refs.update(intent.authority_basis_refs)

    def validation_context(
        self,
        snapshot: RuntimeSnapshot,
        participant_address: str,
    ) -> ParticipantCrossingValidationContext:
        del snapshot, participant_address
        return ParticipantCrossingValidationContext(
            known_subjects=tuple(self.subjects),
            policies=(self.policy,),
            known_evidence_refs=frozenset(
                {
                    *self.evidence_refs,
                    # Every governed API-407 policy feature, so a case that
                    # exercises one is not failed for a fixture gap.
                    *(f"evidence:backend:{feature}" for feature in PARTICIPANT_RUNTIME_POLICY_FEATURES),
                }
            ),
            known_authority_basis_refs=frozenset(self.authority_refs),
        )


class TransformedActionResolver(StaticCrossingResolver):
    def __init__(self, *, deny_fresh: bool = False) -> None:
        super().__init__()
        self.deny_fresh = deny_fresh
        self.governed_request: ParticipantActionAdmissionRequest | None = None

    def resolve_operation(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
        carrier: object,
    ) -> ParticipantCrossingPolicyResolution:
        assert isinstance(carrier, ParticipantActionAdmissionRequest)
        self._remember(intent)
        self.governed_request = replace(
            carrier,
            action_contract_address=TRANSFORMED_ACTION,
            action_instance_id=f"{carrier.action_instance_id}-redacted",
        )
        result_subject = _action_subject(SimpleNamespace(_snapshot=snapshot), self.governed_request)
        if result_subject not in self.subjects:
            self.subjects.append(result_subject)
        base = super().resolve(intent, snapshot)
        return replace(
            base,
            gates=replace(
                base.gates,
                transformation_validity=ParticipantCrossingGateDisposition.PERMIT,
            ),
            required_operation=ParticipantCrossingOperation.REDACTION,
            transformation=ParticipantCrossingTransformationResolution(
                result_subject=result_subject,
                rule_ref="rule:redact-action",
                rule_revision="1",
                result_marking_refs=("marking:participant-control",),
            ),
        )

    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantCrossingPolicyResolution:
        resolution = super().resolve(intent, snapshot)
        if self.governed_request is not None and intent.subject.subject_ref.endswith(
            self.governed_request.action_instance_id
        ):
            if self.deny_fresh:
                return replace(
                    resolution,
                    gates=replace(
                        resolution.gates,
                        action_admission=ParticipantCrossingGateDisposition.DENY,
                    ),
                )
        return resolution

    def transform_ingress(
        self,
        intent: ParticipantCrossingIntent,
        governed_subject: ParticipantCrossingSubjectReferenceModel,
        carrier: object,
    ) -> ParticipantActionAdmissionRequest:
        del intent, governed_subject, carrier
        assert self.governed_request is not None
        return self.governed_request


class TransformedEgressResolver(StaticCrossingResolver):
    def __init__(self) -> None:
        super().__init__()
        self.governed_view: object | None = None

    def resolve_operation(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
        carrier: object,
    ) -> ParticipantCrossingPolicyResolution:
        self._remember(intent)
        self.governed_view = carrier.model_copy(
            update={
                "view_id": f"{carrier.view_id}.redacted",
                "redaction_policy_ref": "policy:redacted-status",
                "marking_definition_refs": ["marking:participant-control", "marking:redacted"],
            }
        )
        result_subject = _view_subject(
            self.governed_view,
            participant_address=intent.participant_address,
            episode_id=intent.episode_id,
            subject_kind=intent.subject.subject_kind,
        )
        if result_subject not in self.subjects:
            self.subjects.append(result_subject)
        base = super().resolve(intent, snapshot)
        return replace(
            base,
            gates=replace(
                base.gates,
                transformation_validity=ParticipantCrossingGateDisposition.PERMIT,
            ),
            required_operation=ParticipantCrossingOperation.REDACTION,
            transformation=ParticipantCrossingTransformationResolution(
                result_subject=result_subject,
                rule_ref="rule:redact-status",
                rule_revision="1",
                result_marking_refs=("marking:participant-control", "marking:redacted"),
            ),
        )

    def transform_egress(
        self,
        intent: ParticipantCrossingIntent,
        governed_subject: ParticipantCrossingSubjectReferenceModel,
        carrier: object,
    ) -> object:
        del intent, governed_subject, carrier
        return self.governed_view


def control_specification() -> ParticipantBehaviorSpecificationRuntime:
    autonomous = MixedControlControllerStateRuntime(
        address="participant.behavior-specification.controlled.controller-state.autonomous",
        name="autonomous",
        spec={},
        state_id="autonomous",
        controller_ref="supervisor",
        controller_address=CONTROLLER,
        authority_basis_refs=("red-team",),
        authority_basis_addresses=("entities.red-team",),
        scope_refs=("web",),
        scope_addresses=("nodes.web",),
        policy_revision="1.0.0",
        valid_from_order=0,
        valid_until_order=20,
        authority_status="active",
        evidence_refs=("authority-evidence",),
        evidence_addresses=("evidence.authority",),
    )
    supervised = replace(
        autonomous,
        address="participant.behavior-specification.controlled.controller-state.supervised",
        name="supervised",
        state_id="supervised",
    )
    transition = MixedControlTransitionRuntime(
        address="participant.behavior-specification.controlled.control-transition.handoff",
        name="handoff",
        spec={},
        transition_id="handoff",
        transition_kind=MixedControlTransitionKind.HANDOFF.value,
        from_state_address=autonomous.address,
        to_state_address=supervised.address,
        policy_revision="1.0.0",
        expected_state_revision=0,
        resulting_state_revision=1,
        effective_order=1,
        valid_from_order=0,
        valid_until_order=20,
        completion_evidence_refs=("handoff-evidence",),
        completion_evidence_addresses=("evidence.handoff",),
    )
    return ParticipantBehaviorSpecificationRuntime(
        address="participant.behavior-specification.controlled",
        name="controlled",
        spec={},
        spec_name="controlled",
        participant_addresses=(PARTICIPANT,),
        behavior_mode="mixed-control",
        mixed_control_participant_address=PARTICIPANT,
        mixed_control_policy_revision="1.0.0",
        mixed_control_order_strategy="total-effective-order",
        mixed_control_initial_state_address=autonomous.address,
        mixed_control_dispositions=MixedControlDispositionRulesRuntime(
            duplicate="idempotent",
            stale="reject",
            revoked="reject",
            late="reject",
            concurrent="reject",
            conflict="reject",
        ),
        controller_states=(autonomous, supervised),
        control_transitions=(transition,),
    )


def action_plane(
    resolver: StaticCrossingResolver,
    *,
    target: object | None = None,
    store: object | None = None,
    enforce_final_sink_flow_control: bool = False,
    participant_control: object | None = None,
) -> RuntimeControlPlane:
    # Legacy API-423-only fixtures pass a resolver without the SEM-233 final-sink
    # hook, so enforcement is opted out here by default. Tests exercising SEM-233
    # final-sink enforcement pass a hook-capable resolver (enforcement runs
    # regardless of this flag once the hook is present).
    plane = RuntimeControlPlane(
        target or policy_capable_target(),
        crossing_policy_resolver=resolver,
        store=store,
        enforce_final_sink_flow_control=enforce_final_sink_flow_control,
        participant_control=participant_control,
    )
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    return plane


def admit(
    plane: RuntimeControlPlane,
    *,
    request: ParticipantActionAdmissionRequest | None = None,
    idempotency_key: str = "crossing-action",
    control_identity: ControlPlaneIdentity | None = None,
):
    return plane.admit_participant_action(
        behavior(),
        request or admission_request(),
        identity=control_identity or identity(),
        crossing_evidence=evidence(),
        idempotency_key=idempotency_key,
    )
