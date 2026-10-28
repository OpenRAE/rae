"""The trial handoff implemented by modules of the shared runtime engine."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic

from raes_contracts.contracts.trial_replacement_archive import replacement_resources_reusable
from raes_contracts.trial_unit import TrialUnitResult, validate_trial_unit_result

from .control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload
from .operation_policy_admission import authored_attempt_budget
from .runtime_decisions import RunPhaseDecision
from .runtime_module_step import advance_step, step_records
from .runtime_run_cleanup import advance_destroy
from .runtime_trial_decisions import TrialInterruptionDecision, TrialObservationDecision
from .runtime_trial_services import TrialExecutionObservation


class TrialPending(RuntimeError):
    """The attempt needs observation or reconciliation, never blind redispatch."""


class RuntimeTrialUnit:
    def __init__(self, run, request, realization, services, attempt, identity):
        self.run, self.request, self.realization = run, replace(request), realization
        self.services, self.attempt, self.identity = services, attempt, identity
        started = datetime.fromisoformat(attempt.started_at)
        deadline = datetime.fromisoformat(attempt.deadline)
        now = datetime.now(UTC)
        if now < started or deadline <= started:
            raise ValueError("trial clock continuity is unavailable")
        # A local wall-clock adjustment cannot renew an admitted allowance.
        # Restoration uses only the remaining part of the retained UTC bound.
        self._deadline = monotonic() + max(0, (deadline - now).total_seconds())
        owner = run._engine.owner
        experiment = owner._experiments.get(attempt.experiment_id)
        if (
            experiment is None
            or experiment.services is not services
            or attempt not in owner._store.load_runtime_decisions()
            or run._run_scope != "run:" + request.run_id
            or attempt.execution_attempt_id != request.execution_attempt_id
            or realization.snapshot_digest != request.instantiated_sdl_digest
            or realization.provisioning_plan != request.provisioning_plan
            or realization.orchestration_plan != request.orchestration_plan
            or realization.evaluation_plan != request.evaluation_plan
        ):
            raise ValueError("trial adapter is not bound to its engine admission")

    def observations(self):
        return {
            record.observation.kind: record
            for record in self.run._store.load_runtime_decisions()
            if isinstance(record, TrialObservationDecision)
            and record.execution_attempt_id == self.request.execution_attempt_id
        }

    def _validate(self, observation):
        # Reconstruct nested untrusted values before their installed owner checks
        # content and live probes. A valid reference alone cannot pass this gate.
        observation = type(observation).model_validate(observation.model_dump(mode="json"))
        if any(
            item.run_ref.ref_kind != "run" or item.run_ref.ref_id != self.request.run_id
            for item in observation.evidence
        ):
            raise ValueError("trial evidence belongs to another run")
        if observation.kind == "configuration":
            if observation.configurations != self.request.participant_configurations:
                raise ValueError("observed participant configuration differs from admitted settings")
            if observation.configurations and not observation.evidence:
                raise ValueError("applied participant settings require observed evidence")
        if observation.kind == "execution" and observation.ceased and not observation.evidence:
            raise ValueError("execution cessation requires observed evidence")
        if observation.kind == "retry":
            self._validate_retry(observation)
        self.run._execution_adapter.call(
            "control",
            self.services.verify,
            self.request,
            observation,
            timeout_ms=self.run._supervision.observation_ms,
        )
        return observation

    def _validate_retry(self, observation):
        plan = self.request.cleanup_plan
        evidence_ids = {item.evidence_record_id for item in observation.evidence}
        for key, result in observation.obligation_results.items():
            obligation = plan.cleanup_obligations.get(key)
            if obligation is None or key != result.obligation_id or "retry" not in obligation.triggers:
                raise ValueError("retry observation does not match an authored retry obligation")
            if not set(result.evidence_refs) <= evidence_ids:
                raise ValueError("retry obligation evidence is missing")
        if observation.ready:
            if not evidence_ids:
                raise ValueError("retry readiness requires verified evidence")
            owed = {
                key
                for key, value in plan.cleanup_obligations.items()
                if value.requirement == "required" and "retry" in value.triggers
            }
            if any(
                key not in observation.obligation_results or observation.obligation_results[key].status != "succeeded"
                for key in owed
            ):
                raise ValueError("retry readiness omits required retry obligations")
            if not set(plan.retry_policy.compensation_refs) <= set(observation.verified_compensations):
                raise ValueError("retry readiness omits authored compensation")

    def prepare_retry(self):
        return self._module(4, self.services.prepare_retry)

    def _module(self, phase, method, *, outcome=None):
        run, request = self.run, self.request

        def invoke(snapshot):
            if outcome is None:
                result, observation = method(request, snapshot)
            else:
                result, observation = method(request, outcome, snapshot)
            expected = {0: "configuration", 1: "capture", 2: "cleanup", 4: "retry"}[phase]
            if getattr(observation, "kind", None) != expected:
                raise ValueError("trial module returned another evidence kind")
            observation = self._validate(observation)
            run._store.claim_runtime_decision(
                TrialObservationDecision(
                    execution_attempt_id=request.execution_attempt_id,
                    observation=observation,
                    snapshot_json=(
                        json.dumps(_snapshot_payload(result.snapshot), sort_keys=True, separators=(",", ":"))
                        if observation.kind == "configuration"
                        else None
                    ),
                )
            )
            return result

        return advance_step(
            run,
            execution_id=request.execution_attempt_id,
            phase=phase,
            dispatch=lambda key: run._interaction_backend_call(
                invoke,
                request,
                run.snapshot,
                address=f"runtime.trial.{phase}",
                snapshot=run.snapshot,
                runtime_composition=True,
                idempotency_key=key,
                identity=self.identity,
            ),
        )

    def _stop(self, cause):
        run, request = self.run, self.request
        return advance_step(
            run,
            execution_id=request.execution_attempt_id,
            phase=3,
            dispatch=lambda key: run._interaction_backend_call(
                lambda snapshot: self.services.stop(request, cause, snapshot),
                request,
                cause,
                run.snapshot,
                address="runtime.trial.stop",
                snapshot=run.snapshot,
                runtime_composition=True,
                idempotency_key=key,
                identity=self.identity,
            ),
        )

    def advance(self, *, cancelled=False):
        """Advance a bounded lifecycle cut; pending and unknown retain reservation."""
        observed = self.observations()
        execution = observed.get("execution")
        if execution is None:
            state = self._execution(cancelled)
            if state != "progress":
                return state
            return "progress"
        execution = execution.observation
        if not execution.ceased:
            return "indeterminate"
        capture = self._module(1, self.services.capture)
        if capture in {"pending", "indeterminate"}:
            return capture
        # Capture is retained before teardown, including an explicit failed cut.
        teardown = advance_destroy(self.run, self.request.execution_attempt_id + ":destroy", self.identity)
        if teardown != "succeeded":
            return "cleanup-failed" if teardown in {"failed", "cancelled"} else teardown
        cleanup = self._module(2, self.services.cleanup, outcome=execution.state)
        if cleanup in {"pending", "indeterminate"}:
            return cleanup
        if cleanup != "succeeded":
            return "cleanup-failed"
        self.result()
        return "succeeded"

    def _execution(self, cancelled):
        run, request = self.run, self.request
        expired = monotonic() >= self._deadline or datetime.now(UTC) >= datetime.fromisoformat(self.attempt.deadline)
        interruption = next(
            (
                record
                for record in run._store.load_runtime_decisions()
                if isinstance(record, TrialInterruptionDecision)
                and record.execution_attempt_id == request.execution_attempt_id
            ),
            None,
        )
        if interruption is None and (cancelled or expired):
            interruption = TrialInterruptionDecision(
                execution_attempt_id=request.execution_attempt_id,
                cause="cancellation" if cancelled else "timeout",
                disposition=request.execution_controls.on_cancellation
                if cancelled
                else request.execution_controls.on_timeout,
            )
            run._store.claim_runtime_decision(interruption)
        forced = None
        if interruption is not None:
            forced = (
                "aborted"
                if interruption.disposition == "abort"
                else ("cancelled" if interruption.cause == "cancellation" else "timed-out")
            )
            state = self._stop(interruption.cause)
            if state in {"pending", "indeterminate"}:
                return state
        else:
            state = self._apply()
            if state in {"progress", "pending", "indeterminate"}:
                return state
            if state != "succeeded":
                forced = state
        with run._mutation_authority.external_call():
            observation = run._execution_adapter.call(
                "control",
                self.services.observe,
                request,
                deepcopy(run.snapshot),
                timeout_ms=run._supervision.observation_ms,
            )
            observation = self._validate(observation)
        if not isinstance(observation, TrialExecutionObservation):
            raise ValueError("execution observer returned another evidence kind")
        if observation.state == "running" or not observation.ceased:
            return "indeterminate" if forced is not None else "pending"
        if forced is not None:
            observation = observation.model_copy(update={"state": forced})
        run._store.claim_runtime_decision(
            TrialObservationDecision(
                execution_attempt_id=request.execution_attempt_id,
                observation=observation,
                snapshot_json=json.dumps(_snapshot_payload(run.snapshot), sort_keys=True, separators=(",", ":")),
            )
        )
        return "progress"

    def _apply(self):
        with authored_attempt_budget(self._deadline):
            configuration = self._module(0, self.services.configure)
            if configuration != "succeeded":
                return configuration
            return self.run.advance_plan(
                replace(
                    self.realization.execution_plan,
                    base_snapshot=_snapshot_from_payload(
                        json.loads(self.observations()["configuration"].snapshot_json)
                    ),
                ),
                execution_id=self.request.execution_attempt_id + ":apply",
                identity=self.identity,
            ).state

    def result(self):
        observed = self.observations()
        if "execution" not in observed or "cleanup" not in observed:
            raise TrialPending("trial does not have terminal execution and cleanup observations")
        cleanup = observed["cleanup"].observation
        if cleanup.receipt.trial_outcome != observed["execution"].observation.state:
            raise ValueError("cleanup receipt changed the observed trial outcome")
        execution_ids = {self.request.execution_attempt_id + suffix for suffix in ("", ":apply", ":destroy")}
        operation_ids = {
            operation_id
            for decision in self.run._store.load_runtime_decisions()
            if isinstance(decision, RunPhaseDecision) and decision.execution_id in execution_ids
            for operation_id in decision.operation_ids
        }
        result = TrialUnitResult(
            operation_receipts=tuple(
                record.receipt for key, record in self.run._store.load_records().items() if key in operation_ids
            ),
            execution_snapshot=_snapshot_from_payload(json.loads(observed["execution"].snapshot_json)),
            evidence=tuple(
                item
                for kind in ("configuration", "execution", "capture", "retry")
                if kind in observed
                for item in observed[kind].observation.evidence
            ),
            cleanup_receipt=cleanup.receipt,
            cleanup_evidence=cleanup.evidence,
        )
        validate_trial_unit_result(self.request, result, target_scope=self.run._target_scope)
        return result

    def reusable(self):
        result = self.result()
        return replacement_resources_reusable(self.request.cleanup_plan, result.cleanup_receipt)

    def capture_succeeded(self):
        capture = self.observations().get("capture")
        records = step_records(self.run, self.request.execution_attempt_id, 1)
        return bool(
            capture
            and capture.observation.complete
            and records
            and all(record.status.state.value == "succeeded" for record in records)
        )

    def execute_trial(self, request):
        from raes_contracts.runtime_state import OperationKind

        from .control_plane_mutation import control_plane_mutation

        if replace(request) != self.request:
            raise ValueError("trial adapter request conflicts with its admitted entry")
        self.run._assert_runtime_owner()
        self.run._engine.reserve(self.run)
        with (
            self.run._runtime_call(),
            self.run._resource_claim.runtime_call(self.run._engine.owner),
            control_plane_mutation(self.run, OperationKind.COMPOSITION_PHASE),
        ):
            for _ in range(16):
                state = self.advance()
                if state == "succeeded":
                    return self.result()
                if state != "progress":
                    raise TrialPending("trial requires observation or recovery through its shared runtime")
        raise TrialPending("trial has not reached its terminal cut")
