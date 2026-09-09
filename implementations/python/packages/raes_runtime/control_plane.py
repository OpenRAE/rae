"""Reference async-style control plane over runtime targets.

This is a repo-owned, schema-oriented façade that exposes runtime execution as
submitted operations over plain-data-compatible envelopes. The current
implementation completes operations eagerly, but the contract surface matches an
async control plane so non-Python runtimes can evolve behind the same API.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import RLock
from typing import TypeVar

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.manifest_authority import PARTICIPANT_RUNTIME_POLICY_FEATURES
from raes_contracts.planning import (
    EvaluationPlan,
    OrchestrationPlan,
    ProvisioningPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationStatus,
    RuntimeSnapshot,
    RuntimeSnapshotEnvelope,
)
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_processor.models import ParticipantBehaviorSpecificationRuntime

from .backend_calls import _call_backend_diagnostics
from .control_plane_admission import RuntimeAdmissionMixin
from .control_plane_durability import RuntimeDurabilityMixin
from .control_plane_execution import (
    OperationExecutionRequest,
    execute_operation,
)
from .control_plane_lifecycle import RuntimeLifecycleMixin, runtime_owned, store_authoritative_state
from .control_plane_operation_context import (
    operation_admission_context,
    operation_idempotency_fingerprint,
    operation_requires_ephemeral_retry_proof,
)
from .control_plane_plan_authorization import RuntimePlanAuthorizationMixin
from .control_plane_recovery import reconcile_interrupted_operations
from .control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    ControlPlaneStore,
    InMemoryControlPlaneStore,
    SnapshotState,
)
from .control_plane_store_compatibility import adapt_control_plane_store
from .control_plane_submission import _submitted_plan_diagnostics
from .control_plane_workflow_control import WorkflowControlMixin
from .operational_apparatus import operational_apparatus_summary
from .participant_control import ParticipantControlMixin
from .participant_crossing_mediation import (
    ParticipantCrossingPolicyResolver,
    validate_persisted_crossing_history,
)
from .participant_information_state_validation import require_participant_information_state_snapshot
from .participant_retrieval import ParticipantRetrievalMixin
from .registry import RuntimeTarget as _RuntimeTarget

_ProjectionT = TypeVar("_ProjectionT")


def _require_crossing_policy_configuration(
    target: _RuntimeTarget,
    resolver: ParticipantCrossingPolicyResolver | None,
) -> None:
    capabilities = target.manifest.participant_runtime
    if capabilities is None:
        return
    enabled_policy_features = {
        declaration.feature
        for declaration in capabilities.feature_support
        if declaration.feature in PARTICIPANT_RUNTIME_POLICY_FEATURES
        and declaration.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED
    }
    if enabled_policy_features and resolver is None:
        features = ", ".join(sorted(enabled_policy_features))
        raise ValueError(f"participant policy capabilities require a crossing policy resolver: {features}")


def _require_final_sink_flow_control_configuration(
    resolver: ParticipantCrossingPolicyResolver | None,
    enforce_final_sink_flow_control: bool,
) -> None:
    """Reject a policy resolver that cannot resolve the SEM-233 final-sink permit.

    Final-sink enforcement is fail-closed by default: a control plane that
    governs participant crossings must resolve a fresh exact-cut SEM-233 permit
    immediately before every effect. A resolver without ``resolve_flow_sink_decision``
    cannot, so the control plane refuses to construct rather than silently
    admitting effects with no final-sink decision. A deployment that intentionally
    runs the legacy API-423-only path passes ``enforce_final_sink_flow_control=False``.
    """

    if not enforce_final_sink_flow_control or resolver is None:
        return
    if not callable(getattr(resolver, "resolve_flow_sink_decision", None)):
        raise ValueError(
            "participant final-sink flow-control enforcement requires the crossing policy "
            "resolver to implement resolve_flow_sink_decision; pass "
            "enforce_final_sink_flow_control=False to run the legacy API-423-only path"
        )


class RuntimeControlPlane(
    RuntimeLifecycleMixin,
    RuntimePlanAuthorizationMixin,
    RuntimeDurabilityMixin,
    RuntimeAdmissionMixin,
    WorkflowControlMixin,
    ParticipantControlMixin,
    ParticipantRetrievalMixin,
):
    """Reference control plane for async runtime submission and observation."""

    def __init__(
        self,
        target: _RuntimeTarget,
        *,
        initial_snapshot: RuntimeSnapshot | None = None,
        store: ControlPlaneStore | None = None,
        behavior_specifications: Mapping[str, ParticipantBehaviorSpecificationRuntime] | None = None,
        crossing_policy_resolver: ParticipantCrossingPolicyResolver | None = None,
        information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
        enforce_final_sink_flow_control: bool = True,
    ) -> None:
        self._initialize_runtime_lifecycle()
        if store is not None and initial_snapshot is not None:
            raise ValueError("initial_snapshot cannot be combined with an explicit store")
        _require_crossing_policy_configuration(target, crossing_policy_resolver)
        _require_final_sink_flow_control_configuration(crossing_policy_resolver, enforce_final_sink_flow_control)
        self._target = target
        self._enforce_final_sink_flow_control = enforce_final_sink_flow_control
        self._store = store or InMemoryControlPlaneStore(initial_snapshot)
        try:
            self._operation_lock = RLock()
            self._snapshot_projection_depth = 0
            self._store_commits = adapt_control_plane_store(self._store)
            acquire_runtime_lease = getattr(self._store, "acquire_runtime_lease", None)
            if callable(acquire_runtime_lease):
                self._runtime_lease = acquire_runtime_lease()
            self._snapshot_state = self._store.load_snapshot_state()
            self._operations: dict[str, ControlPlaneOperationRecord] = self._store.load_records()
            self._operations = reconcile_interrupted_operations(self._store_commits, self._operations)
            self._behavior_specifications = dict(behavior_specifications or {})
            self._crossing_policy_resolver = crossing_policy_resolver
            self._information_state_context_resolver = information_state_context_resolver
            self._ephemeral_idempotency_fingerprints: dict[str, str] = {}
            self._participant_control_lock = self._operation_lock
            self._trusted_runtime_plan_lock = RLock()
            self._trusted_runtime_plan_digests: set[str] = set()
            require_participant_information_state_snapshot(
                self._snapshot,
                information_state_context_resolver,
            )
            if self._snapshot.participant_crossing_history:
                if crossing_policy_resolver is None:
                    raise ValueError("persisted participant crossing history requires a policy resolver")
                validate_persisted_crossing_history(self._snapshot, crossing_policy_resolver)
        except BaseException:
            self.close()
            raise

    @property
    def _snapshot(self) -> RuntimeSnapshot:
        return self._snapshot_state.snapshot

    @_snapshot.setter
    def _snapshot(self, snapshot: RuntimeSnapshot) -> None:
        self._snapshot_state = SnapshotState(
            snapshot=snapshot,
            revision=self._snapshot_state.revision,
        )

    @runtime_owned
    def _project_snapshot_read(
        self,
        projector: Callable[[], _ProjectionT],
    ) -> tuple[_ProjectionT, int]:
        """Project one response from an authoritative, revision-bound state cut."""

        self._assert_runtime_owner()
        with self._operation_lock:
            self._reload_derived_state_if_unpinned()
            observed_state = self._snapshot_state
            self._snapshot_projection_depth += 1
            try:
                projected = projector()
            finally:
                self._snapshot_projection_depth -= 1
            return projected, observed_state.revision

    @property
    @runtime_owned
    def snapshot(self) -> RuntimeSnapshot:
        self._assert_runtime_owner()
        with self._operation_lock:
            self._reload_derived_state_if_unpinned()
            return self._snapshot

    @property
    @runtime_owned
    def target_name(self) -> str:
        self._assert_runtime_owner()
        return self._target.name

    @runtime_owned
    def audit_log(self) -> list[AuditEvent]:
        self._assert_runtime_owner()
        return self._store.read_audit()

    @runtime_owned
    def operational_apparatus_summary(self) -> dict[str, object]:
        """Return a compact operational view over existing control-plane carriers."""

        self._assert_runtime_owner()
        with self._operation_lock:
            self._reload_derived_state_if_unpinned()
            operation_records = list(self._operations.values())
            snapshot = self._snapshot
        audit_events = self._store.read_audit()
        return operational_apparatus_summary(
            target_name=self._target.name,
            snapshot=snapshot,
            operation_records=operation_records,
            audit_events=audit_events,
        )

    @runtime_owned
    @store_authoritative_state
    def submit_provisioning(
        self,
        plan: ProvisioningPlan,
        *,
        base_snapshot: RuntimeSnapshot | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        self._assert_runtime_owner()
        context = operation_admission_context(
            self,
            kind=OperationKind.PROVISIONING,
            request=plan,
            base_snapshot=base_snapshot,
            identity=identity,
        )
        exact_retry_fingerprint = (
            operation_idempotency_fingerprint(
                kind=OperationKind.PROVISIONING,
                request=plan,
                base_snapshot=base_snapshot,
            )
            if operation_requires_ephemeral_retry_proof(request=plan, base_snapshot=base_snapshot)
            else None
        )
        existing = self._idempotent_receipt(
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            exact_retry_fingerprint=exact_retry_fingerprint,
        )
        if existing is not None:
            return existing
        self._require_observed_base_snapshot(base_snapshot)
        diagnostics = _submitted_plan_diagnostics(
            plan,
            RuntimeDomain.PROVISIONING,
            self._snapshot,
            self._target.manifest,
        )
        if not diagnostics:
            diagnostics.extend(self._plan_authorization_diagnostics(plan))
        if diagnostics:
            return self._reject_diagnostics(
                domain=RuntimeDomain.PROVISIONING,
                diagnostics=diagnostics,
                idempotency_key=idempotency_key,
                request_fingerprint=context.request_commitment,
                context=context,
            )
        diagnostics = _call_backend_diagnostics(
            self._target.provisioner.validate,
            plan,
            address="runtime.control-plane.provisioning.validate",
        )
        return execute_operation(
            self,
            OperationExecutionRequest(
                domain=RuntimeDomain.PROVISIONING,
                method=self._target.provisioner.apply,
                plan=plan,
                address="runtime.control-plane.provisioning",
                diagnostics=diagnostics,
                base_snapshot=base_snapshot,
                idempotency_key=idempotency_key,
                request_fingerprint=context.request_commitment,
                context=context,
                exact_retry_fingerprint=exact_retry_fingerprint,
            ),
        )

    @runtime_owned
    @store_authoritative_state
    def submit_orchestration(
        self,
        plan: OrchestrationPlan,
        *,
        base_snapshot: RuntimeSnapshot | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        self._assert_runtime_owner()
        context = operation_admission_context(
            self,
            kind=OperationKind.ORCHESTRATION,
            request=plan,
            base_snapshot=base_snapshot,
            identity=identity,
        )
        exact_retry_fingerprint = (
            operation_idempotency_fingerprint(
                kind=OperationKind.ORCHESTRATION,
                request=plan,
                base_snapshot=base_snapshot,
            )
            if operation_requires_ephemeral_retry_proof(request=plan, base_snapshot=base_snapshot)
            else None
        )
        existing = self._idempotent_receipt(
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            exact_retry_fingerprint=exact_retry_fingerprint,
        )
        if existing is not None:
            return existing
        self._require_observed_base_snapshot(base_snapshot)
        if self._target.orchestrator is None:
            receipt = self._reject_submission(
                domain=RuntimeDomain.ORCHESTRATION,
                message="Target does not provide an orchestrator.",
                request_fingerprint=context.request_commitment,
                context=context,
            )
        else:
            diagnostics = _submitted_plan_diagnostics(plan, RuntimeDomain.ORCHESTRATION, self._snapshot)
            if not diagnostics:
                diagnostics.extend(self._plan_authorization_diagnostics(plan))
            if diagnostics:
                receipt = self._reject_diagnostics(
                    domain=RuntimeDomain.ORCHESTRATION,
                    diagnostics=diagnostics,
                    idempotency_key=idempotency_key,
                    request_fingerprint=context.request_commitment,
                    context=context,
                )
            else:
                receipt = execute_operation(
                    self,
                    OperationExecutionRequest(
                        domain=RuntimeDomain.ORCHESTRATION,
                        method=self._target.orchestrator.start,
                        plan=plan,
                        address="runtime.control-plane.orchestration",
                        diagnostics=[],
                        base_snapshot=base_snapshot,
                        idempotency_key=idempotency_key,
                        request_fingerprint=context.request_commitment,
                        context=context,
                        exact_retry_fingerprint=exact_retry_fingerprint,
                    ),
                )
        return receipt

    @runtime_owned
    @store_authoritative_state
    def submit_evaluation(
        self,
        plan: EvaluationPlan,
        *,
        base_snapshot: RuntimeSnapshot | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        self._assert_runtime_owner()
        context = operation_admission_context(
            self,
            kind=OperationKind.EVALUATION,
            request=plan,
            base_snapshot=base_snapshot,
            identity=identity,
        )
        exact_retry_fingerprint = (
            operation_idempotency_fingerprint(
                kind=OperationKind.EVALUATION,
                request=plan,
                base_snapshot=base_snapshot,
            )
            if operation_requires_ephemeral_retry_proof(request=plan, base_snapshot=base_snapshot)
            else None
        )
        existing = self._idempotent_receipt(
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            exact_retry_fingerprint=exact_retry_fingerprint,
        )
        if existing is not None:
            return existing
        self._require_observed_base_snapshot(base_snapshot)
        if self._target.evaluator is None:
            receipt = self._reject_submission(
                domain=RuntimeDomain.EVALUATION,
                message="Target does not provide an evaluator.",
                request_fingerprint=context.request_commitment,
                context=context,
            )
        else:
            diagnostics = _submitted_plan_diagnostics(plan, RuntimeDomain.EVALUATION, self._snapshot)
            if not diagnostics:
                diagnostics.extend(self._plan_authorization_diagnostics(plan))
            if diagnostics:
                receipt = self._reject_diagnostics(
                    domain=RuntimeDomain.EVALUATION,
                    diagnostics=diagnostics,
                    idempotency_key=idempotency_key,
                    request_fingerprint=context.request_commitment,
                    context=context,
                )
            else:
                receipt = execute_operation(
                    self,
                    OperationExecutionRequest(
                        domain=RuntimeDomain.EVALUATION,
                        method=self._target.evaluator.start,
                        plan=plan,
                        address="runtime.control-plane.evaluation",
                        diagnostics=[],
                        base_snapshot=base_snapshot,
                        idempotency_key=idempotency_key,
                        request_fingerprint=context.request_commitment,
                        context=context,
                        exact_retry_fingerprint=exact_retry_fingerprint,
                    ),
                )
        return receipt

    @runtime_owned
    def get_operation(self, operation_id: str) -> OperationStatus | None:
        self._assert_runtime_owner()
        with self._operation_lock:
            self._operations = self._store.load_records()
            record = self._operations.get(operation_id)
        return None if record is None else record.status

    @runtime_owned
    def get_snapshot(self) -> RuntimeSnapshotEnvelope:
        self._assert_runtime_owner()
        with self._operation_lock:
            self._reload_derived_state_if_unpinned()
            return RuntimeSnapshotEnvelope(snapshot=self._snapshot)

    def _require_observed_base_snapshot(self, base_snapshot: RuntimeSnapshot | None) -> None:
        if base_snapshot is not None and base_snapshot != self._snapshot:
            raise ValueError("explicit base snapshot does not match the authoritative runtime snapshot")
