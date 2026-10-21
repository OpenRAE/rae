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
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import OperationAdmissionContext, OperationKind, OperationReceipt, RuntimeDomain

from .control_plane_execution import OperationExecutionRequest, execute_operation
from .control_plane_lifecycle import runtime_owned, store_authoritative_state
from .control_plane_mutation import control_plane_mutation, mutation_entry
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .control_plane_store import ControlPlaneOperationRecord
from .inject_execution import require_inject_plan


def _authorize_trigger(plane: object, identity: object | None) -> None:
    if identity is None:
        # P0/P1 trusted embedder boundary.
        return
    if (
        not isinstance(identity, ControlPlaneIdentity)
        or identity.target_name != plane._target.name
        or not identity.roles.intersection({ControlPlaneRole.OPERATOR, ControlPlaneRole.BACKEND})
    ):
        raise PermissionError("inject mutation authority is unavailable")


def _inject_diagnostic() -> Diagnostic:
    return Diagnostic(
        code="runtime.inject.admission-refused",
        domain="runtime",
        address="runtime.control-plane.inject",
        message="The authored inject, target, admission or execution contract could not be admitted.",
    )


class RuntimeInjectMixin:
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
            raise ValueError("inject target/run scope mismatch")
        incumbent = self._store.find_by_idempotency(request.request_key, context=context)
        if incumbent is not None:
            if not self._operation_read_allowed(incumbent, identity) or incumbent.inject_occurrence is None:
                raise ValueError("inject retry conflicts with the original request")
            require_inject_trigger_retry(incumbent.inject_occurrence, request, actor_id=context.actor_id)
            return incumbent.receipt
        try:
            admission = self._admit_inject(request, context)
        except Exception:
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
            raise ValueError("inject execution is unavailable in this composition")
        require_inject_occurrence_provider(
            self._target.operation_provider, self._target.manifest.supported_contract_versions
        )
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
            raise ValueError("inject resolver changed the requested admission")
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
        except Exception:
            return [_inject_diagnostic()]
        return []

    def _require_inject_schedule(self, request):
        if request.placement.kind == "schedule":
            from .inject_schedule import require_schedule

            with self._trusted_runtime_plan_lock:
                model = self._trusted_orchestration_models.get(request.plan.digest)
            if model is None:
                raise ValueError("inject schedule compiler context is unavailable")
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
        except (ValueError, PermissionError):
            return None
        return deepcopy(record.inject_delivery)

    @runtime_owned
    def get_inject_capture(self, operation_id: str, *, identity: object | None = None):
        from .inject_capture import InjectCaptureResult

        record = self._read_inject_record(operation_id, identity)
        if record is None or record.inject_occurrence is None or record.result_payload is None:
            return None
        return InjectCaptureResult.model_validate(deepcopy(record.result_payload))
