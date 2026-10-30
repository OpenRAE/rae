"""Shared execution capacity and resource ownership across fixed run contexts."""

from __future__ import annotations

from threading import RLock
from time import monotonic
from typing import TYPE_CHECKING
from weakref import ref

from raes_contracts.errors import ConflictError, NotFoundError, OperationalError
from raes_contracts.runtime_state import OperationState

from .control_plane_recovery import unresolved_indeterminate_operation_ids_from_records
from .control_plane_store import NewClaimRejected
from .errors import RuntimeBudgetExhaustedError
from .operation_execution_adapter import LocalExecutionAdapter
from .runtime_decisions import RunContextDecision, runtime_store_digest
from .runtime_resource_ownership import RuntimeResourceClaim, ledger_identity

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane
    from .control_plane_configuration import ControlPlaneConfiguration
    from .registry import RuntimeTarget
    from .runtime_decisions import RuntimeDecision
    from .runtime_run_context import RuntimeRunContext

_ENGINE_CLOSED = "runtime engine is closed"


class RuntimeEngineResources:
    def __init__(
        self, owner: RuntimeControlPlane, target: RuntimeTarget, configuration: ControlPlaneConfiguration
    ) -> None:
        self._owner = ref(owner)
        self.target = target
        self.configuration = configuration
        self._lock = RLock()
        self._runs = {}
        self._operation_contexts = {}
        self._reserved_run = None
        self.adapter = None
        self.claim = None
        self.closing = False
        self.closed = False

    @property
    def owner(self) -> RuntimeControlPlane:
        owner = self._owner()
        if owner is None:
            raise RuntimeError("runtime engine owner is unavailable")
        return owner

    def bind(self, context: RuntimeRunContext) -> None:
        with self._lock:
            if self.closing or self.closed:
                raise OperationalError(_ENGINE_CLOSED)
            if self.claim is None:
                self.claim = RuntimeResourceClaim(self.owner, self.target, ledger=ledger_identity(context._store))
            if self.adapter is None:
                bounds = self.configuration.supervision
                self.adapter = LocalExecutionAdapter(
                    effect_capacity=bounds.effect_capacity,
                    control_capacity=bounds.control_capacity,
                    store_capacity=bounds.store_capacity,
                )
            context._resource_claim = self.claim
            context._execution_adapter = self.adapter

    def contexts(self) -> tuple[RuntimeRunContext, ...]:
        owner = self.owner
        return (owner, *self._runs.values())

    def register_operation(self, context: RuntimeRunContext, operation_id: str) -> None:
        with self._lock:
            prior = self._operation_contexts.get(operation_id)
            if prior is not None and prior is not context:
                raise ConflictError("operation identity already belongs to another run context")
            self._operation_contexts[operation_id] = context

    def operation_context(self, operation_id: str) -> RuntimeRunContext:
        with self._lock:
            return self._operation_contexts.get(operation_id, self.owner)

    def restore_context(self, context: RuntimeRunContext) -> None:
        for operation_id in context._operations:
            self.register_operation(context, operation_id)
        reader = getattr(self.owner._store, "load_runtime_decisions", None)
        if reader is not None:
            for record in reader():
                if (
                    isinstance(record, RunContextDecision)
                    and record.run_scope == context._run_scope
                    and record.status == "retired"
                ):
                    if record.store_digest != runtime_store_digest(context._store):
                        raise ConflictError("retired run store identity conflicts with its retained binding")
                    context._retired = True
                    context._effect_admission_stopped = True

    def get_run(self, run_scope: str) -> RuntimeRunContext:
        with self._lock:
            if run_scope == self.owner._run_scope:
                return self.owner
            try:
                return self._runs[run_scope]
            except KeyError:
                raise NotFoundError("run scope is not owned by this engine") from None

    def open_run(self, configuration: ControlPlaneConfiguration) -> RuntimeRunContext:
        from .runtime_run_context import RuntimeRunContext

        with self._lock:
            if self.closed or self.closing:
                raise OperationalError(_ENGINE_CLOSED)
            if configuration.run_scope == self.owner._run_scope or configuration.run_scope in self._runs:
                raise ConflictError("run scope already belongs to this engine")
            from dataclasses import replace

            from .control_plane_store import InMemoryControlPlaneStore

            if configuration.store is None:
                configuration = replace(
                    configuration,
                    store=InMemoryControlPlaneStore(configuration.initial_snapshot),
                    initial_snapshot=None,
                )
            identity = ledger_identity(configuration.store)
            if ledger_identity(self.owner._store)[0] != "in-memory-ledger" and identity[0] == "in-memory-ledger":
                raise ValueError("a durable engine requires a durable store for each run")
            if any(ledger_identity(context._store) == identity for context in self.contexts()):
                raise ValueError("each run context requires its own scope-bound store")
            decision = RunContextDecision(
                run_scope=configuration.run_scope,
                store_digest=runtime_store_digest(configuration.store),
                status="opened",
            )
            self.owner._store.claim_runtime_decision(decision)
            context = RuntimeRunContext(self.target, config=configuration, engine=self)
            self._runs[configuration.run_scope] = context
            return context

    def reserve(self, context: RuntimeRunContext) -> None:
        """Retain target exclusion until verified run retirement, including unknown effects."""
        with self._lock:
            if self.closed or self.closing:
                raise OperationalError(_ENGINE_CLOSED)
            if context._retired:
                raise ConflictError("runtime run is retired")
            if self.owner._store.effect_admission_stopped():
                raise NewClaimRejected("runtime engine effect admission is closed")
            if self._reserved_run is not None and self._reserved_run is not context:
                raise ConflictError("target resources are reserved by another run")
            self._require_restored_contexts(context)
            self._require_other_runs_idle(context)
            self._reserved_run = context

    def _require_restored_contexts(self, context: RuntimeRunContext) -> None:
        reader = getattr(self.owner._store, "load_runtime_decisions", None)
        if reader is not None:
            decisions = tuple(record for record in reader() if isinstance(record, RunContextDecision))
            opened = {record.run_scope for record in decisions if record.status == "opened"}
            retired = {record.run_scope for record in decisions if record.status == "retired"}
            unrestored = opened - retired - set(self._runs)
            if unrestored - {context._run_scope}:
                raise ConflictError("reserved run contexts must be restored before effects")

    def _require_other_runs_idle(self, context: RuntimeRunContext) -> None:
        # Restored run state retains exclusion even before a fresh command.
        for other in self.contexts():
            if other is context or getattr(other, "_retired", False):
                continue
            if self._context_has_reservation(other):
                raise ConflictError("target resources are reserved by another run")

    def _context_has_reservation(self, context: RuntimeRunContext) -> bool:
        return getattr(context, "_durability_poisoned", False) or (
            hasattr(context, "_snapshot_state") and bool(context._snapshot.entries or self.unresolved(context))
        )

    @staticmethod
    def unresolved(context: RuntimeRunContext) -> bool:
        records = getattr(context, "_operations", {})
        return (
            getattr(context, "_durability_poisoned", False)
            or bool(unresolved_indeterminate_operation_ids_from_records(records))
            or any(
                record.status.state in {OperationState.ACCEPTED, OperationState.RUNNING} for record in records.values()
            )
        )

    def retire(self, context: RuntimeRunContext) -> None:
        with self._lock:
            if context._retired:
                return
            self._require_trial_reuse(context)
            self._require_idle_context(context)
            self.owner._store.claim_runtime_decision(
                RunContextDecision(
                    run_scope=context._run_scope,
                    store_digest=runtime_store_digest(context._store),
                    status="retired",
                )
            )
            context._retired = True
            context._effect_admission_stopped = True
            if self._reserved_run is context:
                self._reserved_run = None

    def _require_trial_reuse(self, context: RuntimeRunContext) -> None:
        from .runtime_trial_decisions import TrialAttemptDecision, TrialTerminalDecision

        records = self.owner._store.load_runtime_decisions()
        attempts = [
            record
            for record in records
            if isinstance(record, TrialAttemptDecision) and "run:" + record.run_id == context._run_scope
        ]
        terminals = {
            record.execution_attempt_id: record for record in records if isinstance(record, TrialTerminalDecision)
        }
        if any(
            attempt.execution_attempt_id not in terminals or not terminals[attempt.execution_attempt_id].reusable
            for attempt in attempts
        ):
            raise ConflictError("trial cleanup evidence does not permit target reuse")
        self._require_retry_completion(context, {attempt.execution_attempt_id for attempt in attempts})

    def _require_retry_completion(self, context: RuntimeRunContext, attempt_ids: set[str]) -> None:
        from .runtime_trial_decisions import TrialObservationDecision

        local = context._store.load_runtime_decisions()
        retry_started = self._retry_phases(local, attempt_ids, "started")
        retry_finished = self._retry_phases(local, attempt_ids, "succeeded")
        retry_ready = {
            record.execution_attempt_id
            for record in local
            if isinstance(record, TrialObservationDecision)
            and record.observation.kind == "retry"
            and record.observation.ready
        }
        if retry_started - (retry_finished & retry_ready):
            raise ConflictError("retry preparation has not restored verified reusable state")

    @staticmethod
    def _retry_phases(records: tuple[RuntimeDecision, ...], attempt_ids: set[str], state: str) -> set[str]:
        from .runtime_decisions import RunPhaseDecision

        return {
            record.execution_id
            for record in records
            if isinstance(record, RunPhaseDecision)
            and record.execution_id in attempt_ids
            and record.phase == 4
            and record.state == state
        }

    def _require_idle_context(self, context: RuntimeRunContext) -> None:
        own_depth = getattr(context._lifecycle_local, "depth", 0)
        if context._active_runtime_calls > own_depth or (self.adapter is not None and self.adapter.pending_calls):
            raise ConflictError("runtime callbacks remain active")
        context._reload_derived_state()
        if self.unresolved(context):
            raise ConflictError("run has unresolved effects; target remains reserved")
        if context._snapshot.entries:
            raise ConflictError("run requires verified cleanup before target reuse")
        if not context._stop_participant_clock_driver():
            raise ConflictError("runtime clock callbacks remain active")

    def close(self) -> None:
        """Close all contexts before releasing shared capacity or backend ownership."""
        with self._lock:
            if self.closed:
                return
            if self.claim is not None and self.claim.active_calls:
                raise ConflictError("runtime callbacks remain active")
        owner = self.owner
        bounds = self.configuration.supervision
        budget = bounds.drain_ms / 1000
        if not owner._begin_runtime_close(owner._lifecycle_condition, budget):
            return
        with self._lock:
            self.closing = True
        contexts = tuple(context for context in self.contexts() if hasattr(context, "_lifecycle_condition"))
        deadline = monotonic() + budget
        provider_close_started = False
        try:
            self._drain_contexts(contexts, budget, deadline)
            self._settle_dispatcher(contexts, deadline)
            unresolved = any(self.unresolved(context) for context in contexts)
            provider_close_started = True
            self._close_providers(contexts)
            self._release_capacity(unresolved, deadline)
            self._finish_close(contexts)
        except BaseException:
            self._abort_close(contexts, provider_close_started)
            raise

    def _release_capacity(self, unresolved: bool, deadline: float) -> None:
        if self.adapter is not None and not self.adapter.close(timeout_ms=self._remaining(deadline)):
            raise RuntimeBudgetExhaustedError("runtime drain has unresolved external calls")
        if self.claim is not None:
            self.claim.release(unresolved=unresolved)

    def _drain_contexts(self, contexts: tuple[RuntimeRunContext, ...], budget: float, deadline: float) -> None:
        for context in contexts:
            if context is self.owner or context._begin_runtime_close(context._lifecycle_condition, budget):
                if not context._stop_participant_clock_driver():
                    raise RuntimeBudgetExhaustedError("runtime clock driver remains active")
                context._drain_runtime_calls(context._lifecycle_condition, None, deadline)
        if self.adapter is not None and not self.adapter.drain(timeout_ms=self._remaining(deadline)):
            raise RuntimeBudgetExhaustedError("runtime drain has unresolved external calls")

    def _settle_dispatcher(self, contexts: tuple[RuntimeRunContext, ...], deadline: float) -> None:
        for context in contexts:
            if not context._closed and context._distributed_execution is not None:
                context._settle_shutdown_invocations()
        dispatcher = self.configuration.distributed_execution
        if dispatcher is not None and self.adapter is not None:
            self.adapter.call("control", dispatcher.close, timeout_ms=self._remaining(deadline))

    @staticmethod
    def _close_providers(contexts: tuple[RuntimeRunContext, ...]) -> None:
        for context in contexts:
            if not context._closed:
                context._close_runtime_provider()
        for context in contexts:
            if not context._closed:
                context._close_runtime_lease()

    def _finish_close(self, contexts: tuple[RuntimeRunContext, ...]) -> None:
        with self._lock:
            self.closed = True
            self.closing = False
        for context in contexts:
            with context._lifecycle_condition:
                context._closed = True
                context._closing = False
                context._lifecycle_condition.notify_all()

    def _abort_close(self, contexts: tuple[RuntimeRunContext, ...], provider_close_started: bool) -> None:
        if self.claim is not None:
            self.claim.retain_unresolved()
        for context in reversed(contexts):
            if context is not self.owner:
                context._abort_runtime_close(context._lifecycle_condition, provider_close_started)
        with self._lock:
            self.closing = False
        self.owner._abort_runtime_close(self.owner._lifecycle_condition, provider_close_started)

    @staticmethod
    def _remaining(deadline: float) -> int:
        return max(1, int((deadline - monotonic()) * 1000))
