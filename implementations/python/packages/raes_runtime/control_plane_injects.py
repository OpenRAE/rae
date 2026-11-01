"""Shared runtime admission and actor-scoped occurrence readback."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from raes_backend_protocols.inject_execution import InjectAdmission
from raes_backend_protocols.operation_supervision import require_inject_occurrence_provider
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    InjectOccurrenceCorrelationModel,
    InjectOccurrenceModel,
    InjectOccurrenceOutcomeModel,
    InjectTriggerRequestModel,
    ParticipantInjectApplicationModel,
    ParticipantInjectContentModel,
    ParticipantInjectDeliveryReceiptModel,
    inject_occurrence_correlation,
    require_inject_trigger_retry,
)
from raes_contracts.contracts.participant_delivery_invocation import ParticipantDeliveryInvocationRequestModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import AuthorizationError, ConflictError, InvalidInputError, NotFoundError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeDomain,
)

from .control_plane_execution import OperationExecutionRequest, execute_operation
from .control_plane_lifecycle import runtime_owned, store_authoritative_state
from .control_plane_mutation import control_plane_mutation, mutation_entry
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_store import ControlPlaneOperationRecord, TerminalCommitMode, terminal_operation_audit
from .inject_capture import InjectCaptureResult
from .inject_execution import require_inject_plan
from .participant_control_orchestration import admit_ingress_sinks
from .participant_control_runtime import ParticipantControlLiveCut
from .participant_crossing_action import combined_crossing_audit
from .participant_crossing_commit import commit_prepared_crossing
from .participant_crossing_intents import action_crossing_intent, action_subject
from .participant_crossing_mediation import prepare_participant_crossing
from .participant_crossing_state_cut import expected_participant_history_heads
from .participant_crossing_transform import governed_action_request, require_governed_subject
from .participant_delivery_invocation import invoke_delivery
from .participant_delivery_tools import ParticipantDeliveryInvocationTools
from .participant_execution_control import InvocationToolActionLedger
from .participant_flow_sink import ParticipantFlowSinkKind
from .participant_inject_application import authorized_delivery_binding
from .participant_inject_control import require_delivery_control
from .participant_result_contracts import participant_runtime_state_contract_diagnostics

_LOGGER = get_logger(__name__)


def _authorize_trigger(plane: object, identity: object | None) -> None:
    if identity is None:
        # P0/P1 trusted embedder boundary.
        return
    if (
        not isinstance(identity, ControlPlaneIdentity)
        or identity.target_name != plane._target.name
        or not identity.roles.intersection({ControlPlaneRole.OPERATOR, ControlPlaneRole.BACKEND})
    ):
        raise AuthorizationError("inject mutation authority is unavailable")


def _inject_diagnostic() -> Diagnostic:
    return Diagnostic(
        code="runtime.inject.admission-refused",
        domain="runtime",
        address="runtime.control-plane.inject",
        message="The authored inject, target, admission or execution contract could not be admitted.",
    )


class RuntimeInjectMixin:
    def delivery_create_tool_ledger(self, parent):
        self._require_state_writer()
        return InvocationToolActionLedger(
            store=self._store,
            parent_operation_id=parent.receipt.operation_id,
            parent_context=parent.receipt.context,
            engine_admission=self._tool_engine_admission,
            wall_clock=self.wall_clock,
        )

    def delivery_commit_invocation_terminal(self, record):
        return self._commit_terminal_operation(self._snapshot, record, mode=TerminalCommitMode.OPERATION_ONLY)

    def delivery_live_cut(self, raw):
        if not isinstance(raw, ParticipantControlLiveCut):
            raise ConflictError("tool action live cut is unavailable")
        return ParticipantControlLiveCut.model_validate(raw.model_dump(mode="json"))

    @property
    def delivery_action_sink_kind(self):
        return ParticipantFlowSinkKind.ACTION_ARGUMENT

    def delivery_authorized_delivery_binding(self, *args, **kwargs):
        self._require_state_writer()
        return authorized_delivery_binding(self, *args, **kwargs)

    def delivery_operation_admission_context(self, *args, **kwargs):
        self._require_state_writer()
        return operation_admission_context(self, *args, **kwargs)

    def delivery_prepare_participant_crossing(self, *args, **kwargs):
        self._require_state_writer()
        return prepare_participant_crossing(self, *args, **kwargs)

    def delivery_action_crossing_intent(self, *args, **kwargs):
        self._require_state_writer()
        return action_crossing_intent(self, *args, **kwargs)

    def delivery_action_subject(self, *args, **kwargs):
        self._require_state_writer()
        return action_subject(self, *args, **kwargs)

    def delivery_admit_ingress_sinks(self, *args, **kwargs):
        self._require_state_writer()
        return admit_ingress_sinks(self, *args, **kwargs)

    def delivery_require_delivery_control(self, *args, **kwargs):
        self._require_state_writer()
        return require_delivery_control(self, *args, **kwargs)

    def delivery_governed_action_request(self, *args, **kwargs):
        self._require_state_writer()
        return governed_action_request(self, *args, **kwargs)

    def delivery_require_governed_subject(self, *args, **kwargs):
        self._require_state_writer()
        return require_governed_subject(*args, **kwargs)

    def delivery_combined_crossing_audit(self, *args, **kwargs):
        self._require_state_writer()
        return combined_crossing_audit(*args, **kwargs)

    def delivery_commit_prepared_crossing(self, *args, **kwargs):
        self._require_state_writer()
        return commit_prepared_crossing(self, *args, **kwargs)

    def delivery_expected_participant_history_heads(self, *args, **kwargs):
        self._require_state_writer()
        return expected_participant_history_heads(*args, **kwargs)

    def delivery_participant_runtime_state_contract_diagnostics(self, *args, **kwargs):
        self._require_state_writer()
        return participant_runtime_state_contract_diagnostics(*args, **kwargs)

    def delivery_terminal_operation_audit(self, *args, **kwargs):
        self._require_state_writer()
        return terminal_operation_audit(*args, **kwargs)

    def delivery_invocation_record(self, operation_id, now, context, key, invocation):
        self._require_state_writer()
        return ControlPlaneOperationRecord(
            receipt=OperationReceipt(
                operation_id=operation_id,
                domain=RuntimeDomain.PARTICIPANT,
                submitted_at=now,
                accepted=True,
                context=context,
            ),
            status=OperationStatus(
                operation_id=operation_id,
                domain=RuntimeDomain.PARTICIPANT,
                state=OperationState.RUNNING,
                submitted_at=now,
                updated_at=now,
                context=context,
            ),
            request_fingerprint=context.request_commitment,
            idempotency_key=key,
            result_payload={
                "kind": "participant-delivery-invocation/v1",
                "binding": invocation.model_dump(mode="json"),
            },
        )

    @runtime_owned
    @mutation_entry(OperationKind.COMPOSITION_PHASE)
    def invoke_participant_delivery(
        self,
        request: ParticipantDeliveryInvocationRequestModel,
        *,
        identity: ControlPlaneIdentity | None,
    ) -> OperationReceipt:
        if not isinstance(request, ParticipantDeliveryInvocationRequestModel):
            raise TypeError("delivery invocation requires a typed request")
        request = ParticipantDeliveryInvocationRequestModel.model_validate(request.model_dump(mode="json"))
        with control_plane_mutation(self, OperationKind.COMPOSITION_PHASE):
            self._reload_derived_state()
            return invoke_delivery(self, request, identity)

    def delivery_claim_record(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        self._require_state_writer()
        return self._claim_record(*args, **kwargs)

    def delivery_commit_participant_transition(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        self._require_state_writer()
        return self._commit_participant_transition(*args, **kwargs)

    def delivery_commit_terminal_operation(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        self._require_state_writer()
        return self._commit_terminal_operation(*args, **kwargs)

    @property
    def delivery_execution_adapter(self):
        """Read current state for runtime-owned delivery composition."""
        return self._execution_adapter

    @property
    def delivery_execution_generation(self):
        """Read current state for runtime-owned delivery composition."""
        return self._execution_generation

    @property
    def delivery_inject_delivery(self):
        """Read current state for runtime-owned delivery composition."""
        return self._inject_delivery

    @property
    def delivery_mutation_authority(self):
        """Read current state for runtime-owned delivery composition."""
        self._require_state_writer()
        return self._mutation_authority

    def delivery_operation_read_allowed(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        return self._operation_read_allowed(*args, **kwargs)

    @property
    def delivery_operations(self):
        """Read current state for runtime-owned delivery composition."""
        self._require_state_writer()
        return self._operations

    def delivery_reload_derived_state(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        self._require_state_writer()
        return self._reload_derived_state(*args, **kwargs)

    def delivery_require_state_writer(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        self._require_state_writer()
        return self._require_state_writer(*args, **kwargs)

    @property
    def delivery_snapshot(self):
        """Read current state for runtime-owned delivery composition."""
        return self._snapshot

    @property
    def delivery_snapshot_state(self):
        """Read current state for runtime-owned delivery composition."""
        return self._snapshot_state

    @property
    def delivery_store(self):
        """Read current state for runtime-owned delivery composition."""
        self._require_state_writer()
        return self._store

    @property
    def delivery_supervision(self):
        """Read current state for runtime-owned delivery composition."""
        return self._supervision

    @property
    def delivery_target(self):
        """Read current state for runtime-owned delivery composition."""
        return self._target

    def delivery_tool_engine_admission(self, *args, **kwargs):
        """Guarded runtime-owned delivery collaborator operation."""
        self._require_state_writer()
        return self._tool_engine_admission(*args, **kwargs)

    @property
    def delivery_tool_port_type(self):
        return ParticipantDeliveryInvocationTools

    @runtime_owned
    @mutation_entry(OperationKind.PARTICIPANT_CROSSING)
    def deliver_participant_inject(
        self, application: ParticipantInjectApplicationModel, *, identity: object | None = None
    ) -> ParticipantInjectDeliveryReceiptModel:
        from .participant_inject_application import deliver_participant_inject

        return deliver_participant_inject(self, application, identity=identity)

    @runtime_owned
    @mutation_entry(OperationKind.ORCHESTRATION)
    @store_authoritative_state
    def submit_inject(self, request: InjectTriggerRequestModel, *, identity: object | None = None) -> OperationReceipt:
        self._assert_runtime_owner()
        _authorize_trigger(self, identity)
        if not isinstance(request, InjectTriggerRequestModel):
            raise TypeError("inject trigger requires a typed request")
        request = InjectTriggerRequestModel.model_validate(request.model_dump(mode="json"))
        with control_plane_mutation(self, OperationKind.ORCHESTRATION):
            return self._submit_inject(request, identity=identity)

    def _submit_inject(
        self, request: InjectTriggerRequestModel, *, identity: ControlPlaneIdentity | None
    ) -> OperationReceipt:
        context = operation_admission_context(
            self, kind=OperationKind.ORCHESTRATION, request=request, identity=identity
        )
        if (request.target_scope, request.run_scope) != (self._target_scope, self._run_scope):
            raise ConflictError("inject target/run scope mismatch")
        incumbent = self._store.find_by_idempotency(request.request_key, context=context)
        if incumbent is not None:
            if not self._operation_read_allowed(incumbent, identity) or incumbent.inject_occurrence is None:
                raise ConflictError("inject retry conflicts with the original request")
            try:
                require_inject_trigger_retry(incumbent.inject_occurrence, request, actor_id=context.actor_id)
            except ValueError as exc:
                raise ConflictError("inject retry conflicts with the original request") from exc
            return incumbent.receipt
        try:
            admission = self._admit_inject(request, context)
        except Exception as exc:
            admission = None
            if not isinstance(exc, RaesError):
                # Isolation of the inject resolver: a failure refuses the inject like any admission refusal.
                _LOGGER.exception(
                    "inject admission failed in the inject resolver or its contract checks",
                    exc_info=foreign_failure_record(exc),
                )
        if admission is None:
            # Refused after the handler, so a refusal audit failure carries no resolver exception as its context.
            return self._reject_diagnostics(
                domain=RuntimeDomain.ORCHESTRATION, context=context, diagnostics=[_inject_diagnostic()]
            )
        occurrence = admission.occurrence
        execution = OperationExecutionRequest(
            domain=RuntimeDomain.ORCHESTRATION,
            method=self._target.orchestrator.start,
            plan=admission.plan,
            address="runtime.control-plane.inject",
            diagnostics=[],
            base_snapshot=None,
            idempotency_key=request.request_key,
            request_fingerprint=context.request_commitment,
            context=context,
            inject_occurrence=occurrence,
            admission_diagnostics=lambda: self._inject_live_diagnostics(occurrence),
        )
        return execute_operation(self, execution)

    def _admit_inject(self, request: InjectTriggerRequestModel, context: OperationAdmissionContext) -> InjectAdmission:
        if (
            self._inject_execution is None
            or self._distributed_execution is not None
            or self._target.orchestrator is None
        ):
            raise ConflictError("inject execution is unavailable in this composition")
        try:
            require_inject_occurrence_provider(
                self._target.operation_provider, self._target.manifest.supported_contract_versions
            )
        except ValueError as exc:
            raise ConflictError("inject execution is unavailable in this composition") from exc
        operation_id, revision = str(uuid4()), self._snapshot_state.revision
        with self._mutation_authority.external_call():
            admission = self._execution_adapter.call(
                "effect",
                self._inject_execution.admit,
                request,
                context,
                operation_id,
                revision,
                deepcopy(self._snapshot),
                timeout_ms=self._supervision.admission_ms,
            )
        require_inject_plan(self, admission)
        self._require_inject_schedule(request)
        occurrence = InjectOccurrenceModel.model_validate(admission.occurrence.model_dump(mode="json"))
        if (
            occurrence.request != request
            or occurrence.admission != context
            or occurrence.operation_id != operation_id
            or occurrence.store_revision != str(revision)
        ):
            raise InvalidInputError("inject resolver changed the requested admission")
        return InjectAdmission(admission.plan, occurrence)

    def _inject_live_diagnostics(self, occurrence: InjectOccurrenceModel) -> list[Diagnostic]:
        try:
            self._require_inject_schedule(occurrence.request)
            with self._mutation_authority.external_call():
                self._execution_adapter.call(
                    "effect",
                    self._inject_execution.revalidate,
                    occurrence,
                    deepcopy(self._snapshot),
                    timeout_ms=self._supervision.admission_ms,
                )
        except Exception as exc:
            if not isinstance(exc, RaesError):
                # Isolation of the inject resolver: a failed revalidation refuses the live inject.
                _LOGGER.exception(
                    "inject revalidation failed in the inject resolver", exc_info=foreign_failure_record(exc)
                )
            return [_inject_diagnostic()]
        return []

    def _require_inject_schedule(self, request: InjectTriggerRequestModel) -> None:
        if request.placement.kind == "schedule":
            from .inject_schedule import require_schedule

            with self._trusted_runtime_plan_lock:
                model = self._trusted_orchestration_models.get(request.plan.digest)
            if model is None:
                raise ConflictError("inject schedule compiler context is unavailable")
            require_schedule(model, request, self._snapshot)

    def _read_inject_record(
        self, operation_id: str, identity: ControlPlaneIdentity | None
    ) -> ControlPlaneOperationRecord | None:
        self._assert_runtime_owner()
        record = self._store.load_records().get(operation_id)
        return record if record is not None and self._operation_read_allowed(record, identity) else None

    @runtime_owned
    def get_inject_occurrence(
        self, operation_id: str, *, identity: object | None = None
    ) -> InjectOccurrenceModel | None:
        record = self._read_inject_record(operation_id, identity)
        return None if record is None else record.inject_occurrence

    @runtime_owned
    def get_inject_outcome(
        self, operation_id: str, *, identity: object | None = None
    ) -> InjectOccurrenceOutcomeModel | None:
        record = self._read_inject_record(operation_id, identity)
        return None if record is None else record.inject_outcome

    @runtime_owned
    def get_inject_result(
        self, operation_id: str, *, identity: object | None = None
    ) -> AssociatedArtifactManifestModel | None:
        record = self._read_inject_record(operation_id, identity)
        return None if record is None or record.inject_evidence is None else deepcopy(record.inject_evidence.manifest)

    @runtime_owned
    def get_inject_artifact(
        self, operation_id: str, artifact_id: str, *, identity: object | None = None
    ) -> bytes | None:
        record = self._read_inject_record(operation_id, identity)
        if record is None or record.inject_evidence is None:
            return None
        return next((item.content for item in record.inject_evidence.contents if item.artifact_id == artifact_id), None)

    @runtime_owned
    def get_inject_correlation(
        self, operation_id: str, *, identity: object | None = None
    ) -> InjectOccurrenceCorrelationModel | None:
        record = self._read_inject_record(operation_id, identity)
        if record is None or record.inject_outcome is None:
            return None
        try:
            return inject_occurrence_correlation(
                record.inject_occurrence, record.invocation.request, record.inject_outcome
            )
        except ValueError:
            return None

    @runtime_owned
    def get_inject_delivery(
        self, operation_id: str, *, identity: object | None = None
    ) -> ParticipantInjectContentModel | None:
        from .participant_inject_application import _authorized_binding

        record = self._read_inject_record(operation_id, identity)
        if record is None or record.inject_delivery is None or record.status.state.value != "succeeded":
            return None
        try:
            _authorized_binding(self, record.inject_delivery.application, identity)
        except AuthorizationError, ConflictError, InvalidInputError, NotFoundError:
            # Any refusal of the delivery binding reads as an absent record.
            return None
        return deepcopy(record.inject_delivery)

    @runtime_owned
    def get_inject_capture(self, operation_id: str, *, identity: object | None = None) -> InjectCaptureResult | None:
        from .inject_capture import InjectCaptureResult

        record = self._read_inject_record(operation_id, identity)
        if record is None or record.inject_occurrence is None or record.result_payload is None:
            return None
        return InjectCaptureResult.model_validate(deepcopy(record.result_payload))
