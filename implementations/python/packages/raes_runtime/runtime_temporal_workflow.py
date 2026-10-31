"""Temporal drives shared runtime progress without interpreting authored policy."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from raes_contracts.errors import InvalidInputError

    from .runtime_sequence_reference import RuntimeSequenceReference


async def _drive(payload: dict[str, Any]) -> str:
    reference = RuntimeSequenceReference.model_validate(payload)
    for _ in range(128):
        # A delivered state step reconciles its existing operation claims.
        # Temporal never retries an effect or invents a fresh RAE attempt.
        try:
            state = await workflow.execute_activity(
                "raes.runtime.advance",
                reference.model_dump(mode="json"),
                task_queue=reference.state_queue,
                start_to_close_timeout=timedelta(milliseconds=reference.activity_budget_ms),
                schedule_to_close_timeout=timedelta(milliseconds=reference.activity_budget_ms),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            state = "unavailable"
        if state not in {"progress", "pending", "indeterminate", "unavailable"}:
            return state
        if state != "progress":
            await workflow.sleep(timedelta(milliseconds=reference.poll_interval_ms))
    workflow.continue_as_new(reference.model_dump(mode="json"))


@workflow.defn(name="raes.run")
class RaeRunWorkflow:
    def __init__(self) -> None:
        self._reference = None

    @workflow.query(name="runtime_reference")
    def runtime_reference(self) -> dict[str, Any] | None:
        return self._reference

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> str:
        reference = RuntimeSequenceReference.model_validate(payload)
        if reference.kind != "run":
            raise InvalidInputError("run workflow reference kind mismatch")
        self._reference = reference.model_dump(mode="json")
        return await _drive(self._reference)


@workflow.defn(name="raes.experiment")
class RaeExperimentWorkflow:
    def __init__(self) -> None:
        self._reference = None

    @workflow.query(name="runtime_reference")
    def runtime_reference(self) -> dict[str, Any] | None:
        return self._reference

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> str:
        reference = RuntimeSequenceReference.model_validate(payload)
        if reference.kind != "experiment":
            raise InvalidInputError("experiment workflow reference kind mismatch")
        self._reference = reference.model_dump(mode="json")
        return await _drive(self._reference)
