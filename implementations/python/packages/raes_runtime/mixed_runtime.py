"""Exact admitted component binding and runtime-owned phase activation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from uuid import uuid4

from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope
from raes_contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedMixedCompositionBindingModel,
    AdmittedTrialEntryModel,
    AdmittedTrialPlanModel,
    BackendManifestV2Model,
)
from raes_contracts.contracts.mixed_composition import (
    MixedCompositionComponentModel,
    MixedParticipantCompositionProfileModel,
)
from raes_contracts.contracts.mixed_composition_resolution import (
    MixedCompositionResolutionContext,
    validate_mixed_composition_context,
)
from raes_contracts.contracts.mixed_runtime import (
    MixedCompositionRuntimeEventModel,
    MixedCompositionRuntimeStateModel,
)
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
)

from .control_plane_execution import _utc_now
from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, mutation_entry
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .mixed_runtime_edge import MixedEdgeExecutionBinding
from .mixed_runtime_handoff import MixedHandoffBinding
from .registry import RuntimeTarget


@dataclass(frozen=True)
class MixedRuntimeComponent:
    """One configured effect sink joined to its exact admitted manifest."""

    target: RuntimeTarget
    manifest: BackendManifestV2Model
    envelope: BackendRealizationEnvelopeModel


@dataclass(frozen=True)
class MixedPhaseTransitionEvaluation:
    """Bounded, value-free result from one admitted transition evaluator."""

    permitted: bool
    attempts: int
    order_ref: str
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MixedRuntimeBinding:
    """Trusted immutable runtime input for one sealed trial entry."""

    plan: AdmittedTrialPlanModel
    plan_entry_id: str
    profile: MixedParticipantCompositionProfileModel
    context: MixedCompositionResolutionContext
    components: Mapping[str, MixedRuntimeComponent]
    transition_evaluators: Mapping[str, Callable[..., MixedPhaseTransitionEvaluation]] = field(default_factory=dict)
    edge_bindings: Mapping[str, MixedEdgeExecutionBinding] = field(default_factory=dict)
    handoff_bindings: Mapping[str, MixedHandoffBinding] = field(default_factory=dict)

    def __post_init__(self) -> None:
        plan = revalidate_admitted_trial_plan(self.plan)
        _require_admitted_profile(plan, self.plan_entry_id, self.profile)
        validate_mixed_composition_context(self.profile, self.context, require_trial_admission=True)
        _require_bound_components(self.profile, self.components)
        _require_transition_evaluators(self.profile, self.transition_evaluators)
        if set(self.edge_bindings) - set(self.profile.edges):
            raise ValueError("mixed runtime edge bindings must name admitted edges")
        if set(self.handoff_bindings) - set(self.profile.transitions):
            raise ValueError("mixed runtime handoff bindings must name admitted transitions")
        for transition_id, handoff in self.handoff_bindings.items():
            if not isinstance(handoff, MixedHandoffBinding):
                raise TypeError("executable handoff must be a typed installed binding")
            transition = self.profile.transitions[transition_id]
            source = self.profile.phases[transition.source_phase_id]
            target = self.profile.phases[transition.target_phase_id]
            departing = set(source.active_component_ids) - set(target.active_component_ids)
            arriving = set(target.active_component_ids) - set(source.active_component_ids)
            if (
                handoff.transition_id != transition_id
                or departing != {handoff.source_component_id}
                or arriving != {handoff.destination_component_id}
                or self.profile.components[handoff.source_component_id].native_ownership_ref != handoff.source_owner_ref
                or self.profile.components[handoff.destination_component_id].native_ownership_ref
                != handoff.destination_owner_ref
            ):
                raise ValueError("executable handoff differs from admitted transition ownership")
            time_model = self.context.time_models.get(handoff.time_model_ref)
            if (
                time_model is None
                or self.context.time_model_digests.get(handoff.time_model_ref) != handoff.time_model_digest
                or handoff.mapping_ref not in time_model.mappings
                or handoff.source_clock_address not in time_model.clocks
                or handoff.destination_clock_address not in time_model.clocks
            ):
                raise ValueError("executable handoff time binding is unresolved")
            mapping = time_model.mappings[handoff.mapping_ref]
            if (
                mapping.source_domain_address != time_model.clocks[handoff.source_clock_address].time_domain_address
                or mapping.target_domain_address
                != time_model.clocks[handoff.destination_clock_address].time_domain_address
            ):
                raise ValueError("executable handoff clock mapping differs from admission")
        for edge_id, installed in self.edge_bindings.items():
            if not isinstance(installed, MixedEdgeExecutionBinding):
                raise TypeError("executable edge binding must be a typed installed binding")
            edge = self.profile.edges[edge_id]
            if (
                installed.edge_id != edge_id
                or installed.bridge_ref != edge.routing_ref
                or installed.mapping_ref != edge.time_binding.mapping_address
                or installed.mapping_loss_ref != edge.mapping_loss.limitation_ref
            ):
                raise ValueError("executable edge binding differs from admitted edge")
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))
        object.__setattr__(self, "transition_evaluators", MappingProxyType(dict(self.transition_evaluators)))
        object.__setattr__(self, "edge_bindings", MappingProxyType(dict(self.edge_bindings)))
        object.__setattr__(self, "handoff_bindings", MappingProxyType(dict(self.handoff_bindings)))

    @property
    def entry(self) -> AdmittedTrialEntryModel:
        return self.plan.entries[self.plan_entry_id]


def _require_admitted_profile(
    plan: AdmittedTrialPlanModel,
    plan_entry_id: str,
    profile: MixedParticipantCompositionProfileModel,
) -> None:
    entry = plan.entries.get(plan_entry_id)
    if entry is None or not isinstance(entry.apparatus, AdmittedMixedCompositionBindingModel):
        raise ValueError("mixed runtime requires an exact admitted mixed entry")
    reference = entry.apparatus.profile_ref
    admitted_identity = (reference.ref_id, reference.ref_version, reference.ref_digest)
    configured_identity = (profile.profile_id, profile.profile_revision, profile.profile_digest)
    if admitted_identity != configured_identity:
        raise ValueError("mixed runtime profile does not match the admitted entry")


def _require_bound_components(
    profile: MixedParticipantCompositionProfileModel,
    components: Mapping[str, MixedRuntimeComponent],
) -> None:
    if set(components) != set(profile.components):
        raise ValueError("mixed runtime components must exactly match the admitted profile")
    for component_id, declaration in profile.components.items():
        _require_bound_component(components[component_id], declaration)


def _require_bound_component(bound: MixedRuntimeComponent, declaration: MixedCompositionComponentModel) -> None:
    if not isinstance(bound, MixedRuntimeComponent):
        raise TypeError("mixed runtime components must be typed exact bindings")
    manifest_ref = declaration.manifest_ref
    admitted_manifest = (
        manifest_ref.subject_ref.ref_id,
        manifest_ref.subject_ref.ref_version,
        manifest_ref.ref_digest,
        declaration.realization_envelope,
    )
    configured_manifest = (
        bound.manifest.identity.name,
        bound.manifest.identity.version,
        canonical_json_digest(bound.manifest.model_dump(mode="json")),
        bound.envelope.identity,
    )
    if configured_manifest != admitted_manifest:
        raise ValueError("mixed runtime component manifest or envelope differs from admission")
    expected_manifest = backend_manifest_from_v2_model_with_envelope(bound.manifest, bound.envelope)
    if bound.target.manifest != expected_manifest:
        raise ValueError("mixed runtime target manifest differs from the admitted component")


def _require_transition_evaluators(
    profile: MixedParticipantCompositionProfileModel,
    evaluators: Mapping[str, Callable[..., MixedPhaseTransitionEvaluation]],
) -> None:
    required = {transition.evaluator_ref for transition in profile.transitions.values()}
    if set(evaluators) != required or any(not callable(evaluator) for evaluator in evaluators.values()):
        raise ValueError("mixed runtime must bind every admitted transition evaluator exactly")


def _activation_binding(control_plane: object, identity: object) -> MixedRuntimeBinding:
    if not isinstance(identity, ControlPlaneIdentity):
        raise PermissionError("mixed runtime activation requires an authenticated identity")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        raise PermissionError("mixed runtime identity is not authorized for this target")
    binding = control_plane._mixed_runtime
    if binding is None:
        raise ValueError("mixed runtime is not configured")
    return binding


def _activation_operation(
    control_plane: object,
    binding: MixedRuntimeBinding,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
) -> tuple[OperationReceipt, ControlPlaneOperationRecord]:
    context = operation_admission_context(
        control_plane,
        kind=OperationKind.COMPOSITION_PHASE,
        request={
            "action": "activate",
            "plan_digest": binding.plan.plan_digest,
            "entry_digest": binding.entry.entry_digest,
            "profile_digest": binding.profile.profile_digest,
        },
        identity=identity,
    )
    operation_id = str(uuid4())
    timestamp = _utc_now()
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=timestamp,
        accepted=True,
        context=context,
    )
    running = ControlPlaneOperationRecord(
        receipt=receipt,
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=timestamp,
            updated_at=timestamp,
            context=context,
        ),
        idempotency_key=idempotency_key,
        request_fingerprint=context.request_commitment,
    )
    return receipt, running


_RUNTIME_STATE_FIELDS = {
    "run_id",
    "plan_id",
    "plan_entry_id",
    "profile_id",
    "profile_digest",
    "phase_id",
    "phase_revision",
    "active_component_ids",
    "active_allocation_ids",
    "active_edge_ids",
}


def _initial_composition(
    binding: MixedRuntimeBinding,
    operation_id: str,
) -> tuple[MixedCompositionRuntimeEventModel, MixedCompositionRuntimeStateModel]:
    phase = binding.profile.phases[binding.profile.initial_phase_id]
    event = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:initial",
        event_kind="phase-activated",
        run_id=binding.entry.run_id,
        plan_id=binding.plan.plan_id,
        plan_entry_id=binding.entry.plan_entry_id,
        profile_id=binding.profile.profile_id,
        profile_digest=binding.profile.profile_digest,
        phase_id=phase.phase_id,
        phase_revision=0,
        active_component_ids=phase.active_component_ids,
        active_allocation_ids=phase.active_allocation_ids,
        active_edge_ids=phase.active_edge_ids,
        disposition="committed",
        order_ref="order:admitted-initial-phase",
        evidence_refs=[item.evidence_ref for item in phase.evidence_bindings],
    )
    state = MixedCompositionRuntimeStateModel(
        **event.model_dump(mode="python", include=_RUNTIME_STATE_FIELDS),
        history_head=event.event_id,
    )
    return event, state


def _commit_activation(
    control_plane: object,
    binding: MixedRuntimeBinding,
    running: ControlPlaneOperationRecord,
    event: MixedCompositionRuntimeEventModel,
    state: MixedCompositionRuntimeStateModel,
) -> None:
    snapshot = control_plane._snapshot.with_entries(
        dict(control_plane._snapshot.entries),
        mixed_composition_states={
            **control_plane._snapshot.mixed_composition_states,
            binding.entry.run_id: state.model_dump(mode="json"),
        },
        mixed_composition_history={
            **control_plane._snapshot.mixed_composition_history,
            binding.entry.run_id: [event.model_dump(mode="json")],
        },
    )
    terminal = replace(
        running,
        status=replace(running.status, state=OperationState.SUCCEEDED, updated_at=_utc_now()),
    )
    context = running.status.context
    audit = AuditEvent(
        timestamp=terminal.status.updated_at,
        action="activate_mixed_composition",
        identity=context.actor_id,
        allowed=True,
        target=context.target_scope,
        operation_id=running.receipt.operation_id,
        reason="committed",
    )
    control_plane._commit_participant_transition(
        expected_history_heads={f"mixed_composition_history:{binding.entry.run_id}": None},
        snapshot=snapshot,
        record=terminal,
        audit_event=audit,
    )


class MixedRuntimeMixin:
    """Own phase facts in the incumbent control-plane store."""

    _composition_operation_kind = OperationKind.COMPOSITION_PHASE

    @runtime_owned
    @mutation_entry(OperationKind.COMPOSITION_PHASE)
    def activate_mixed_composition(
        self,
        *,
        identity: object,
        idempotency_key: str,
    ) -> OperationReceipt:
        binding = _activation_binding(self, identity)
        with control_plane_mutation(self, OperationKind.COMPOSITION_PHASE):
            self._reload_derived_state()
            already_active = binding.entry.run_id in self._snapshot.mixed_composition_states
            receipt, running = _activation_operation(self, binding, identity, idempotency_key)
            claimed = self._claim_record(
                running,
                new_claim_blocked="current-state" if already_active else None,
            )
            if claimed.receipt.operation_id != receipt.operation_id:
                return claimed.receipt
            event, state = _initial_composition(binding, receipt.operation_id)
            _commit_activation(self, binding, running, event, state)
            return receipt

    @runtime_owned
    @mutation_entry(OperationKind.COMPOSITION_PHASE)
    def advance_mixed_composition(
        self,
        transition_id: str,
        *,
        identity: object,
        idempotency_key: str,
    ) -> OperationReceipt:
        from .mixed_runtime_phase import advance_mixed_composition

        with control_plane_mutation(self, OperationKind.COMPOSITION_PHASE):
            return advance_mixed_composition(
                self,
                transition_id=transition_id,
                identity=identity,
                idempotency_key=idempotency_key,
            )
