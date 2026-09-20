"""Reference async-style control plane over runtime targets."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import TypeVar, Unpack

from raes_contracts.diagnostics import Diagnostic
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

from .control_plane_admission import RuntimeAdmissionMixin
from .control_plane_composition import (
    require_crossing_policy_configuration,
    require_final_sink_flow_control_configuration,
)
from .control_plane_configuration import ControlPlaneConfiguration, ControlPlaneOptions
from .control_plane_durability import RuntimeDurabilityMixin
from .control_plane_execution import (
    OperationExecutionRequest,
    execute_operation,
    reject_new_operation_if_admission_fails,
)
from .control_plane_lifecycle import RuntimeLifecycleMixin, runtime_owned, store_authoritative_state
from .control_plane_mutation import (
    RuntimeMutationAuthority,
    SubordinateMutationGate,
    control_plane_mutation,
    mutation_entry,
)
from .control_plane_operation_context import (
    legacy_operation_request_commitment,
    operation_actor_scope,
    operation_admission_context,
    operation_idempotency_fingerprint,
    operation_requires_ephemeral_retry_proof,
    runtime_target_scope,
)
from .control_plane_plan_authorization import RuntimePlanAuthorizationMixin
from .control_plane_profiles import (
    CORE_CAPABILITIES,
    ControlPlaneProfile,
    ControlPlaneProfileDeclaration,
    require_profile_capabilities,
    select_profile,
    store_capabilities,
)
from .control_plane_recovery import RuntimeRecoveryMixin, reconcile_startup_operations
from .control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    IdempotencyClaimIdentity,
    InMemoryControlPlaneStore,
    RuntimeAdmittedControlPlaneStore,
    SnapshotState,
    require_operation_record_scopes,
)
from .control_plane_store_compatibility import adapt_control_plane_store
from .control_plane_submission import control_plane_plan_diagnostics
from .control_plane_workflow_control import WorkflowControlMixin
from .observation_execution import ObservationExecution
from .observation_results import observation_execution_from_payload
from .operational_apparatus import operational_apparatus_summary
from .participant_control import ParticipantControlMixin
from .participant_crossing_mediation import (
    validate_persisted_crossing_history,
)
from .participant_information_state_validation import require_participant_information_state_snapshot
from .participant_retrieval import ParticipantRetrievalMixin
from .registry import RuntimeTarget as _RuntimeTarget

_ProjectionT = TypeVar("_ProjectionT")


def _unavailable_backend_diagnostics(domain: RuntimeDomain, component: str) -> list[Diagnostic]:
    return [
        Diagnostic(
            code="runtime.control-plane.rejected",
            domain="runtime",
            address=f"runtime.control-plane.{domain.value}",
            message=f"Target does not provide {component}.",
        )
    ]


def _unavailable_backend(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("an unavailable backend cannot be invoked")


class RuntimeControlPlane(
    RuntimeLifecycleMixin,
    RuntimeRecoveryMixin,
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
        **options: Unpack[ControlPlaneOptions],
    ) -> None:
        config = ControlPlaneConfiguration(**options)
        target_scope = runtime_target_scope(target.name)
        initial_snapshot, store = config.initial_snapshot, config.store
        crossing_policy_resolver = config.crossing_policy_resolver
        information_state_context_resolver = config.information_state_context_resolver
        if store is not None and initial_snapshot is not None:
            raise ValueError("initial_snapshot cannot be combined with an explicit store")
        declaration = select_profile(config.profile) if config.profile is not None else None
        if declaration is not None and declaration.profile is ControlPlaneProfile.P2:
            raise ValueError("P2 is selected by the HTTP composition over a P1 core")
        selected_store = store if store is not None else InMemoryControlPlaneStore(initial_snapshot)
        provider_capabilities = store_capabilities(selected_store) if declaration is not None else frozenset()
        scope_binder = getattr(selected_store, "bind_scope", None)
        if declaration is not None:
            require_profile_capabilities(declaration, CORE_CAPABILITIES | provider_capabilities)
            if declaration.profile is ControlPlaneProfile.P0 and not callable(scope_binder):
                raise TypeError("control-plane profile P0 missing capabilities: store.scope-bound")
            if declaration.profile is ControlPlaneProfile.P1 and not isinstance(
                selected_store, RuntimeAdmittedControlPlaneStore
            ):
                raise TypeError("control-plane profile P1 missing capabilities: store.owner-lease")
        self._profile_declaration = declaration
        self._initialize_runtime_lifecycle()
        require_crossing_policy_configuration(target, crossing_policy_resolver)
        require_final_sink_flow_control_configuration(crossing_policy_resolver, config.enforce_final_sink_flow_control)
        self._target = target
        self._target_scope, self._run_scope = target_scope, config.run_scope
        self._materialization_archive = config.materialization_archive
        self._enforce_final_sink_flow_control = config.enforce_final_sink_flow_control
        self._store = selected_store
        try:
            self._mutation_authority = RuntimeMutationAuthority()
            self._operation_lock = RLock()
            self._snapshot_projection_depth = 0
            self._store_commits = adapt_control_plane_store(self._store)
            if declaration is not None and declaration.profile is ControlPlaneProfile.P0:
                owner = scope_binder(target_scope=target_scope, run_scope=config.run_scope)
                if not callable(getattr(owner, "assert_owner", None)) or not callable(getattr(owner, "close", None)):
                    close = getattr(owner, "close", None)
                    if callable(close):
                        close()
                    raise TypeError("control-plane profile P0 missing capabilities: store.scope-bound")
                self._runtime_lease = owner
            if isinstance(self._store, RuntimeAdmittedControlPlaneStore):
                self._runtime_lease = self._store.admit_runtime(
                    target_scope=self._target_scope,
                    run_scope=self._run_scope,
                )
            self._snapshot_state = self._store.load_snapshot_state()
            self._operations: dict[str, ControlPlaneOperationRecord] = self._store.load_records()
            require_operation_record_scopes(
                self._operations, target_scope=self._target_scope, run_scope=self._run_scope
            )
            self._behavior_specifications = dict(config.behavior_specifications or {})
            self._crossing_policy_resolver = crossing_policy_resolver
            self._information_state_context_resolver = information_state_context_resolver
            self._ephemeral_idempotency_fingerprints: dict[IdempotencyClaimIdentity, str] = {}
            self._participant_control_lock = SubordinateMutationGate(self._mutation_authority)
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
            reconcile_startup_operations(self)
            self._runtime_ready = True
        except BaseException:
            self.close()
            raise

    @property
    def _snapshot(self) -> RuntimeSnapshot:
        return self._snapshot_state.snapshot

    @property
    @runtime_owned
    def profile_declaration(self) -> ControlPlaneProfileDeclaration | None:
        """The selected core profile, or no claim for a legacy composition."""

        self._assert_runtime_owner()
        return self._profile_declaration

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
        *,
        mutation_kind: OperationKind | None = None,
    ) -> tuple[_ProjectionT, int]:
        """Project one response from an authoritative, revision-bound state cut."""

        self._assert_runtime_owner()
        if mutation_kind is not None:
            with control_plane_mutation(self, mutation_kind):
                with self._operation_lock:
                    self._reload_derived_state_if_unpinned()
                    observed_state = self._snapshot_state
                    self._snapshot_projection_depth += 1
                try:
                    projected = projector()
                finally:
                    with self._operation_lock:
                        self._snapshot_projection_depth -= 1
                return projected, observed_state.revision
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
    @mutation_entry(OperationKind.PROVISIONING)
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
        request = OperationExecutionRequest(
            domain=RuntimeDomain.PROVISIONING,
            method=self._target.provisioner.apply,
            plan=plan,
            address="runtime.control-plane.provisioning",
            diagnostics=[],
            validation_method=(self._target.provisioner.validate if plan.preparation is None else None),
            base_snapshot=base_snapshot,
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            legacy_request_fingerprint=legacy_operation_request_commitment(
                kind=OperationKind.PROVISIONING,
                request=plan,
                base_snapshot=base_snapshot,
            ),
            exact_retry_fingerprint=exact_retry_fingerprint,
            admission_diagnostics=lambda: control_plane_plan_diagnostics(self, plan, RuntimeDomain.PROVISIONING),
        )
        denied_or_replay = reject_new_operation_if_admission_fails(self, request)
        return denied_or_replay or execute_operation(self, request)

    @runtime_owned
    @mutation_entry(OperationKind.ORCHESTRATION)
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
        orchestrator = self._target.orchestrator
        request = OperationExecutionRequest(
            domain=RuntimeDomain.ORCHESTRATION,
            method=_unavailable_backend if orchestrator is None else orchestrator.start,
            plan=plan,
            address="runtime.control-plane.orchestration",
            diagnostics=[],
            base_snapshot=base_snapshot,
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            legacy_request_fingerprint=legacy_operation_request_commitment(
                kind=OperationKind.ORCHESTRATION,
                request=plan,
                base_snapshot=base_snapshot,
            ),
            exact_retry_fingerprint=exact_retry_fingerprint,
            admission_diagnostics=(
                (lambda: _unavailable_backend_diagnostics(RuntimeDomain.ORCHESTRATION, "an orchestrator"))
                if orchestrator is None
                else lambda: control_plane_plan_diagnostics(self, plan, RuntimeDomain.ORCHESTRATION)
            ),
        )
        denied_or_replay = reject_new_operation_if_admission_fails(self, request)
        return denied_or_replay or execute_operation(self, request)

    @runtime_owned
    @mutation_entry(OperationKind.EVALUATION)
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
        evaluator = self._target.evaluator
        request = OperationExecutionRequest(
            domain=RuntimeDomain.EVALUATION,
            method=_unavailable_backend if evaluator is None else evaluator.start,
            plan=plan,
            address="runtime.control-plane.evaluation",
            diagnostics=[],
            base_snapshot=base_snapshot,
            idempotency_key=idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            legacy_request_fingerprint=legacy_operation_request_commitment(
                kind=OperationKind.EVALUATION,
                request=plan,
                base_snapshot=base_snapshot,
            ),
            exact_retry_fingerprint=exact_retry_fingerprint,
            admission_diagnostics=(
                (lambda: _unavailable_backend_diagnostics(RuntimeDomain.EVALUATION, "an evaluator"))
                if evaluator is None
                else lambda: control_plane_plan_diagnostics(self, plan, RuntimeDomain.EVALUATION)
            ),
        )
        denied_or_replay = reject_new_operation_if_admission_fails(self, request)
        return denied_or_replay or execute_operation(self, request)

    @runtime_owned
    def get_operation(
        self,
        operation_id: str,
        *,
        identity: object | None = None,
    ) -> OperationStatus | None:
        self._assert_runtime_owner()
        with self._operation_lock:
            self._operations = self._store.load_records()
            record = self._operations.get(operation_id)
        if record is None or not self._operation_read_allowed(record, identity):
            return None
        return record.status

    def _operation_read_allowed(
        self,
        record: ControlPlaneOperationRecord,
        identity: object | None,
    ) -> bool:
        if identity is None:
            return True
        target_name = getattr(identity, "target_name", None)
        if target_name is not None and target_name != self._target.name:
            return False
        actor_id, authorization_scope = operation_actor_scope(identity)
        context = record.status.context
        return (actor_id, authorization_scope) == (context.actor_id, context.authorization_scope)

    @runtime_owned
    def observation_execution(self, operation_id: str) -> ObservationExecution | None:
        """Return committed metadata and explicitly retained descriptions."""

        self._assert_runtime_owner()
        with self._operation_lock:
            self._operations = self._store.load_records()
            record = self._operations.get(operation_id)
        return observation_execution_from_payload(None if record is None else record.result_payload)

    @runtime_owned
    def get_snapshot(self) -> RuntimeSnapshotEnvelope:
        self._assert_runtime_owner()
        with self._operation_lock:
            self._reload_derived_state_if_unpinned()
            return RuntimeSnapshotEnvelope(snapshot=self._snapshot)
